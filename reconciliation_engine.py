from datetime import date
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import Connection, text

from iran_time import iran_today

def auto_pin_center_coordinates(db: Session, center_id: int, lat: float, lng: float) -> bool:
    """ثبت خودکار مختصات برای ۴۴۹ پایگاه فاقد لوکیشن در اولین حضور معتبر ویزیتور"""
    if not lat or not lng:
        return False
    try:
        res = db.execute(
            text("""
                UPDATE centers
                SET latitude = :lat, longitude = :lng
                WHERE id = :cid AND (latitude IS NULL OR longitude IS NULL)
            """),
            {"lat": lat, "lng": lng, "cid": center_id}
        )
        db.commit()
        return res.rowcount > 0
    except Exception:
        db.rollback()
        return False

def calculate_monthly_reconciliation(
    db: Connection | Session,
    plan_id: int,
    up_to_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    موتور تطبیق ۴گانه پایان ماه:
    1. انجام‌شده طبق برنامه (on_schedule)
    2. جابه‌جاشده در ماه (rescheduled)
    3. عقب‌افتاده / انجام‌نشده (missed)
    4. خارج از برنامه / سرزده (unplanned)
    """
    from monthly_visit_plans import month_window

    cutoff = up_to_date or iran_today()

    plan = db.execute(
        text("SELECT * FROM monthly_visit_plans WHERE id = :pid"),
        {"pid": plan_id}
    ).mappings().first()

    if not plan:
        return {"error": "برنامه ماهانه یافت نشد."}

    start, end = month_window(plan["month"])
    filters = {"pid": plan_id, "sp": plan["salesperson_id"],
               "start": start, "end": end, "cutoff": cutoff}
    stops = db.execute(
        text("""
            SELECT s.*, s.base_id AS center_id, s.objective AS visit_goal,
                COALESCE(p.name, b.name, m.name) AS center_name,
                EXISTS (
                SELECT 1 FROM base_checkins c
                WHERE c.salesperson_id = :sp AND c.status = 'verified'
                    AND c.base_source = s.base_source AND c.base_id = s.base_id
                    AND c.checked_in_at::date = s.visit_date
            ) AS verified_visit, EXISTS (
                SELECT 1 FROM daily_reports d
                WHERE d.salesperson_id = :sp AND d.report_date = s.visit_date
            ) AS has_daily_report
            FROM monthly_visit_plan_stops s
            LEFT JOIN pharmacies p ON s.base_source = 'pharmacies' AND s.base_id = p.id
            LEFT JOIN cosmetics_shops b ON s.base_source = 'cosmetics_shops' AND s.base_id = b.id
            LEFT JOIN kerman_bases_manual m ON s.base_source = 'kerman_bases_manual' AND s.base_id = m.id
            WHERE s.plan_id = :pid AND s.visit_date >= :start
                AND s.visit_date < :end AND s.visit_date <= :cutoff
            ORDER BY s.visit_date ASC, s.id ASC
        """),
        filters,
    ).mappings().all()

    unplanned = [dict(row) for row in db.execute(
        text("""
            SELECT c.base_source, c.base_id AS center_id,
                c.checked_in_at::date AS visit_date,
                COALESCE(p.name, b.name, m.name) AS center_name,
                'verified' AS outcome_status
            FROM base_checkins c
            LEFT JOIN pharmacies p ON c.base_source = 'pharmacies' AND c.base_id = p.id
            LEFT JOIN cosmetics_shops b ON c.base_source = 'cosmetics_shops' AND c.base_id = b.id
            LEFT JOIN kerman_bases_manual m ON c.base_source = 'kerman_bases_manual' AND c.base_id = m.id
            WHERE c.salesperson_id = :sp AND c.status = 'verified'
                AND c.checked_in_at >= :start AND c.checked_in_at < :end
                AND c.checked_in_at::date <= :cutoff
                AND NOT EXISTS (
                    SELECT 1 FROM monthly_visit_plan_stops s
                    WHERE s.plan_id = :pid AND s.base_source = c.base_source
                        AND s.base_id = c.base_id
                )
            GROUP BY c.checked_in_at::date, c.base_source, c.base_id, p.name, b.name, m.name
            ORDER BY visit_date, c.base_source, c.base_id
        """),
        filters,
    ).mappings()]
    on_schedule, rescheduled, missed = [], [], []

    for s in stops:
        stop_dict = dict(s)
        status = stop_dict.get("outcome_status") or stop_dict.get("status")

        if status == "rescheduled":
            rescheduled.append(stop_dict)
        elif status in ("completed", "order_placed", "scientific", "follow_up", "no_order", "done"):
            on_schedule.append(stop_dict)
        elif not status and stop_dict["verified_visit"] and stop_dict["has_daily_report"]:
            stop_dict["outcome_status"] = "verified"
            on_schedule.append(stop_dict)
        else:
            missed.append(stop_dict)

    total = len(stops)
    strict_pct = round((len(on_schedule) / total * 100), 1) if total > 0 else 0.0
    effective_pct = round(((len(on_schedule) + len(rescheduled)) / total * 100), 1) if total > 0 else 0.0
    total_rial = sum(int(x.get("order_amount_rial") or 0) for x in (on_schedule + rescheduled + unplanned))

    return {
        "plan_id": plan_id,
        "summary": {
            "total_planned_up_to_date": total,
            "on_schedule_count": len(on_schedule),
            "rescheduled_count": len(rescheduled),
            "missed_count": len(missed),
            "unplanned_count": len(unplanned),
            "strict_compliance_percent": strict_pct,
            "effective_coverage_percent": effective_pct,
            "total_orders_rial": total_rial
        },
        "buckets": {
            "on_schedule": on_schedule,
            "rescheduled": rescheduled,
            "missed": missed,
            "unplanned": unplanned
        }
    }
