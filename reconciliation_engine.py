from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

def ensure_reconciliation_schema(db: Session) -> None:
    """افزودن ایمن ستون‌های نتیجه ویزیت، کد پیش‌فاکتور و ثبت خودکار مختصات بدون حذف داده‌های قبلی"""
    statements = [
        "ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS outcome_status VARCHAR(50);",
        "ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS holoo_preinvoice_code VARCHAR(100);",
        "ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS order_amount_rial BIGINT DEFAULT 0;",
        "ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS outcome_notes TEXT;",
        "ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS follow_up_date DATE;"
    ]
    for stmt in statements:
        try:
            db.execute(text(stmt))
        except Exception:
            pass
    db.commit()

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
    db: Session,
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
    cutoff = up_to_date or date.today()

    plan = db.execute(
        text("SELECT * FROM monthly_visit_plans WHERE id = :pid"),
        {"pid": plan_id}
    ).mappings().first()

    if not plan:
        return {"error": "برنامه ماهانه یافت نشد."}

    stops = db.execute(
        text("""
            SELECT s.*
            FROM monthly_visit_plan_stops s
            WHERE s.plan_id = :pid
            ORDER BY s.visit_date ASC, s.id ASC
        """),
        {"pid": plan_id}
    ).mappings().all()

    on_schedule, rescheduled, missed, unplanned = [], [], [], []

    for s in stops:
        stop_dict = dict(s)
        v_date = stop_dict.get("visit_date")
        status = stop_dict.get("outcome_status") or stop_dict.get("status")

        if status in ("completed", "order_placed", "scientific", "follow_up", "no_order", "done"):
            on_schedule.append(stop_dict)
        elif status == "rescheduled":
            rescheduled.append(stop_dict)
        else:
            if v_date and str(v_date) <= str(cutoff):
                missed.append(stop_dict)

    total = len(stops) if stops else 0
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
