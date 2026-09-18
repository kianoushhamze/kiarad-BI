"""Role-aware, deterministic business assistant for Kiarad BI.

Only a fixed catalogue of read-only queries is used. Company data is never
sent to an external AI service and free text is never converted to SQL.
"""

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import engine
from operations import current_user

router = APIRouter(prefix="/assistant", tags=["assistant"])
MANAGEMENT_ROLES = {"ceo", "sales_manager", "finance"}
PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1000)


def fa_number(value: float | int, decimals: int = 0) -> str:
    return f"{float(value):,.{decimals}f}".translate(PERSIAN_DIGITS)


def money(value: float | int) -> str:
    return f"{fa_number(value)} ریال"


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("ي", "ی").replace("ك", "ک")).strip().lower()


def detect_intent(message: str) -> str:
    value = normalize(message)
    catalog = [
        ("liquidity", ("نقدینگی", "کسری", "چک", "پرداختنی", "خزانه")),
        ("debtors", ("بدهکار", "مطالبات", "وصول", "طلب", "مشتری را پیگیری")),
        ("tasks", ("تسک", "کارهای من", "وظیفه", "عقب افتاده", "عقب‌افتاده")),
        ("reports", ("گزارش شب", "گزارش کار", "ویزیت", "رقیب", "سفارش از دست")),
        ("inventory", ("موجودی کالا", "انبار", "کم موجود", "کالا", "محصول")),
        ("team", ("ویزیتور", "فروشنده", "تیم", "عملکرد کارکنان", "بهترین فروش")),
        ("forecast", ("پیش بینی فروش", "پیش‌بینی فروش", "پایان ماه", "فروش آینده", "روند فروش")),
        ("target", ("تارگت", "هدف فروش", "درصد تحقق", "تحقق هدف")),
        ("overview", ("وضعیت", "خلاصه", "امروز", "فروش چقدر", "داشبورد")),
        ("help", ("چه سوال", "چه سؤال", "راهنما", "کمک", "چه کاری")),
    ]
    for intent, words in catalog:
        if any(word in value for word in words):
            return intent
    return "help"


def scalar(conn, sql: str, params: dict | None = None) -> float:
    return float(conn.execute(text(sql), params or {}).scalar() or 0)


def sales_scope(user: dict) -> tuple[str, dict]:
    if user["role"] == "salesperson":
        return " AND salesperson_id=:salesperson_id", {"salesperson_id": user["salesperson_id"] or -1}
    return "", {}


def sales_overview(conn, user: dict) -> dict[str, Any]:
    clause, params = sales_scope(user)
    total = scalar(conn, f"SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE 1=1 {clause}", params)
    month = scalar(conn, f"""SELECT COALESCE(SUM(total_amount),0) FROM sales
        WHERE date >= date_trunc('month', CURRENT_DATE) {clause}""", params)
    invoices = int(scalar(conn, f"SELECT COUNT(*) FROM sales WHERE 1=1 {clause}", params))
    return {"total_sales": total, "month_sales": month, "invoice_count": invoices}


def target_analysis(conn, user: dict) -> dict[str, Any]:
    params: dict[str, Any] = {}
    where = "status='active'"
    if user["role"] == "salesperson":
        where += " AND salesperson_id=:salesperson_id"
        params["salesperson_id"] = user["salesperson_id"] or -1
    row = conn.execute(text(f"""SELECT id, title, target_amount, start_date, end_date, salesperson_id
        FROM targets WHERE {where}
        ORDER BY start_date DESC NULLS LAST, id DESC LIMIT 1"""), params).mappings().first()
    if not row:
        return {"exists": False, "target": 0, "actual": 0, "achievement": 0, "remaining": 0}
    sale_params = {"start": row["start_date"], "end": row["end_date"]}
    person_clause = ""
    if row["salesperson_id"] is not None:
        person_clause = " AND salesperson_id=:salesperson_id"
        sale_params["salesperson_id"] = row["salesperson_id"]
    actual = scalar(conn, f"""SELECT COALESCE(SUM(total_amount),0) FROM sales
        WHERE CAST(date AS DATE) BETWEEN :start AND :end {person_clause}""", sale_params)
    target = float(row["target_amount"] or 0)
    return {
        "exists": True, "title": row["title"], "target": target, "actual": actual,
        "achievement": round(actual / target * 100, 1) if target else 0,
        "remaining": max(target - actual, 0),
    }


