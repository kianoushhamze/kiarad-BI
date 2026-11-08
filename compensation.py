
# -*- coding: utf-8 -*-
"""Compensation: contracts, targets, attendance and verified base check-ins."""
import math
import re
import hashlib
import json
from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from db import get_connection
import payroll_service
from operations import current_user, require_manager
from iran_time import IRAN_TIMEZONE, iran_now
from payroll_periods import period_is_approved
from location_policy import MAX_AUTOMATIC_ACCURACY_M

router = APIRouter(prefix="/api/compensation", tags=["Compensation"])
_POSITION_CHECK_RESULTS = {}
COMPENSATION_ADMIN_ROLES = {"ceo", "sales_manager", "cfo", "finance", "accountant", "hr"}
BASE_TABLES = {"pharmacies", "cosmetics_shops", "kerman_bases_manual"}


def _payroll_operation(operation, *, write=False):
    from psycopg2.errors import UniqueViolation
    conn = get_connection()
    cur = conn.cursor()
    try:
        result = operation(cur)
        if write:
            conn.commit()
        return result
    except UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409,detail="این سند یا کارکرد قبلاً ثبت شده است")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@router.on_event("startup")
def initialize_payroll_rules():
    _payroll_operation(payroll_service.ensure_payroll_schema, write=True)


