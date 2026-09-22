
"""
Kiarad BI - AI Copilot v2
Free conversation via OpenRouter GPT + live BI data + conversation memory.
No fake fallback. No default CEO role. Real JWT auth only.
"""
import os
import logging
import requests
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from db import engine
from operations import current_user

logger = logging.getLogger("kiarad_assistant")
router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def fa_num(v, d=0):
    try:
        return format(float(v), ",." + str(d) + "f")
    except Exception:
        return str(v)


def money(v):
    return fa_num(v) + " ریال"


def get_env_live(key, default=""):
    try:
        with open(r"D:\project\kiaradbi\.env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    pieces = line.split("=", 1)
                    return pieces.pop().strip()
    except Exception:
        pass
    return os.getenv(key, default)


def require_user(auth: Optional[str] = Header(default=None)) -> dict:
    """Real auth: no token means 401. Never a default CEO."""
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user(auth)


def build_live_context(conn) -> dict:
    def s(sql):
        try:
            return float(conn.execute(text(sql)).scalar() or 0)
        except Exception:
            return 0

    return dict(
        today=date.today().isoformat(),
        sales_30d=s("SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE date >= CURRENT_DATE - INTERVAL '30 days'"),
        sales_today=s("SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE date = CURRENT_DATE"),
        invoices_30d=s("SELECT COUNT(*) FROM sales WHERE date >= CURRENT_DATE - INTERVAL '30 days'"),
        open_tasks=s("SELECT COUNT(*) FROM tasks WHERE status NOT IN ('done','cancelled')"),
        overdue_tasks=s("SELECT COUNT(*) FROM tasks WHERE status NOT IN ('done','cancelled') AND due_date IS NOT NULL AND due_date < CURRENT_DATE"),
        active_users=s("SELECT COUNT(*) FROM users WHERE is_active = true"),
    )


def context_text(ctx, role, full_name):
    return (
        "داده‌های زنده شرکت کیاراد از دیتابیس (امروز: " + str(ctx.get("today", "")) + ") :\n"
        + "- فروش 30 روز اخیر: " + money(ctx.get("sales_30d", 0)) + "\n"
        + "- فروش امروز: " + money(ctx.get("sales_today", 0)) + "\n"
        + "- تعداد فاکتورهای 30 روز: " + fa_num(ctx.get("invoices_30d", 0)) + "\n"
        + "- تسک‌های باز: " + fa_num(ctx.get("open_tasks", 0)) + " | عقب‌افتاده: " + fa_num(ctx.get("overdue_tasks", 0)) + "\n"
        + "- کاربران فعال سیستم: " + fa_num(ctx.get("active_users", 0)) + "\n"
        + "- نقش کاربر فعلی: " + str(role) + " | نام: " + str(full_name)
    )


def call_gpt(msg, ctx, history, role, full_name):
    api_key = get_env_live("LLM_API_KEY")
    model = get_env_live("LLM_MODEL", "openai/gpt-4o-mini")
    if not api_key:
        return None
    sys_prompt = (
        "تو «دستیار ارشد هوش تجاری کیاراد» هستی، در شرکت پخش دارو و محصولات درماتولوژی در استان کرمان. "
        "سبد محصولات: سوآلین ویرا، درمالیست، ام‌سی کازمتیک، توتال درم. "
        "قوانین مهم: 1) برای هر سوالی پاسخ بده؛ از اینکه سوال در حوزه تو نیست خودداری نکن. "
        "2) اگر سوال عددی درباره شرکت بود، فقط از داده‌های زنده زیر استفاده کن و عدد اختراعی نگو. "
        "3) اگر داده کافی نبود، صریح بگو که داده کافی در سیستم نیست. "
        "4) به فارسی روان، حرفه‌ای و نسبتاً کوتاه پاسخ بده و از ایموجی کم استفاده کن. "
        "5) در تحلیل‌ها همیشه یک پیشنهاد عملی واضح داشته باش.\n"
        + context_text(ctx, role, full_name)
    )
    headers = dict()
    headers["Authorization"] = "Bearer " + api_key
    headers["Content-Type"] = "application/json"
    headers["HTTP-Referer"] = "http://localhost:3000"
    headers["X-Title"] = "Kiarad BI Command Center"
    messages = list()
    messages.append(dict(role="system", content=sys_prompt))
    for h in history:
        r = "assistant" if h.get("role") == "assistant" else "user"
        messages.append(dict(role=r, content=h.get("content", "")))
    messages.append(dict(role="user", content=msg))
    payload = dict(model=model, messages=messages, temperature=0.6, max_tokens=1500)
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions",
                            json=payload, headers=headers, timeout=45)
        if res.status_code == 200:
            data = res.json()
            choices = data.get("choices") or list()
            first = next(iter(choices), None)
            if first:
                msgobj = first.get("message") or dict()
                content = msgobj.get("content")
                if content:
                    return content.strip()
            return None
        logger.warning("OpenRouter status: " + str(res.status_code) + " " + str(res.text)[:300])
    except Exception as e:
        logger.warning("OpenRouter error: " + str(e))
    return None


def load_history(user_id, limit=8):
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT role, content FROM (SELECT role, content FROM assistant_messages "
                "WHERE user_id = :u ORDER BY id DESC LIMIT :l) h ORDER BY id"
            ), dict(u=user_id, l=limit)).mappings().all()
            return list(dict(r) for r in rows)
    except Exception:
        return list()


def save_turn(user_id, user_msg, ai_msg):
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO assistant_messages (user_id, role, content, intent, created_at) "
                "VALUES (:u, 'user', :c, 'chat', NOW()), (:u, 'assistant', :a, 'chat', NOW())"
            ), dict(u=user_id, c=user_msg, a=ai_msg))
    except Exception as e:
        logger.warning("history save failed: " + str(e))


@router.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(require_user)):
    with engine.connect() as conn:
        ctx = build_live_context(conn)
    uid = user.get("id", 0)
    history = load_history(uid, 8)
    answer = call_gpt(req.message, ctx, history,
                      user.get("role", "unknown"), user.get("full_name", ""))
    if not answer:
        raise HTTPException(status_code=502,
                            detail="سرویس هوش مصنوعی در دسترس نیست. اینترنت و کلید OpenRouter را بررسی کنید.")
    save_turn(uid, req.message, answer)
    return dict(answer=answer, mode="gpt_free_v2", user_role=user.get("role", "unknown"))


@router.get("/history")
def history(limit: int = Query(default=30, ge=1, le=100), user: dict = Depends(require_user)):
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT id, role, content, intent, created_at FROM (SELECT id, role, content, intent, created_at "
                "FROM assistant_messages WHERE user_id = :u ORDER BY id DESC LIMIT :l) h ORDER BY id"
            ), dict(u=user.get("id", 0), l=limit)).mappings().all()
            return dict(messages=list(dict(r) for r in rows), mode="gpt_free_v2")
    except Exception:
        return dict(messages=list(), mode="gpt_free_v2")


@router.delete("/history")
def clear_history(user: dict = Depends(require_user)):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM assistant_messages WHERE user_id = :u"),
                         dict(u=user.get("id", 0)))
    except Exception:
        pass
    return dict(status="cleared")
