
# -*- coding: utf-8 -*-
"""AI campaign suggestions - strictly data-grounded, human-approved."""
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


def build_market_brief():
    conn = get_connection()
    cur = conn.cursor()
    per_sp = list()
    cur.execute(
        "SELECT sp.name, COALESCE(SUM(s.total_amount), 0), COUNT(s.id) "
        "FROM salespersons sp LEFT JOIN sales s "
        " ON s.salesperson_id = sp.id AND s.date >= CURRENT_DATE - INTERVAL '30 days' "
        "GROUP BY sp.id, sp.name ORDER BY 2 DESC")
    for (nm, tot, cnt) in cur.fetchall():
        per_sp.append("- " + str(nm) + ": " + format(float(tot), ",.0f") + " ریال | " + str(cnt) + " فاکتور")
    cities = list()
    cur.execute(
        "SELECT COALESCE(NULLIF(c.city, ''), 'نامشخص') AS city, COUNT(s.id), COALESCE(SUM(s.total_amount), 0) "
        "FROM sales s JOIN customers c ON c.id = s.customer_id "
        "WHERE s.date >= CURRENT_DATE - INTERVAL '30 days' "
        "GROUP BY city ORDER BY 3 DESC LIMIT 5")
    for (city, cnt, tot) in cur.fetchall():
        cities.append("- " + str(city) + ": " + format(float(tot), ",.0f") + " ریال | " + str(cnt) + " فاکتور")
    cur.execute("SELECT COALESCE(SUM(total_amount), 0) FROM sales "
                "WHERE date >= CURRENT_DATE - INTERVAL '60 days' AND date < CURRENT_DATE - INTERVAL '30 days'")
    prev30 = float(next(iter(cur.fetchone())) or 0)
    cur.close()
    conn.close()
    return per_sp, cities, prev30


@router.post("/suggest")
def suggest(user: dict = Depends(require_user)):
    with engine.connect() as conn:
        ctx = build_live_context(conn)
    per_sp, cities, prev30 = build_market_brief()
    cur30 = float(ctx.get("sales_30d", 0) or 0)
    trend_line = ""
    if prev30 > 0:
        pct = round((cur30 - prev30) / prev30 * 100.0, 1)
        trend_line = " | روند نسبت به ماه قبل: " + ("+" if pct >= 0 else "") + str(pct) + "٪"
    low = cur30 * 1.1
    high = cur30 * 1.5
    brief = (
        "داده‌های تحلیلی زنده (فقط بر این مبنا تصمیم بگیر):\n"
        "- فروش ۳۰ روز اخیر: " + format(cur30, ",.0f") + " ریال | "
        + str(int(ctx.get("invoices_30d", 0))) + " فاکتور" + trend_line + "\n"
        "- فروش ۳۰ روز قبل از آن: " + format(prev30, ",.0f") + " ریال\n"
        "- فروش به تفکیک ویزیتور (۳۰ روز اخیر):\n" + "\n".join(per_sp) + "\n"
        "- سهم شهرها (۳۰ روز اخیر):\n" + "\n".join(cities) + "\n"
    )
    rules = (
        "قوانین الزامی:\n"
        "۱) target_amount باید بین " + format(low, ",.0f") + " و " + format(high, ",.0f")
        + " ریال باشد (۱.۱ تا ۱.۵ برابر فروش واقعی ۳۰ روز اخیر) و در rationale نسبت به این اعداد را توضیح بده.\n"
        "۲) هیچ عددی از خودت اختراع نکن؛ فقط از داده‌های بالا.\n"
        "۳) اگر داده برای تصمیم کافی نیست (مثلاً داده تستی یا پراکنده است)، در rationale صریح بگو چه داده‌ای کم است.\n"
        "۴) پاسخ فقط آبجکت JSON با کلیدهای: title, description, days, target_amount, reward_type, reward_value, reward_note, rationale."
    )
    ask = brief + "\n" + rules + "\nبر این مبنا یک کمپین فروش و پاداش برای تیم ویزیتور پیشنهاد بده."
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
    return dict(suggestion_id=sid, proposal=payload, rationale=rationale, market_brief=dict(sales_30d=cur30, prev_30d=prev30))


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