def ensure_location_schema():
    conn = get_connection()
    cur = conn.cursor()
    try:
        _ensure_attendance_schema(cur)
        for table in BASE_TABLES:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema='public' AND table_name = %s
                )
            """, (table,))
            if not cur.fetchone()[0]:
                print(f"[compensation] table '{table}' missing, skip")
                continue
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS visit_radius_m INTEGER DEFAULT 150")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS base_checkins (
                id SERIAL PRIMARY KEY,
                salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
                base_source VARCHAR(40) NOT NULL,
                base_id INTEGER NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                accuracy_m DOUBLE PRECISION,
                distance_m DOUBLE PRECISION,
                status VARCHAR(24) NOT NULL,
                note TEXT,
                checked_in_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS ix_base_checkins_salesperson_time ON base_checkins(salesperson_id, checked_in_at DESC)")
        _ensure_checkin_review_schema(cur)
        _ensure_checkin_submission_schema(cur)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS visit_route_assignments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
                base_source VARCHAR(40) NOT NULL,
                base_id INTEGER NOT NULL,
                visit_date DATE NOT NULL,
                stop_order INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                assigned_by INTEGER NOT NULL REFERENCES users(id),
                assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, base_source, base_id, visit_date)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS ix_visit_routes_user_date ON visit_route_assignments(user_id, visit_date, stop_order)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payroll_approvals (
                id SERIAL PRIMARY KEY,
                salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
                payroll_month VARCHAR(7) NOT NULL,
                worked_hours NUMERIC NOT NULL DEFAULT 0,
                verified_visit_days INTEGER NOT NULL DEFAULT 0,
                base_pay NUMERIC NOT NULL DEFAULT 0,
                visit_allowance NUMERIC NOT NULL DEFAULT 0,
                additions NUMERIC NOT NULL DEFAULT 0,
                deductions NUMERIC NOT NULL DEFAULT 0,
                approved_total NUMERIC NOT NULL DEFAULT 0,
                note TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'approved',
                approved_by INTEGER NOT NULL REFERENCES users(id),
                approved_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (salesperson_id, payroll_month)
            )
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()



@router.on_event("startup")
def initialize_compensation_schema():
    ensure_location_schema()


def _ensure_checkin_review_schema(cur, *, temporary: bool = False):
    cur.execute(f"""CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS base_checkin_reviews (
        id SERIAL PRIMARY KEY,
        checkin_id INTEGER NOT NULL UNIQUE REFERENCES base_checkins(id),
        reviewed_by INTEGER NOT NULL REFERENCES users(id),
        original_status VARCHAR(24) NOT NULL,
        decision VARCHAR(24) NOT NULL,
        note TEXT NOT NULL,
        reviewed_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran')
    )""")


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = max(0.0, min(1.0, a))
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _ensure_attendance_schema(cur, *, temporary: bool = False):
    cur.execute(f"""CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS salesperson_locations (
        id SERIAL PRIMARY KEY,
        salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
        latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
        battery_level INTEGER, activity VARCHAR(100), accuracy DOUBLE PRECISION,
        recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
    )""")
    cur.execute(f"""CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS attendance_sessions (
        id SERIAL PRIMARY KEY,
        salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
        start_time TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'), end_time TIMESTAMP,
        start_lat DOUBLE PRECISION, start_lng DOUBLE PRECISION,
        end_lat DOUBLE PRECISION, end_lng DOUBLE PRECISION,
        duration_hours NUMERIC(8,2), is_active BOOLEAN DEFAULT TRUE
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_attendance_person_active ON attendance_sessions(salesperson_id,is_active)")


def _position_values(data: dict):
    if any(isinstance(data.get(key), bool) for key in ("lat", "lng", "accuracy_m")):
        raise HTTPException(status_code=422, detail="مختصات و دقت موقعیت معتبر نیست")
    try:
        lat, lng = float(data.get("lat")), float(data.get("lng"))
        accuracy = float(data["accuracy_m"]) if data.get("accuracy_m") is not None else None
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(status_code=422, detail="مختصات و دقت موقعیت معتبر نیست")
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        raise HTTPException(status_code=422, detail="مختصات موقعیت خارج از محدوده است")
    if accuracy is not None and (not math.isfinite(accuracy) or accuracy <= 0):
        raise HTTPException(status_code=422, detail="دقت موقعیت باید عدد مثبت باشد")
    return lat, lng, accuracy


@router.post("/position-check")
def check_device_position(data: dict, user: dict = Depends(current_user)):
    from datetime import datetime
    _lat, _lng, accuracy = _position_values(data)
    if accuracy is None:
        raise HTTPException(status_code=422, detail="دقت موقعیت لازم است")
    try:
        observed = datetime.fromisoformat(str(data.get('observed_at','')).replace('Z','+00:00'))
        if observed.tzinfo is None:
            raise ValueError
        observed = observed.astimezone(IRAN_TIMEZONE)
    except ValueError:
        raise HTTPException(status_code=422, detail="زمان دریافت موقعیت باید معتبر و دارای منطقهٔ زمانی باشد")
    received = iran_now()
    age = (received-observed).total_seconds()
    if age < -10 or age > 120:
        raise HTTPException(status_code=422, detail="موقعیت تازه نیست؛ دوباره اجازهٔ دریافت بدهید")
    # A diagnostic is neither attendance nor a visit; raw coordinates are discarded.
    result = {'ok':True,'accuracy_m':accuracy,'observed_at':observed.isoformat(),'received_at':received.isoformat(),
              'max_automatic_accuracy_m':MAX_AUTOMATIC_ACCURACY_M}
    _POSITION_CHECK_RESULTS[user['id']] = result
    return result


@router.get("/position-check")
def device_position_check_result(user: dict = Depends(current_user)):
    return _POSITION_CHECK_RESULTS.get(user['id'], {'ok':False,'state':'not_tested'})


def _attendance_profile_id(value, user: dict) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise HTTPException(status_code=422, detail="پروفایل پرسنل معتبر نیست")
    try:
        salesperson_id = int(value)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(status_code=422, detail="پروفایل پرسنل معتبر نیست")
    if salesperson_id <= 0:
        raise HTTPException(status_code=422, detail="پروفایل پرسنل معتبر نیست")
    require_salesperson_access(salesperson_id, user)
    return salesperson_id


def _attendance_started_at(value):
    return value.astimezone(IRAN_TIMEZONE).isoformat() if value is not None else None


def _record_shift_location(cur, salesperson_id, lat, lng, accuracy, activity):
    cur.execute("""INSERT INTO salesperson_locations
        (salesperson_id, latitude, longitude, activity, accuracy, battery_level, recorded_at)
        VALUES (%s,%s,%s,%s,%s,NULL,NOW())""", (salesperson_id, lat, lng, activity, accuracy))


def require_compensation_admin(user: dict = Depends(current_user)) -> dict:
    if user.get("role") not in COMPENSATION_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="دسترسی مدیریت حقوق لازم است")
    return user


def require_salesperson_access(salesperson_id: int, user: dict) -> None:
    if user.get("role") in {"ceo", "sales_manager"}:
        return
    linked_id = user.get("salesperson_id")
    if not linked_id or int(linked_id) != salesperson_id:
        raise HTTPException(status_code=403, detail="فقط اطلاعات خودتان در دسترس است")

CONTRACT_COLS = ("id", "hourly_rate", "min_monthly_hours", "settlement_commission_percent",
                 "daily_mission_allowance", "per_km_rate")
