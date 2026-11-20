
# -*- coding: utf-8 -*-
"""AI campaign suggestions - strictly data-grounded, human-approved."""
import json
import math
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from db import get_connection, engine
from assistant_engine import build_live_context, call_gpt, require_user
from operations import require_manager
from iran_time import iran_today
from sqlalchemy import text

router = APIRouter(prefix="/campaigns/ai", tags=["CampaignAI"])


def ensure_suggestion_storage(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS ai_suggestions (
        id SERIAL PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
        description TEXT, payload JSONB NOT NULL, rationale TEXT,
        status TEXT NOT NULL DEFAULT 'pending', suggested_by INTEGER,
        decided_by INTEGER, decided_at TIMESTAMPTZ, approved_campaign_id INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )"""))


def suggestion_payload(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


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
    today = iran_today()
    begin = today-timedelta(days=29)
    end = today+timedelta(days=1)
    cur.execute(
        "SELECT sp.name, COALESCE(SUM(s.total_amount), 0), COUNT(s.id) "
        "FROM salespersons sp LEFT JOIN sales s "
        " ON s.salesperson_id = sp.id AND s.date >= %s AND s.date < %s "
        "GROUP BY sp.id, sp.name ORDER BY 2 DESC",(begin,end))
    for (nm, tot, cnt) in cur.fetchall():
        per_sp.append("- " + str(nm) + ": " + format(float(tot), ",.0f") + " ریال | " + str(cnt) + " سند فروش و برگشت")
    cities = list()
    cur.execute(
        "SELECT COALESCE(NULLIF(c.city, ''), 'نامشخص') AS city, COUNT(s.id), COALESCE(SUM(s.total_amount), 0) "
        "FROM sales s JOIN customers c ON c.id = s.customer_id "
        "WHERE s.date >= %s AND s.date < %s "
        "GROUP BY city ORDER BY 3 DESC LIMIT 5",(begin,end))
    for (city, cnt, tot) in cur.fetchall():
        cities.append("- " + str(city) + ": " + format(float(tot), ",.0f") + " ریال | " + str(cnt) + " سند فروش و برگشت")
    cur.execute("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE date >= %s AND date < %s",(begin-timedelta(days=30),begin))
    prev30 = float(next(iter(cur.fetchone())) or 0)
    cur.close()
    conn.close()
    return per_sp, cities, prev30


@router.post("/suggest")
def suggest(user: dict = Depends(require_manager)):
    with engine.connect() as conn:
        ctx = build_live_context(conn,user)
    ctx['_actor'] = {key:user.get(key) for key in ('id','role','salesperson_id')}
    per_sp, cities, prev30 = build_market_brief()
    cur30 = float(ctx.get("sales_30d", 0) or 0)
    if cur30 <= 0 or ctx.get('invoices_30d') is None:
        raise HTTPException(422,detail='برای پیشنهاد تارگت کمپین، فروش خالص مثبت و معتبر لازم است؛ دیتای ناقص یا مبنای صفر را تأیید نمی‌کنم.')
    trend_line = ""
    if prev30 > 0:
        pct = round((cur30 - prev30) / prev30 * 100.0, 1)
        trend_line = " | روند نسبت به ماه قبل: " + ("+" if pct >= 0 else "") + str(pct) + "٪"
    low = cur30 * 1.1
    high = cur30 * 1.5
    brief = (
        "داده‌های تحلیلی زنده (فقط بر این مبنا تصمیم بگیر):\n"
        "- فروش ۳۰ روز اخیر: " + format(cur30, ",.0f") + " ریال | "
        + str(int(ctx.get("invoices_30d", 0))) + " سند فروش و برگشت" + trend_line + "\n"
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
    if not isinstance(answer,str) or not answer:
        raise HTTPException(status_code=502, detail="سرویس هوش مصنوعی پاسخ نداد — کلید LLM_API_KEY و اینترنت را بررسی کن.")
    prop = parse_json_block(answer)
    if not isinstance(prop,dict) or not prop.get("title"):
        raise HTTPException(status_code=502, detail="پاسخ نامعتبر بود — یک بار دیگر تلاش کن.")
    try:
        target=float(prop.get('target_amount'))
        reward=float(prop.get('reward_value',0))
        if not math.isfinite(target) or not low<=target<=high or not math.isfinite(reward) or not 0<=reward<=1e12:
            raise ValueError()
    except (ValueError,TypeError,OverflowError):
        raise HTTPException(502,detail='مبلغ پیشنهادی با محدودهٔ گزارش یا قواعد پاداش سازگار نیست؛ هیچ پیشنهادی ذخیره نشد.')
    days = 30
    try:
        days = max(7, min(int(prop.get("days", 30) or 30), 120))
    except Exception:
        days = 30
    starts = iran_today()
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
def pending(user: dict = Depends(require_manager)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, rationale, payload, created_at FROM ai_suggestions "
                "WHERE status = 'pending' ORDER BY id DESC LIMIT 10")
    out = list()
    for (sid, title, rationale, payload, created) in cur.fetchall():
        prop = suggestion_payload(payload)
        out.append(dict(id=sid, title=title, rationale=rationale, proposal=prop, created_at=str(created)))
    cur.close()
    conn.close()
    return out


@router.post("/decide")
def decide(data: dict, user: dict = Depends(require_manager)):
    raw_id=data.get("suggestion_id")
    if isinstance(raw_id,bool):
        raise HTTPException(422,"شناسهٔ پیشنهاد معتبر نیست.")
    try:
        sid=int(raw_id)
        if str(sid)!=str(raw_id) or sid<=0:raise ValueError()
    except (ValueError,TypeError):
        raise HTTPException(422,"شناسهٔ پیشنهاد معتبر نیست.")
    action=str(data.get("action","")).strip()
    if action not in ("approve","reject"):
        raise HTTPException(422,"تصمیم باید تأیید یا رد باشد.")
    conn=get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload, status FROM ai_suggestions WHERE id=%s AND kind='campaign' FOR UPDATE",(sid,))
                row=cur.fetchone()
                if not row:raise HTTPException(404,"پیشنهاد پیدا نشد.")
                payload_raw,status_now=row
                if status_now!="pending":raise HTTPException(409,"این پیشنهاد قبلاً تصمیم‌گیری شده است.")
                if action=="reject":
                    cur.execute("UPDATE ai_suggestions SET status='rejected',decided_by=%s,decided_at=NOW() WHERE id=%s",(user["id"],sid))
                    return {"status":"rejected"}
                prop=suggestion_payload(payload_raw)
                try:
                    target=float(prop['target_amount'])
                    reward=float(prop['reward_value'])
                    starts=date.fromisoformat(prop['starts_at'])
                    ends=date.fromisoformat(prop['ends_at'])
                    kind=prop['reward_type']
                    if not math.isfinite(target) or target<=0 or not math.isfinite(reward) or reward<0 or ends<starts or kind not in ('fixed','percent') or (kind=='percent' and reward>100):raise ValueError()
                    title=str(prop['title']).strip()
                    if not title:raise ValueError()
                except (ValueError,TypeError,KeyError):
                    raise HTTPException(422,"بدنهٔ پیشنهاد معتبر نیست؛ هیچ کمپینی ساخته نشد.")
                cur.execute("""INSERT INTO campaigns(title,description,starts_at,ends_at,target_amount,reward_type,reward_value,reward_note)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (title[:200],str(prop.get('description',''))[:500],starts,ends,target,kind,reward,str(prop.get('reward_note',''))[:300]))
                cid=cur.fetchone()[0]
                cur.execute("UPDATE ai_suggestions SET status='approved',decided_by=%s,decided_at=NOW(),approved_campaign_id=%s WHERE id=%s",(user['id'],cid,sid))
                return {"status":"approved","campaign_id":cid}
    finally:
        conn.close()