def sales_forecast(conn, user: dict) -> dict[str, Any]:
    clause, params = sales_scope(user)
    rows = conn.execute(text(f"""SELECT date_trunc('month', date)::date AS month,
               COALESCE(SUM(total_amount),0) AS amount
        FROM sales WHERE date >= date_trunc('month', CURRENT_DATE) - interval '5 months' {clause}
        GROUP BY 1 ORDER BY 1"""), params).mappings().all()
    month_start = date.today().replace(day=1)
    current = next((float(r["amount"] or 0) for r in rows if r["month"] == month_start), 0)
    elapsed = max(date.today().day, 1)
    next_month = date(date.today().year + (date.today().month == 12), 1 if date.today().month == 12 else date.today().month + 1, 1)
    days_in_month = (next_month - month_start).days
    run_rate = current / elapsed * days_in_month
    completed = [float(r["amount"] or 0) for r in rows if r["month"] < month_start]
    baseline = sum(completed[-3:]) / min(len(completed), 3) if completed else run_rate
    forecast = max(current, run_rate * 0.65 + baseline * 0.35)
    return {
        "current": current, "forecast": round(forecast), "days_elapsed": elapsed,
        "confidence": "medium" if len(completed) >= 2 else "low",
    }


def task_analysis(conn, user: dict) -> dict[str, Any]:
    params: dict[str, Any] = {}
    where = "1=1"
    if user["role"] == "salesperson":
        where = "assigned_to=:user_id"
        params["user_id"] = user["id"]
    row = conn.execute(text(f"""SELECT
        COUNT(*) FILTER (WHERE status <> 'completed') AS open_count,
        COUNT(*) FILTER (WHERE status <> 'completed' AND due_date < NOW()) AS overdue_count,
        COALESCE(AVG(progress) FILTER (WHERE status <> 'completed'),0) AS avg_progress
        FROM tasks WHERE {where}"""), params).mappings().first()
    return {
        "open": int(row["open_count"] or 0), "overdue": int(row["overdue_count"] or 0),
        "average_progress": round(float(row["avg_progress"] or 0), 1),
    }


def debtor_analysis(conn) -> dict[str, Any]:
    snapshot = conn.execute(text("""SELECT id, total_amount, row_count, snapshot_date
        FROM receivable_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1""")).mappings().first()
    if not snapshot:
        return {"exists": False, "total": 0, "count": 0, "top": []}
    top = conn.execute(text("""SELECT counterparty, balance FROM receivable_balances
        WHERE snapshot_id=:id ORDER BY balance DESC LIMIT 3"""), {"id": snapshot["id"]}).mappings().all()
    return {
        "exists": True, "total": float(snapshot["total_amount"] or 0),
        "count": int(snapshot["row_count"] or 0), "top": [dict(x) for x in top],
    }


def liquidity_analysis(conn) -> dict[str, Any]:
    cash = scalar(conn, "SELECT COALESCE(SUM(current_balance),0) FROM cash_accounts WHERE is_active=1")
    reserve = scalar(conn, "SELECT COALESCE(SUM(minimum_reserve),0) FROM cash_accounts WHERE is_active=1")
    receivable = scalar(conn, """SELECT COALESCE(SUM(amount*collection_probability),0)
        FROM financial_documents WHERE status='open' AND document_type='receivable'
        AND due_date <= CURRENT_DATE+30""")
    payable = scalar(conn, """SELECT COALESCE(SUM(amount),0) FROM financial_documents
        WHERE status='open' AND document_type='payable' AND due_date <= CURRENT_DATE+30""")
    fixed = scalar(conn, "SELECT COALESCE(SUM(amount),0) FROM fixed_expenses WHERE is_active=1")
    available = cash - reserve + receivable - payable - fixed
    next_due = conn.execute(text("""SELECT counterparty, amount, due_date FROM financial_documents
        WHERE status='open' AND document_type='payable' ORDER BY due_date, id LIMIT 1""")).mappings().first()
    return {
        "cash": cash, "reserve": reserve, "receivable_30d": receivable,
        "payable_30d": payable, "fixed_expenses": fixed, "available_30d": available,
        "next_payable": dict(next_due) if next_due else None,
    }


def inventory_analysis(conn) -> dict[str, Any]:
    row = conn.execute(text("""SELECT COUNT(*) AS product_count,
        COALESCE(SUM(price*stock),0) AS value,
        COUNT(*) FILTER (WHERE stock <= 10) AS low_count FROM products""")).mappings().first()
    low = conn.execute(text(
        "SELECT name, stock FROM products WHERE stock <= 10 ORDER BY stock, name LIMIT 5"
    )).mappings().all()
    return {
        "products": int(row["product_count"] or 0), "value": float(row["value"] or 0),
        "low_count": int(row["low_count"] or 0), "low_items": [dict(x) for x in low],
    }


