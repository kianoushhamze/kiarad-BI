
# -*- coding: utf-8 -*-
"""Campaigns: team reward campaigns with live progress - raw SQL, zero ORM, zero path params."""
from fastapi import APIRouter, HTTPException
from db import get_connection

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.get("")
def list_campaigns():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, description, starts_at, ends_at, target_amount, reward_type, "
        "reward_value, reward_note, is_active, "
        "(SELECT COALESCE(SUM(s.total_amount), 0) FROM sales s "
        " WHERE s.date::date >= c.starts_at AND s.date::date <= c.ends_at) AS achieved "
        "FROM campaigns c ORDER BY c.is_active DESC, c.id DESC")
    out = list()
    for (cid, title, desc, s_at, e_at, target, rtype, rval, rnote, active, achieved) in cur.fetchall():
        progress = 0.0
        if target and float(target) > 0:
            progress = round(float(achieved) / float(target) * 100.0, 1)
        out.append(dict(id=cid, title=title, description=desc,
                        starts_at=str(s_at), ends_at=str(e_at),
                        target_amount=float(target), reward_type=rtype,
                        reward_value=float(rval), reward_note=rnote,
                        is_active=active, achieved=float(achieved),
                        progress_percent=progress))
    cur.close()
    conn.close()
    return out


@router.post("")
def create_campaign(data: dict):
    title = str(data.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    starts_at = str(data.get("starts_at", "")).strip()
    ends_at = str(data.get("ends_at", "")).strip()
    if not starts_at or not ends_at:
        raise HTTPException(status_code=422, detail="starts_at and ends_at are required")
    target = float(data.get("target_amount", 0) or 0)
    reward_type = str(data.get("reward_type", "fixed"))
    reward_value = float(data.get("reward_value", 0) or 0)
    description = str(data.get("description", "")).strip()
    reward_note = str(data.get("reward_note", "")).strip()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO campaigns (title, description, starts_at, ends_at, target_amount, "
        "reward_type, reward_value, reward_note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (title, description, starts_at, ends_at, target, reward_type, reward_value, reward_note))
    cid = next(iter(cur.fetchone()))
    conn.commit()
    cur.close()
    conn.close()
    return dict(status="success", campaign_id=cid, message="کمپین ساخته شد.")


@router.get("/leaderboard")
def leaderboard(campaign_id: int = 0):
    if not campaign_id:
        raise HTTPException(status_code=422, detail="campaign_id is required")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT starts_at, ends_at FROM campaigns WHERE id = %s", (campaign_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="campaign not found")
    start_d, end_d = row
    cur.execute(
        "SELECT sp.id, sp.name, COALESCE(SUM(s.total_amount), 0), COUNT(s.id) "
        "FROM salespersons sp LEFT JOIN sales s "
        " ON s.salesperson_id = sp.id AND s.date::date >= %s AND s.date::date <= %s "
        "GROUP BY sp.id, sp.name ORDER BY 3 DESC",
        (start_d, end_d))
    out = list()
    rank = 0
    for (sp_id, name, achieved, cnt) in cur.fetchall():
        rank = rank + 1
        out.append(dict(rank=rank, salesperson_id=sp_id, name=name,
                        achieved=float(achieved), invoices=cnt))
    cur.close()
    conn.close()
    return dict(campaign_id=campaign_id, leaderboard=out)


@router.post("/close")
def close_campaign(data: dict):
    cid = int(data.get("campaign_id", 0) or 0)
    if not cid:
        raise HTTPException(status_code=422, detail="campaign_id is required")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE campaigns SET is_active = FALSE WHERE id = %s", (cid,))
    conn.commit()
    changed = cur.rowcount
    cur.close()
    conn.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="campaign not found")
    return dict(status="success", message="کمپین بسته شد.")