TARGET_COLS = ("target_type", "item_identifier", "item_title",
               "target_amount", "target_quantity", "commission_percent")


@router.get("/contract/{salesperson_id}")
def get_contract(salesperson_id: int, month: str | None = None, user: dict = Depends(current_user)):
    if user.get("role") not in COMPENSATION_ADMIN_ROLES:
        require_salesperson_access(salesperson_id, user)
    return _payroll_operation(lambda cur: payroll_service.get_contract(cur, salesperson_id, month))



@router.post("/contract/{salesperson_id}")
def save_contract(salesperson_id: int, data: dict, user: dict = Depends(require_compensation_admin)):
    return _payroll_operation(lambda cur: payroll_service.save_contract(cur, salesperson_id, data, user), write=True)



@router.get("/attendance/status")
def attendance_status(salesperson_id: int | None = None, user: dict = Depends(current_user)):
    sp = _attendance_profile_id(salesperson_id if salesperson_id is not None else user.get("salesperson_id"), user)
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("""SELECT id, start_time AT TIME ZONE 'Asia/Tehran',
            GREATEST(EXTRACT(EPOCH FROM ((NOW() AT TIME ZONE 'Asia/Tehran')-start_time))/3600.0,0)
            FROM attendance_sessions WHERE salesperson_id=%s AND is_active=TRUE ORDER BY id""", (sp,))
        rows = cur.fetchall()
        if len(rows) > 1:
            raise HTTPException(status_code=409, detail="بیش از یک شیفت باز ثبت شده است؛ مدیر باید کارکرد را بررسی کند")
        if not rows:
            return {"is_active": False, "status": "inactive", "salesperson_id": sp, "session_id": None, "started_at": None}
        row = rows[0]
        return {"is_active": True, "status": "active", "salesperson_id": sp, "session_id": row[0],
                "started_at": _attendance_started_at(row[1]), "elapsed_hours": float(row[2])}
    finally:
        cur.close(); conn.close()


@router.post("/attendance/start")
def start_attendance(data: dict, user: dict = Depends(current_user)):
    sp = _attendance_profile_id(data.get("salesperson_id", user.get("salesperson_id")), user)
    lat, lng, accuracy = _position_values(data)
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (sp,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="پروفایل پرسنل پیدا نشد")
        cur.execute("""SELECT id, start_time AT TIME ZONE 'Asia/Tehran'
            FROM attendance_sessions WHERE salesperson_id=%s AND is_active=TRUE ORDER BY id FOR UPDATE""", (sp,))
        rows = cur.fetchall()
        if len(rows) > 1:
            raise HTTPException(status_code=409, detail="بیش از یک شیفت باز ثبت شده است؛ مدیر باید کارکرد را بررسی کند")
        if rows:
            return {"status": "already_active", "is_active": True, "session_id": rows[0][0], "started_at": _attendance_started_at(rows[0][1])}
        if period_is_approved(cur, sp, iran_now()):
            raise HTTPException(status_code=409, detail="کارکرد این دوره تأیید شده؛ شروع شیفت جدید نیازمند بازبینی دوره است")
        cur.execute("""INSERT INTO attendance_sessions (salesperson_id,start_time,start_lat,start_lng,is_active)
            VALUES (%s,NOW() AT TIME ZONE 'Asia/Tehran',%s,%s,TRUE) RETURNING id,start_time AT TIME ZONE 'Asia/Tehran'""", (sp,lat,lng))
        session_id, started_at = cur.fetchone()
        _record_shift_location(cur, sp, lat, lng, accuracy, "shift_start")
        conn.commit()
        return {"status": "started", "is_active": True, "session_id": session_id, "started_at": _attendance_started_at(started_at)}
    finally:
        cur.close(); conn.close()


