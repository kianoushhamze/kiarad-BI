
# -*- coding: utf-8 -*-
"""AI campaign suggestions with human approval loop - reuses the real assistant engine."""
import json
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from db import get_connection, engine
from assistant_engine import build_live_context, call_gpt, require_user

router = APIRouter(prefix="/campaigns/ai", tags=["CampaignAI"])


def parse_json_block(text_value):
    start = text_value.find(chr(123))
    end = text_value.rfind(chr(125))
    if start == -1 or end == -1 or end <= start:
        return None
    chunk = text_value[start:end + 1]
    try:
        return json.loads(chunk)
    except Exception:
        return None


@router.post("/suggest")
def suggest(user: dict = Depends(require_user)):
    with engine.connect() as conn:
        ctx = build_live_context(conn)
    ask = (
        "بر اساس داده‌های زنده‌ی شرکت، یک کمپین فروش و پاداش برای تیم ویزیتور پیشنهاد بده. "
        "پاسخ فقط و فقط یک آبجکت JSON خالص باشد، بدون هیچ متن اضافه، با کلیدهای: "
        "title (عنوان کوتاه)، description (توضیح یک‌خطی)، days (طول کمپین به روز، عدد بین ۷ تا ۱۲۰)، "
        "target_amount (هدف فروش کل بازه به ریال، عددی منطقی و قابل‌دستیابی بر اساس فروش واقعی)، "
        "reward_type (fixed یا percent)، reward_value (مبلغ ریال یا درصد)، "
        "reward_note (توضیح پاداش)، rationale (دلیل تحلیلی در دو سه جمله با ارجاع به اعداد واقعی)."
    )
    answer = call_gpt(ask, ctx, list(), user.get("role", "unknown"), user.get("full_name", ""))
    if not answer:
        raise HTTPException(status_code=502, detail="سرویس هوش مصنوعی پاسخ نداد — کلید LLM_API_KEY و اینترنت را بررسی کن.")
    prop = parse_json_block(answer)
    if not prop or not prop.get("title"):
        raise HTTPException(status_code=502, detail="پاسخ نامعتبر بود — یک بار دیگر تلاش کن.")
    days = 30
    try:
        days = max(7, min(int(prop.get("days", 30) or 30), 120))
    except Exception:
        days = 30
    starts = date.today()
    ends = starts + timedelta(days=days)
    payload = dict(
        title=str(prop.get("title", ""))[:200],
        description=str(prop.get("description", ""))[:500],
        starts_at=starts.isoformat(),
        ends_at=ends.isoformat(),
        target_amount=float(prop.get("target_amount", 0) or 0),
        reward_type=str(prop.get("reward_type", "fixed")),
        reward_value=float(prop.get("reward_value", 0) or 0),
        reward_note=str(prop.get("reward_note", ""))[:300],
    )
    rationale = str(prop.get("rationale", ""))[:1000]
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ai_suggestions (kind, title, description, payload, rationale, status, suggested_by) "
        "VALUES ('campaign', %s, %s, %s, %s, 'pending', %s) RETURNING id",
        (payload.get("title"), payload.get("description"),
         json.dumps(payload, ensure_ascii=False), rationale, user.get("id", 0)))
    sid = next(iter(cur.fetchone()))
    conn.commit()
    cur.close()
    conn.close()
    return dict(suggestion_id=sid, proposal=payload, rationale=rationale)


@router.get("/pending")
def pending(user: dict = Depends(require_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, rationale, payload, created_at FROM ai_suggestions "
                "WHERE status = 'pending' ORDER BY id DESC LIMIT 10")
    out = list()
    for (sid, title, rationale, payload, created) in cur.fetchall():
        try:
            prop = json.loads(payload)
        except Exception:
            prop = dict()
        out.append(dict(id=sid, title=title, rationale=rationale, proposal=prop, created_at=str(created)))
    cur.close()
    conn.close()
    return out


@router.post("/decide")
def decide(data: dict, user: dict = Depends(require_user)):
    sid = int(data.get("suggestion_id", 0) or 0)
    action = str(data.get("action", "")).strip()
    if not sid or action not in ("approve", "reject"):
        raise HTTPException(status_code=422, detail="suggestion_id and action (approve/reject) are required")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT payload, status FROM ai_suggestions WHERE id = %s", (sid,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="suggestion not found")
    payload_raw, status_now = row
    if status_now != "pending":
        cur.close()
        conn.close()
        raise HTTPException(status_code=409, detail="این پیشنهاد قبلاً تصمیم‌گیری شده است.")
    if action == "reject":
        cur.execute("UPDATE ai_suggestions SET status = 'rejected', decided_by = %s, decided_at = NOW() WHERE id = %s",
                    (user.get("id", 0), sid))
        conn.commit()
        cur.close()
        conn.close()
        return dict(status="rejected")
    try:
        prop = json.loads(payload_raw)
    except Exception:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail="payload corrupted")
    cur.execute(
        "INSERT INTO campaigns (title, description, starts_at, ends_at, target_amount, "
        "reward_type, reward_value, reward_note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (str(prop.get("title", "کمپین هوشمند"))[:200], str(prop.get("description", ""))[:500],
         str(prop.get("starts_at")), str(prop.get("ends_at")),
         float(prop.get("target_amount", 0) or 0), str(prop.get("reward_type", "fixed")),
         float(prop.get("reward_value", 0) or 0), str(prop.get("reward_note", ""))[:300]))
    cid = next(iter(cur.fetchone()))
    cur.execute("UPDATE ai_suggestions SET status = 'approved', decided_by = %s, decided_at = NOW(), "
                "approved_campaign_id = %s WHERE id = %s",
                (user.get("id", 0), cid, sid))
    conn.commit()
    cur.close()
    conn.close()
    return dict(status="approved", campaign_id=cid)