def report_analysis(conn, user: dict) -> dict[str, Any]:
    params: dict[str, Any] = {}
    where = "report_date >= CURRENT_DATE-30"
    if user["role"] == "salesperson":
        where += " AND salesperson_id=:salesperson_id"
        params["salesperson_id"] = user["salesperson_id"] or -1
    row = conn.execute(text(f"""SELECT COUNT(*) AS reports,
        COALESCE(SUM(visits_count),0) AS visits, COALESCE(SUM(orders_count),0) AS orders,
        COALESCE(SUM(lost_orders_count),0) AS lost,
        COALESCE(SUM(reported_sales_amount),0) AS sales
        FROM daily_reports WHERE {where}"""), params).mappings().first()
    return {
        key: float(row[key] or 0) if key == "sales" else int(row[key] or 0)
        for key in ("reports", "visits", "orders", "lost", "sales")
    }


def team_analysis(conn) -> dict[str, Any]:
    rows = conn.execute(text("""SELECT sp.name, COALESCE(SUM(s.total_amount),0) AS sales
        FROM salespersons sp LEFT JOIN sales s ON s.salesperson_id=sp.id
        GROUP BY sp.id, sp.name ORDER BY sales DESC LIMIT 5""")).mappings().all()
    return {"count": len(rows), "ranking": [dict(x) for x in rows]}


def answer_for(intent: str, user: dict) -> tuple[str, dict, str]:
    with engine.connect() as conn:
        if intent == "liquidity":
            if user["role"] not in {"ceo", "finance"}:
                return "اطلاعات خزانه و نقدینگی فقط برای مدیرعامل و نقش مالی قابل مشاهده است. من می‌توانم فروش، تارگت و تسک‌های خودتان را تحلیل کنم.", {}, "high"
            x = liquidity_analysis(conn)
            state = "کسری" if x["available_30d"] < 0 else "مازاد"
            answer = f"برآورد ۳۰ روزه پس از ذخیره و تعهدات، {state} {money(abs(x['available_30d']))} است. موجودی نقد {money(x['cash'])}، دریافتنی مورد انتظار {money(x['receivable_30d'])} و پرداختنی باز {money(x['payable_30d'])} است."
            if x["available_30d"] < 0:
                actions: list[str] = []
                if x["receivable_30d"] > 0:
                    actions.append("وصول دریافتنی‌های سررسیددار را جلو بیندازید")
                if x["payable_30d"] > 0:
                    actions.append("پرداختنی‌های قابل‌مذاکره را جابه‌جا کنید")
                if not actions:
                    actions.append("فروش نقدی یا تأمین مالی کوتاه‌مدت را بررسی کنید")
                answer += " پیشنهاد: " + " و ".join(actions) + "؛ اجرای هر اقدام فقط بعد از تأیید شما انجام می‌شود."
            return answer, x, "medium"
        if intent == "debtors":
            if user["role"] not in MANAGEMENT_ROLES:
                return "فهرست بدهکاران شرکت برای نقش شما مجاز نیست. اگر تسک وصولی به شما واگذار شده باشد، آن را در بخش تسک‌ها می‌بینید.", {}, "high"
            x = debtor_analysis(conn)
            if not x["exists"]:
                return "هنوز تصویر مانده بدهکاران وارد نشده است؛ ابتدا فایل Excel بدهکاران را در خزانه‌داری وارد کنید.", x, "high"
            top = "، ".join(f"{r['counterparty']} با {money(r['balance'])}" for r in x["top"])
            return f"مانده بدهکاران {money(x['total'])} در {fa_number(x['count'])} ردیف است. بزرگ‌ترین مانده‌ها: {top}. پیشنهاد می‌کنم وصول از بزرگ‌ترین مانده‌ها شروع شود.", x, "high"
        if intent == "tasks":
            x = task_analysis(conn, user)
            return f"{fa_number(x['open'])} تسک باز دارید؛ {fa_number(x['overdue'])} مورد عقب‌افتاده است و میانگین پیشرفت تسک‌های باز {fa_number(x['average_progress'],1)}٪ است. اولویت با تسک‌های عقب‌افتاده و مالی است.", x, "high"
        if intent == "inventory":
            if user["role"] == "salesperson":
                return "نمای تجمیعی ارزش انبار برای نقش ویزیتور نمایش داده نمی‌شود. موجودی قابل فروش باید در نسخه بعد بر اساس مجوز کالا به شما نشان داده شود.", {}, "high"
            x = inventory_analysis(conn)
            low = "، ".join(str(r["name"]) for r in x["low_items"]) or "موردی نیست"
            return f"ارزش موجودی {money(x['value'])} در {fa_number(x['products'])} قلم است. تعداد اقلام کم‌موجود {fa_number(x['low_count'])} و شامل {low} است.", x, "high"
        if intent == "reports":
            x = report_analysis(conn, user)
            scope = "شما" if user["role"] == "salesperson" else "تیم"
            conversion = round(x["orders"] / x["visits"] * 100, 1) if x["visits"] else 0
            return f"در ۳۰ روز اخیر برای {scope}، {fa_number(x['reports'])} گزارش، {fa_number(x['visits'])} ویزیت و {fa_number(x['orders'])} سفارش ثبت شده است. نرخ تبدیل ویزیت به سفارش {fa_number(conversion,1)}٪ و سفارش‌های ازدست‌رفته {fa_number(x['lost'])} مورد است.", {**x, "conversion_percent": conversion}, "high"
        if intent == "team":
            if user["role"] == "salesperson":
                x = sales_overview(conn, user)
                return f"فروش ثبت‌شده خودتان {money(x['total_sales'])} در {fa_number(x['invoice_count'])} فاکتور است. اطلاعات سایر ویزیتورها برای حساب شما نمایش داده نمی‌شود.", x, "high"
            x = team_analysis(conn)
            ranking = "، ".join(f"{r['name']} ({money(r['sales'])})" for r in x["ranking"]) or "داده‌ای ثبت نشده"
            return f"رتبه‌بندی فروش فعلی: {ranking}.", x, "high"
        if intent == "forecast":
            x = sales_forecast(conn, user)
            return f"فروش این ماه تا امروز {money(x['current'])} است. با نرخ فعلی، پیش‌بینی پایان ماه حدود {money(x['forecast'])} است. چون پیش‌بینی بر اساس سابقه محدود و نرخ روزانه است، با ورود داده بیشتر دقیق‌تر می‌شود.", x, x["confidence"]
        if intent == "target":
            x = target_analysis(conn, user)
            if not x["exists"]:
                return "تارگت فعال متناسب با دسترسی شما پیدا نشد.", x, "high"
            return f"تحقق هدف «{x['title']}» برابر {fa_number(x['achievement'],1)}٪ است؛ فروش محقق‌شده {money(x['actual'])} و فاصله تا هدف {money(x['remaining'])} است.", x, "high"
        if intent == "overview":
            x = sales_overview(conn, user)
            target = target_analysis(conn, user)
            tasks = task_analysis(conn, user)
            return f"فروش این ماه {money(x['month_sales'])} در مجموع {fa_number(x['invoice_count'])} فاکتور ثبت‌شده است. تحقق تارگت فعال {fa_number(target['achievement'],1)}٪ و تعداد تسک باز {fa_number(tasks['open'])} مورد است.", {**x, "target": target, "tasks": tasks}, "high"
    return "می‌توانم درباره فروش و پیش‌بینی، تارگت، تسک‌ها، گزارش‌های شبانه، عملکرد تیم و—برای نقش مجاز—مطالبات و نقدینگی پاسخ بدهم. یکی از سؤال‌های پیشنهادی را انتخاب کنید.", {}, "high"