@router.post("/attendance/stop")
def stop_attendance(data: dict, user: dict = Depends(current_user)):
    sp = _attendance_profile_id(data.get("salesperson_id", user.get("salesperson_id")), user)
    lat, lng, accuracy = _position_values(data)
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (sp,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="پروفایل پرسنل پیدا نشد")
        cur.execute("SELECT id FROM attendance_sessions WHERE salesperson_id=%s AND is_active=TRUE ORDER BY id FOR UPDATE", (sp,))
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(status_code=409, detail="شیفت فعالی پیدا نشد؛ وضعیت را تازه کنید")
        if len(rows) > 1:
            raise HTTPException(status_code=409, detail="بیش از یک شیفت باز ثبت شده است؛ مدیر باید کارکرد را بررسی کند")
        session_id = rows[0][0]
        cur.execute("""UPDATE attendance_sessions SET end_time=NOW() AT TIME ZONE 'Asia/Tehran',end_lat=%s,end_lng=%s,is_active=FALSE,
            duration_hours=ROUND(GREATEST(EXTRACT(EPOCH FROM ((NOW() AT TIME ZONE 'Asia/Tehran')-start_time))/3600.0,0)::numeric,2)
            WHERE id=%s RETURNING duration_hours""", (lat,lng,session_id))
        duration = cur.fetchone()[0]
        _record_shift_location(cur, sp, lat, lng, accuracy, "shift_end")
        conn.commit()
        return {"status": "stopped", "is_active": False, "session_id": session_id, "duration_hours": float(duration)}
    finally:
        cur.close(); conn.close()


@router.get("/bases")
def list_bases(user: dict = Depends(current_user)):
    conn = get_connection()
    cur = conn.cursor()
    items = []
    try:
        for table in sorted(BASE_TABLES):
            cur.execute(
                f"SELECT id, name, city, address, latitude, longitude, COALESCE(visit_radius_m, 150) FROM {table} ORDER BY name"
            )
            for row in cur.fetchall():
                items.append(dict(source=table, id=row[0], name=row[1], city=row[2], address=row[3],
                                  latitude=row[4], longitude=row[5], visit_radius_m=row[6],
                                  location_configured=row[4] is not None and row[5] is not None))
    finally:
        cur.close()
        conn.close()
    return {"items": items}


