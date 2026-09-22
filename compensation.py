
# -*- coding: utf-8 -*-
"""Compensation: contracts, targets, attendance - raw SQL, zero ORM dependency."""
from fastapi import APIRouter, HTTPException
from db import get_connection

router = APIRouter(prefix="/api/compensation", tags=["Compensation"])

CONTRACT_COLS = ("id", "hourly_rate", "min_monthly_hours", "settlement_commission_percent",
                 "daily_mission_allowance", "per_km_rate")
TARGET_COLS = ("target_type", "item_identifier", "item_title",
               "target_amount", "target_quantity", "commission_percent")


@router.get("/contract/{salesperson_id}")
def get_contract(salesperson_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, hourly_rate, min_monthly_hours, settlement_commission_percent, "
        "daily_mission_allowance, per_km_rate FROM salesperson_contracts WHERE salesperson_id = %s",
        (salesperson_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return dict(configured=False, salesperson_id=salesperson_id)
    contract = dict(zip(CONTRACT_COLS, row))
    cur.execute(
        "SELECT target_type, item_identifier, item_title, target_amount, target_quantity, "
        "commission_percent FROM salesperson_targets WHERE contract_id = %s",
        (contract.get("id"),))
    targets = list()
    for t in cur.fetchall():
        targets.append(dict(zip(TARGET_COLS, t)))
    cur.close()
    conn.close()
    contract.update(configured=True, salesperson_id=salesperson_id, targets=targets)
    return contract


@router.post("/contract/{salesperson_id}")
def save_contract(salesperson_id: int, data: dict):
    try:
        hourly_rate = float(data.get("hourly_rate", 0) or 0)
        min_hours = float(data.get("min_monthly_hours", 176) or 176)
        settlement = float(data.get("settlement_commission_percent", 0) or 0)
        allowance = float(data.get("daily_mission_allowance", 0) or 0)
        per_km = float(data.get("per_km_rate", 0) or 0)
        targets = data.get("targets") or list()
    except Exception:
        raise HTTPException(status_code=422, detail="invalid payload")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO salesperson_contracts (salesperson_id, hourly_rate, min_monthly_hours, "
        "settlement_commission_percent, daily_mission_allowance, per_km_rate, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, NOW()) "
        "ON CONFLICT (salesperson_id) DO UPDATE SET hourly_rate = EXCLUDED.hourly_rate, "
        "min_monthly_hours = EXCLUDED.min_monthly_hours, "
        "settlement_commission_percent = EXCLUDED.settlement_commission_percent, "
        "daily_mission_allowance = EXCLUDED.daily_mission_allowance, "
        "per_km_rate = EXCLUDED.per_km_rate, updated_at = NOW() RETURNING id",
        (salesperson_id, hourly_rate, min_hours, settlement, allowance, per_km))
    contract_id = next(iter(cur.fetchone()))
    cur.execute("DELETE FROM salesperson_targets WHERE contract_id = %s", (contract_id,))
    for t in targets:
        cur.execute(
            "INSERT INTO salesperson_targets (contract_id, target_type, item_identifier, "
            "item_title, target_amount, target_quantity, commission_percent) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (contract_id, str(t.get("target_type", "brand")), str(t.get("item_identifier", "")),
             str(t.get("item_title", "")), float(t.get("target_amount", 0) or 0),
             int(t.get("target_quantity", 0) or 0), float(t.get("commission_percent", 0) or 0)))
    conn.commit()
    cur.close()
    conn.close()
    return dict(status="success", message="قرارداد ویزیتور ذخیره شد.")


@router.post("/attendance/start")
def start_attendance(data: dict):
    sp = int(data.get("salesperson_id", 0) or 0)
    if not sp:
        raise HTTPException(status_code=422, detail="salesperson_id is required")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM attendance_sessions WHERE salesperson_id = %s AND is_active = TRUE", (sp,))
    row = cur.fetchone()
    if row:
        cur.close()
        conn.close()
        return dict(status="already_active", session_id=next(iter(row)))
    cur.execute(
        "INSERT INTO attendance_sessions (salesperson_id, start_time, start_lat, start_lng, is_active) "
        "VALUES (%s, NOW(), %s, %s, TRUE) RETURNING id",
        (sp, data.get("lat"), data.get("lng")))
    session_id = next(iter(cur.fetchone()))
    conn.commit()
    cur.close()
    conn.close()
    return dict(status="started", session_id=session_id)


@router.post("/attendance/stop")
def stop_attendance(data: dict):
    sp = int(data.get("salesperson_id", 0) or 0)
    if not sp:
        raise HTTPException(status_code=422, detail="salesperson_id is required")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM attendance_sessions WHERE salesperson_id = %s AND is_active = TRUE", (sp,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="نشست فعالی یافت نشد.")
    session_id = next(iter(row))
    cur.execute(
        "UPDATE attendance_sessions SET end_time = NOW(), end_lat = %s, end_lng = %s, is_active = FALSE, "
        "duration_hours = ROUND((EXTRACT(EPOCH FROM (NOW() - start_time)) / 3600.0)::numeric, 2) "
        "WHERE id = %s RETURNING duration_hours",
        (data.get("lat"), data.get("lng"), session_id))
    dur = next(iter(cur.fetchone()))
    conn.commit()
    cur.close()
    conn.close()
    return dict(status="stopped", duration_hours=float(dur))