def suggestions_for(user: dict) -> list[str]:
    if user["role"] == "salesperson":
        return ["درصد تحقق تارگت من چقدر است؟", "تسک‌های من چه وضعیتی دارند؟", "تحلیل گزارش‌های شبانه من چیست؟", "فروش پایان ماه من چقدر می‌شود؟"]
    if user["role"] == "finance":
        return ["کسری نقدینگی ۳۰ روز آینده چقدر است؟", "مانده بدهکاران چقدر است؟", "وضعیت پرداختنی‌ها چیست؟", "خلاصه وضعیت شرکت را بگو"]
    return ["فروش پایان ماه چقدر می‌شود؟", "کدام بدهکاران را اول پیگیری کنیم؟", "کسری نقدینگی بعدی چقدر است؟", "عملکرد تیم فروش چطور است؟"]


@router.post("/chat")
def chat(data: ChatRequest, user: dict = Depends(current_user)):
    message = data.message.strip()
    intent = detect_intent(message)
    answer, metrics, confidence = answer_for(intent, user)
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO assistant_messages
            (user_id, role, content, intent, created_at)
            VALUES (:user_id, 'user', :content, :intent, NOW()),
                   (:user_id, 'assistant', :answer, :intent, NOW())"""),
            {"user_id": user["id"], "content": message, "answer": answer, "intent": intent})
    return {"answer": answer, "intent": intent, "metrics": metrics, "suggested_questions": suggestions_for(user), "mode": "local_analytics", "confidence": confidence}


@router.get("/history")
def history(limit: int = Query(default=30, ge=1, le=100), user: dict = Depends(current_user)):
    with engine.connect() as conn:
        rows = conn.execute(text("""SELECT id, role, content, intent, created_at FROM (
            SELECT id, role, content, intent, created_at FROM assistant_messages
            WHERE user_id=:user_id ORDER BY id DESC LIMIT :limit
        ) history ORDER BY id"""), {"user_id": user["id"], "limit": limit}).mappings().all()
    return {"messages": [dict(row) for row in rows], "suggested_questions": suggestions_for(user), "mode": "local_analytics"}


@router.delete("/history")
def clear_history(user: dict = Depends(current_user)):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM assistant_messages WHERE user_id=:user_id"), {"user_id": user["id"]})
    return {"status": "cleared"}