def _base_record(cur, source: str, base_id: int):
    if source not in BASE_TABLES:
        raise HTTPException(status_code=422, detail="نوع پایگاه نامعتبر است")
    cur.execute(f"SELECT id, name, city, address FROM {source} WHERE id=%s", (base_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="پایگاه پیدا نشد")
    return row


@router.get("/visit-routes")
def list_visit_routes(user_id: int | None = None, visit_date: date | None = None,
                      user: dict = Depends(current_user)):
    target_user_id = user.get("id")
    if user.get("role") in COMPENSATION_ADMIN_ROLES and user_id is not None:
        target_user_id = user_id
    conn = get_connection(); cur = conn.cursor()
    try:
        params = [target_user_id]
        date_clause = ""
        if visit_date is not None:
            date_clause = " AND r.visit_date=%s"
            params.append(visit_date)
        cur.execute(f"""
            SELECT r.id, r.user_id, r.salesperson_id, r.base_source, r.base_id,
                   r.visit_date, r.stop_order, r.note, r.assigned_at,
                   COALESCE(p.name, c.name, m.name) AS base_name,
                   COALESCE(p.city, c.city, m.city) AS city,
                   COALESCE(p.address, c.address, m.address) AS address,
                   ci.id AS checkin_id, ci.status AS checkin_status,
                   ci.checked_in_at, ci.distance_m
            FROM visit_route_assignments r
            LEFT JOIN pharmacies p ON r.base_source='pharmacies' AND p.id=r.base_id
            LEFT JOIN cosmetics_shops c ON r.base_source='cosmetics_shops' AND c.id=r.base_id
            LEFT JOIN kerman_bases_manual m ON r.base_source='kerman_bases_manual' AND m.id=r.base_id
            LEFT JOIN LATERAL (
                SELECT id, status, checked_in_at, distance_m FROM base_checkins
                WHERE salesperson_id=r.salesperson_id AND base_source=r.base_source
                  AND base_id=r.base_id AND checked_in_at::date=r.visit_date
                ORDER BY CASE WHEN status='verified' THEN 0 ELSE 1 END, checked_in_at DESC, id DESC LIMIT 1
            ) ci ON TRUE
            WHERE r.user_id=%s{date_clause}
            ORDER BY r.visit_date, r.stop_order, r.id
        """, tuple(params))
        columns = [item[0] for item in cur.description]
        items = [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return {"items": items}


@router.post("/visit-routes")
def assign_visit_route(data: dict, user: dict = Depends(require_compensation_admin)):
    try:
        target_user_id = int(data.get("user_id"))
        source = str(data.get("source") or "")
        base_id = int(data.get("base_id"))
        planned_date = date.fromisoformat(str(data.get("visit_date")))
        stop_order = max(1, min(int(data.get("stop_order", 1)), 999))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="اطلاعات برنامهٔ مسیر نامعتبر است")
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('monthly-visit-plans',0))")
        cur.execute("SELECT to_regclass('monthly_visit_plan_stops')")
        if cur.fetchone()[0]:
            cur.execute('''SELECT 1 FROM monthly_visit_plan_stops s JOIN monthly_visit_plans p ON p.id=s.plan_id
                WHERE p.status='approved' AND s.base_source=%s AND s.base_id=%s AND s.visit_date=%s''',(source,base_id,planned_date))
            if cur.fetchone():raise HTTPException(409,'این پایگاه و روز در برنامهٔ ماهانهٔ مصوب است؛ از مسیر موردی تغییر نمی‌کند.')
        _base_record(cur, source, base_id)
        cur.execute("SELECT salesperson_id FROM users WHERE id=%s AND is_active::text IN ('1','true','t')", (target_user_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=422, detail="حساب انتخاب‌شده به پروفایل ویزیتور متصل نیست")
        cur.execute("""
            INSERT INTO visit_route_assignments
                (user_id, salesperson_id, base_source, base_id, visit_date, stop_order, note, assigned_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id, base_source, base_id, visit_date)
            DO UPDATE SET stop_order=EXCLUDED.stop_order, note=EXCLUDED.note,
                          salesperson_id=EXCLUDED.salesperson_id, assigned_by=EXCLUDED.assigned_by,
                          assigned_at=NOW()
            RETURNING id
        """, (target_user_id, row[0], source, base_id, planned_date, stop_order,
              str(data.get("note") or "")[:500], user["id"]))
        route_id = cur.fetchone()[0]
        conn.commit()
    finally:
        cur.close(); conn.close()
    return {"status": "assigned", "id": route_id}


@router.delete("/visit-routes/{route_id}")
def delete_visit_route(route_id: int, _: dict = Depends(require_compensation_admin)):
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('monthly-visit-plans',0))")
        cur.execute("SELECT to_regclass('monthly_visit_plan_stops')")
        if cur.fetchone()[0]:
            cur.execute('SELECT 1 FROM monthly_visit_plan_stops WHERE route_id=%s',(route_id,))
            if cur.fetchone():raise HTTPException(409,'مسیر متصل به برنامهٔ ماهانه از این بخش حذف نمی‌شود.')
        cur.execute("DELETE FROM visit_route_assignments WHERE id=%s RETURNING id", (route_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="برنامهٔ مسیر پیدا نشد")
        conn.commit()
    finally:
        cur.close(); conn.close()
    return {"status": "deleted"}


@router.put("/bases/{source}/{base_id}/location")
def set_base_location(source: str, base_id: int, data: dict, _: dict = Depends(require_compensation_admin)):
    if source not in BASE_TABLES:
        raise HTTPException(status_code=404, detail="نوع پایگاه نامعتبر است")
    lat, lng, accuracy = _position_values(data)
    if accuracy is not None and accuracy > 100:
        raise HTTPException(status_code=422, detail="دقت موقعیت برای ثبت مرجع پایگاه کافی نیست")
    try:
        visit_radius = max(50, min(int(data.get("visit_radius_m", 150)), 1000))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="مختصات پایگاه نامعتبر است")
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute(f"UPDATE {source} SET latitude=%s, longitude=%s, visit_radius_m=%s WHERE id=%s",
                    (lat, lng, visit_radius, base_id))
        if cur.rowcount != 1:
            raise HTTPException(status_code=404, detail="پایگاه پیدا نشد")
        conn.commit()
    finally:
        cur.close(); conn.close()
    return {"status": "updated", "base_id": base_id, "visit_radius_m": visit_radius}


def _ensure_checkin_submission_schema(cur, *, temporary=False):
    cur.execute(f"""CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS base_checkin_submissions (
        user_id INTEGER NOT NULL,submission_key UUID NOT NULL,payload_hash TEXT NOT NULL,
        response JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(user_id,submission_key))""")


@router.post("/base-checkins")
def create_base_checkin(data: dict, user: dict = Depends(current_user)):
    source = str(data.get("source") or "")
    if source not in BASE_TABLES:
        raise HTTPException(status_code=422, detail="نوع پایگاه نامعتبر است")
    try:
        if isinstance(data.get("base_id"), bool) or not isinstance(data.get("base_id"), (int, str)):
            raise ValueError()
        base_id = int(data.get("base_id"))
        if base_id <= 0:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="اطلاعات تیک حضور نامعتبر است")
    lat, lng, accuracy = _position_values(data)
    note = str(data.get("note") or "").strip()
    if not note or len(note) > 2000:
        raise HTTPException(status_code=422, detail="گزارش بازدید را در حداکثر ۲۰۰۰ نویسه بنویسید")
    salesperson_id = user.get("salesperson_id")
    if not salesperson_id:
        raise HTTPException(status_code=403, detail="حساب باید به پروفایل ویزیتور متصل باشد")
    submission_key=None
    if data.get('submission_key') is not None:
        try:
            submission_key=str(UUID(str(data['submission_key'])))
        except (ValueError,TypeError,AttributeError):
            raise HTTPException(422,'شناسهٔ ارسال حضور معتبر نیست')
    signature=hashlib.sha256(json.dumps([salesperson_id,source,base_id,lat,lng,accuracy,note],
                                      ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (salesperson_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=403, detail="پروفایل پرسنل پیدا نشد")
        if submission_key:
            cur.execute('SELECT payload_hash,response FROM base_checkin_submissions WHERE user_id=%s AND submission_key=%s',
                        (user['id'],submission_key))
            previous=cur.fetchone()
            if previous:
                if previous[0]!=signature:
                    raise HTTPException(409,'این شناسهٔ ارسال قبلاً با گزارش دیگری استفاده شده است')
                return {**previous[1],'already_saved':True}
        if period_is_approved(cur, salesperson_id, iran_now()):
            raise HTTPException(status_code=409, detail="کارکرد این ماه تأیید شده؛ ثبت حضور جدید نیازمند بازبینی دوره است")
        cur.execute(f"SELECT name, latitude, longitude, COALESCE(visit_radius_m,150) FROM {source} WHERE id=%s", (base_id,))
        base = cur.fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="پایگاه پیدا نشد")
        measured_distance = None
        status_value = "pending_review"
        if base[1] is not None and base[2] is not None:
            measured_distance = round(distance_m(lat, lng, float(base[1]), float(base[2])), 1)
            if measured_distance > int(base[3]):
                status_value = "outside_radius"
            elif accuracy is not None and accuracy <= MAX_AUTOMATIC_ACCURACY_M:
                status_value = "verified"
        cur.execute("""
            INSERT INTO base_checkins
                (salesperson_id, base_source, base_id, latitude, longitude, accuracy_m, distance_m, status, note,checked_in_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW() AT TIME ZONE 'Asia/Tehran') RETURNING id, checked_in_at
        """, (salesperson_id, source, base_id, lat, lng, accuracy, measured_distance, status_value,
              note))
        checkin_id, checked_at = cur.fetchone()
        cur.execute("""
            INSERT INTO salesperson_locations
                (salesperson_id, latitude, longitude, activity, accuracy, battery_level, recorded_at)
            VALUES (%s,%s,%s,%s,%s,NULL,NOW())
        """, (salesperson_id, lat, lng, "base_checkin", accuracy))
        result={"status":status_value,"checkin_id":checkin_id,"base_name":base[0],
                "distance_m":measured_distance,"checked_in_at":checked_at.isoformat(),"already_saved":False}
        if submission_key:
            cur.execute('INSERT INTO base_checkin_submissions(user_id,submission_key,payload_hash,response) VALUES(%s,%s,%s,%s::jsonb)',
                        (user['id'],submission_key,signature,json.dumps(result,default=str,ensure_ascii=False)))
        conn.commit()
    finally:
        cur.close(); conn.close()
    return result


@router.get("/base-checkins")
def list_base_checkins(status: str | None = None, salesperson_id: int | None = None,
                       limit: int = Query(default=100, ge=1, le=200), user: dict = Depends(current_user)):
    if status is not None and status not in {"pending_review", "outside_radius", "verified", "rejected"}:
        raise HTTPException(status_code=422, detail="وضعیت حضور معتبر نیست")
    manager = user.get("role") in {"ceo", "sales_manager"}
    target = salesperson_id if manager else user.get("salesperson_id")
    if not manager and not target:
        return {"items": []}
    clauses, params = [], []
    if target is not None:
        clauses.append("ci.salesperson_id=%s"); params.append(target)
    if status is not None:
        clauses.append("ci.status=%s"); params.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("""SELECT ci.*,sp.name AS salesperson_name,
            COALESCE(p.name,c.name,m.name,'پایگاه حذف‌شده') AS base_name,
            rv.original_status,rv.decision AS review_decision,rv.note AS review_note,
            rv.reviewed_at,u.full_name AS reviewer_name
            FROM base_checkins ci JOIN salespersons sp ON sp.id=ci.salesperson_id
            LEFT JOIN pharmacies p ON ci.base_source='pharmacies' AND ci.base_id=p.id
            LEFT JOIN cosmetics_shops c ON ci.base_source='cosmetics_shops' AND ci.base_id=c.id
            LEFT JOIN kerman_bases_manual m ON ci.base_source='kerman_bases_manual' AND ci.base_id=m.id
            LEFT JOIN base_checkin_reviews rv ON rv.checkin_id=ci.id
            LEFT JOIN users u ON u.id=rv.reviewed_by""" + where + " ORDER BY ci.checked_in_at DESC,ci.id DESC LIMIT %s", tuple(params + [limit]))
        columns = [item[0] for item in cur.description]
        items = [dict(zip(columns,row)) for row in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return {"items": items}


@router.post("/base-checkins/{checkin_id}/review")
def review_base_checkin(checkin_id: int, data: dict, user: dict = Depends(require_manager)):
    decision = str(data.get("decision") or "")
    note = str(data.get("note") or "").strip()
    if decision not in {"verified", "rejected"} or not note or len(note) > 2000:
        raise HTTPException(status_code=422, detail="تصمیم و علت بررسی را در حداکثر ۲۰۰۰ نویسه وارد کنید")
    conn = get_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT salesperson_id,status,checked_in_at FROM base_checkins WHERE id=%s FOR UPDATE", (checkin_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="حضور پیدا نشد")
        if user.get("salesperson_id") == row[0]:
            raise HTTPException(status_code=403, detail="بررسی حضور خودتان باید توسط مدیر دیگری انجام شود")
        if row[1] not in {"pending_review", "outside_radius"}:
            raise HTTPException(status_code=409, detail="این حضور قبلاً تعیین تکلیف شده است")
        cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (row[0],))
        cur.fetchone()
        if period_is_approved(cur, row[0], row[2]):
            raise HTTPException(status_code=409, detail="کارکرد این ماه تأیید شده؛ ابتدا دوره باید بازبینی شود")
        cur.execute("""INSERT INTO base_checkin_reviews
            (checkin_id,reviewed_by,original_status,decision,note)
            VALUES (%s,%s,%s,%s,%s) RETURNING reviewed_at""", (checkin_id,user["id"],row[1],decision,note))
        reviewed_at = cur.fetchone()[0]
        cur.execute("UPDATE base_checkins SET status=%s WHERE id=%s", (decision,checkin_id))
        conn.commit()
    finally:
        cur.close(); conn.close()
    return {"id": checkin_id, "status": decision, "reviewed_at": reviewed_at}


def _validate_payroll_month(month: str) -> None:
    payroll_service.period(month)



def _payroll_calculation(cur, salesperson_id: int, month: str) -> dict:
    return payroll_service.calculate_period(cur, salesperson_id, month)



@router.get("/payroll-people")
def payroll_people(user: dict = Depends(current_user)):
    conn = get_connection(); cur = conn.cursor()
    try:
        if user.get("role") in COMPENSATION_ADMIN_ROLES:
            cur.execute("""
                SELECT sp.id, sp.name FROM salespersons sp
                WHERE EXISTS (SELECT 1 FROM users u WHERE u.salesperson_id=sp.id AND u.is_active::text IN ('1','true','t'))
                ORDER BY sp.name
            """)
        else:
            salesperson_id = user.get("salesperson_id")
            if not salesperson_id:
                return {"items": [], "can_approve": False}
            cur.execute("SELECT id, name FROM salespersons WHERE id=%s", (salesperson_id,))
        items = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return {"items": items, "can_approve": user.get("role") in COMPENSATION_ADMIN_ROLES}


@router.get("/payroll/{salesperson_id}")
def payroll_summary(salesperson_id: int, month: str, user: dict = Depends(current_user)):
    if user.get("role") not in COMPENSATION_ADMIN_ROLES:
        require_salesperson_access(salesperson_id, user)
    _validate_payroll_month(month)
    return _payroll_operation(lambda cur: payroll_service.summary(cur, salesperson_id, month))



@router.post("/payroll/{salesperson_id}/approve")
def approve_payroll(salesperson_id: int, month: str, data: dict,
                    user: dict = Depends(require_compensation_admin)):
    return _payroll_operation(lambda cur: payroll_service.approve(cur, salesperson_id, month, data, user), write=True)


@router.post("/rules-draft")
def compensation_rules_draft(data: dict, _: dict = Depends(require_compensation_admin)):
    from payroll_assistant import draft_rules
    return draft_rules(data)


@router.post("/rules-preview")
def compensation_rules_preview(data: dict, _: dict = Depends(require_compensation_admin)):
    from payroll_engine import calculate_payroll, PayrollValidationError
    try:
        result = calculate_payroll(payroll_service.normalized_rules(data.get('rules') or {}),
            data.get('worked_hours',0), data.get('verified_visit_days',0),
            facts=data.get('facts',[]), source_complete=data.get('source_complete',{}))
    except (PayrollValidationError,ValueError,TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error))
    return {**result, 'preview_only':True, 'saved':False, 'currency':'IRR'}


@router.get("/contract/{salesperson_id}/history")
def compensation_contract_history(salesperson_id: int, user: dict = Depends(current_user)):
    if user.get('role') not in COMPENSATION_ADMIN_ROLES:
        require_salesperson_access(salesperson_id,user)
    def read(cur):
        cur.execute("""SELECT id,effective_month,approved,created_at,rules_json FROM compensation_rule_versions
            WHERE salesperson_id=%s ORDER BY effective_start DESC,id DESC LIMIT 100""", (salesperson_id,))
        return {'items':[dict(zip(('rule_version','effective_month','rules_approved','created_at','rules'),row)) for row in cur.fetchall()]}
    return _payroll_operation(read)


@router.get("/payroll/{salesperson_id}/facts")
def compensation_facts(salesperson_id: int, month: str, user: dict = Depends(current_user)):
    if user.get('role') not in COMPENSATION_ADMIN_ROLES:
        require_salesperson_access(salesperson_id,user)
    month,start,end,_ = payroll_service.period(month)
    def read(cur):
        cur.execute("""SELECT id,event_date,event_key,kind,amount,quantity,product_id,brand,source_note
            FROM compensation_facts WHERE salesperson_id=%s AND event_date>=%s AND event_date<%s
            ORDER BY event_date,id LIMIT 5000""",(salesperson_id,start.date(),end.date()))
        items=[dict(zip(('id','event_date','event_key','kind','amount','quantity','product_id','brand','source_note'),row)) for row in cur.fetchall()]
        cur.execute("SELECT source,complete,note FROM compensation_source_checks WHERE salesperson_id=%s AND payroll_month=%s",(salesperson_id,month))
        return {'items':items,'sources':[dict(zip(('source','complete','note'),row)) for row in cur.fetchall()]}
    return _payroll_operation(read)


@router.post("/payroll/{salesperson_id}/facts",status_code=201)
def add_compensation_fact(salesperson_id: int, data: dict, user: dict = Depends(require_compensation_admin)):
    return _payroll_operation(lambda cur: payroll_service.record_fact(cur,salesperson_id,data,user),write=True)


@router.post("/payroll/{salesperson_id}/sources")
def verify_compensation_sources(salesperson_id: int, month: str, data: dict, user: dict = Depends(require_compensation_admin)):
    month,start,_,_ = payroll_service.period(month)
    source,complete,note=data.get('source'),data.get('complete'),str(data.get('note') or '').strip()
    if source not in {'sales','collections','mileage','workdays','content','company_sales','rewards'} or type(complete) is not bool or not 8<=len(note)<=2000:
        raise HTTPException(status_code=422,detail="منبع، وضعیت تطبیق و توضیح مستند لازم است")
    def write(cur):
        cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE",(salesperson_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404,detail="پرسنل پیدا نشد")
        from payroll_periods import period_is_approved
        if period_is_approved(cur,salesperson_id,start):
            raise HTTPException(status_code=409,detail="منبع دورهٔ بسته تغییر نمی‌کند")
        cur.execute("""INSERT INTO compensation_source_checks(salesperson_id,payroll_month,source,complete,note,verified_by)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(salesperson_id,payroll_month,source) DO UPDATE SET
            complete=EXCLUDED.complete,note=EXCLUDED.note,verified_by=EXCLUDED.verified_by,
            verified_at=NOW() AT TIME ZONE 'Asia/Tehran'""",(salesperson_id,month,source,complete,note,user['id']))
        return {'status':'verified','source':source,'complete':complete}
    return _payroll_operation(write,write=True)
