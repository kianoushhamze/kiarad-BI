"""Role-aware, deterministic business assistant for Kiarad BI.

The assistant only uses a fixed catalogue of read-only SQL analyses. Company
information is never sent to an external AI service and free text is never
converted to SQL. Natural-language parsing only selects predefined analyses
and response styles.
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
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = value.replace("ۀ", "ه").replace("ة", "ه")
    return re.sub(r"\s+", " ", value).strip().lower()


def has_any(value: str, words: tuple[str, ...]) -> bool:
    return any(word in value for word in words)


def detect_intent(message: str) -> str:
    """Map free text to a safe, predefined analysis family.

    Ordering matters: specific intents are checked before generic sales/overview.
    """
    value = normalize(message)
    catalog = [
        ("liquidity", ("نقدینگی", "کسری", "چک", "پرداختنی", "خزانه", "تعهد مالی", "پول کم")),
        ("debtors", ("بدهکار", "مطالبات", "وصول", "طلب", "مانده مشتری", "مشتری را پیگیری")),
        ("tasks", ("تسک", "کارهای من", "وظیفه", "کار عقب", "عقب افتاده", "عقب‌افتاده")),
        ("reports", ("گزارش شب", "گزارش کار", "ویزیت", "رقیب", "سفارش از دست", "نرخ تبدیل")),
        ("inventory", ("موجودی کالا", "موجودی انبار", "انبار", "کم موجود", "کم‌موجود", "کالا", "محصول")),
        ("team", ("ویزیتور", "فروشنده", "تیم", "عملکرد کارکنان", "بهترین فروشنده", "ضعیف ترین فروشنده", "ضعیف‌ترین فروشنده")),
        ("forecast", ("پیش بینی فروش", "پیش‌بینی فروش", "پایان ماه", "فروش آینده", "روند فروش", "تا آخر ماه")),
        ("target", ("تارگت", "هدف فروش", "درصد تحقق", "تحقق هدف", "فاصله تا هدف", "برای رسیدن به هدف")),
        ("sales", ("فروش", "فاکتور", "درآمد")),
        ("overview", ("وضعیت", "خلاصه", "داشبورد", "اوضاع شرکت", "اوضاع کسب")),
        ("help", ("چه سوال", "چه سؤال", "راهنما", "کمک", "چه کاری", "چی بلدی")),
    ]
    for intent, words in catalog:
        if has_any(value, words):
            return intent
    return "help"


def detect_question_mode(message: str) -> str:
    """Detect what the user wants *about* an intent, not just the topic."""
    value = normalize(message)
    if has_any(value, ("چرا", "علت", "دلیل", "افت", "کم شده", "ضعیف")):
        return "explain"
    if has_any(value, ("چه کار", "چیکار", "پیشنهاد", "راهکار", "بهتره", "اولویت", "پیگیری کنیم")):
        return "recommend"
    if has_any(value, ("مقایسه", "نسبت به", "فرق", "بیشتر", "کمتر", "رشد", "کاهش")):
        return "compare"
    if has_any(value, ("روزی چقدر", "روزانه چقدر", "چقدر باید", "چقدر لازمه", "فاصله تا")):
        return "pace"
    if has_any(value, ("کدام", "کدوم", "چه کسی", "بهترین", "بیشترین", "کمترین", "اول")):
        return "rank"
    if has_any(value, ("چقدر", "چند", "مبلغ", "تعداد", "درصد")):
        return "amount"
    return "status"


def detect_period(message: str) -> str:
    value = normalize(message)
    if "دیروز" in value:
        return "yesterday"
    if "امروز" in value:
        return "today"
    if has_any(value, ("این هفته", "هفته جاری", "هفته اخیر")):
        return "week"
    if has_any(value, ("۳۰ روز", "30 روز", "ماه اخیر", "یک ماه اخیر")):
        return "30d"
    return "month"


def scalar(conn, sql: str, params: dict | None = None) -> float:
    return float(conn.execute(text(sql), params or {}).scalar() or 0)


def sales_scope(user: dict, prefix: str = "") -> tuple[str, dict]:
    col = f"{prefix}salesperson_id" if prefix else "salesperson_id"
    if user["role"] == "salesperson":
        return f" AND {col}=:salesperson_id", {"salesperson_id": user["salesperson_id"] or -1}
    return "", {}


def sales_period_analysis(conn, user: dict, period: str) -> dict[str, Any]:
    clause, params = sales_scope(user)
    periods = {
        "today": ("CAST(date AS DATE) = CURRENT_DATE", "CAST(date AS DATE) = CURRENT_DATE - 1", "امروز", "دیروز"),
        "yesterday": ("CAST(date AS DATE) = CURRENT_DATE - 1", "CAST(date AS DATE) = CURRENT_DATE - 2", "دیروز", "روز قبل"),
        "week": ("date >= date_trunc('week', CURRENT_DATE)", "date >= date_trunc('week', CURRENT_DATE) - interval '7 days' AND date < date_trunc('week', CURRENT_DATE)", "این هفته", "هفته قبل"),
        "30d": ("date >= CURRENT_DATE - interval '29 days'", "date >= CURRENT_DATE - interval '59 days' AND date < CURRENT_DATE - interval '29 days'", "۳۰ روز اخیر", "۳۰ روز قبل از آن"),
        "month": ("date >= date_trunc('month', CURRENT_DATE)", "date >= date_trunc('month', CURRENT_DATE) - interval '1 month' AND date < date_trunc('month', CURRENT_DATE)", "این ماه", "ماه قبل"),
    }
    current_where, previous_where, label, previous_label = periods.get(period, periods["month"])
    row = conn.execute(text(f"""SELECT COUNT(*) AS invoices, COALESCE(SUM(total_amount),0) AS amount
        FROM sales WHERE {current_where} {clause}"""), params).mappings().first()
    previous = conn.execute(text(f"""SELECT COUNT(*) AS invoices, COALESCE(SUM(total_amount),0) AS amount
        FROM sales WHERE {previous_where} {clause}"""), params).mappings().first()
    amount = float(row["amount"] or 0)
    previous_amount = float(previous["amount"] or 0)
    change = ((amount - previous_amount) / previous_amount * 100) if previous_amount else None
    return {
        "period": period,
        "label": label,
        "previous_label": previous_label,
        "amount": amount,
        "invoices": int(row["invoices"] or 0),
        "previous_amount": previous_amount,
        "previous_invoices": int(previous["invoices"] or 0),
        "change_percent": round(change, 1) if change is not None else None,
    }


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
        return {"exists": False, "target": 0, "actual": 0, "achievement": 0, "remaining": 0, "daily_required": 0}
    sale_params = {"start": row["start_date"], "end": row["end_date"]}
    person_clause = ""
    if row["salesperson_id"] is not None:
        person_clause = " AND salesperson_id=:salesperson_id"
        sale_params["salesperson_id"] = row["salesperson_id"]
    actual = scalar(conn, f"""SELECT COALESCE(SUM(total_amount),0) FROM sales
        WHERE CAST(date AS DATE) BETWEEN :start AND :end {person_clause}""", sale_params)
    target = float(row["target_amount"] or 0)
    remaining = max(target - actual, 0)
    end_date = row["end_date"]
    days_left = max((end_date - date.today()).days + 1, 0) if end_date else 0
    daily_required = remaining / days_left if days_left else remaining
    return {
        "exists": True, "title": row["title"], "target": target, "actual": actual,
        "achievement": round(actual / target * 100, 1) if target else 0,
        "remaining": remaining, "days_left": days_left, "daily_required": daily_required,
        "end_date": end_date,
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
        "days_in_month": days_in_month, "confidence": "medium" if len(completed) >= 2 else "low",
        "baseline": round(baseline), "run_rate": round(run_rate),
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
    overdue = conn.execute(text(f"""SELECT title, priority, due_date, progress FROM tasks
        WHERE {where} AND status <> 'completed' AND due_date < NOW()
        ORDER BY due_date ASC NULLS LAST LIMIT 5"""), params).mappings().all()
    return {
        "open": int(row["open_count"] or 0), "overdue": int(row["overdue_count"] or 0),
        "average_progress": round(float(row["avg_progress"] or 0), 1),
        "overdue_items": [dict(x) for x in overdue],
    }


def debtor_analysis(conn) -> dict[str, Any]:
    snapshot = conn.execute(text("""SELECT id, total_amount, row_count, snapshot_date
        FROM receivable_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1""")).mappings().first()
    if not snapshot:
        return {"exists": False, "total": 0, "count": 0, "top": []}
    top = conn.execute(text("""SELECT counterparty, balance FROM receivable_balances
        WHERE snapshot_id=:id ORDER BY balance DESC LIMIT 5"""), {"id": snapshot["id"]}).mappings().all()
    return {
        "exists": True, "total": float(snapshot["total_amount"] or 0),
        "count": int(snapshot["row_count"] or 0), "top": [dict(x) for x in top],
        "snapshot_date": snapshot["snapshot_date"],
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
    rows = conn.execute(text("""SELECT sp.name, COALESCE(SUM(s.total_amount),0) AS sales, COUNT(s.id) AS invoices
        FROM salespersons sp LEFT JOIN sales s ON s.salesperson_id=sp.id
        GROUP BY sp.id, sp.name ORDER BY sales DESC""")).mappings().all()
    return {"count": len(rows), "ranking": [dict(x) for x in rows]}


def sales_answer(conn, user: dict, message: str, mode: str) -> tuple[str, dict, str]:
    period = detect_period(message)
    x = sales_period_analysis(conn, user, period)
    base = f"فروش {x['label']} {money(x['amount'])} در {fa_number(x['invoices'])} فاکتور است."

    if mode in {"compare", "explain"}:
        if x["change_percent"] is None:
            comparison = f"برای {x['previous_label']} فروش قابل‌مقایسه‌ای ثبت نشده؛ بنابراین درصد تغییر قابل اتکا نیست."
        else:
            direction = "رشد" if x["change_percent"] >= 0 else "کاهش"
            comparison = f"نسبت به {x['previous_label']} با فروش {money(x['previous_amount'])}، {fa_number(abs(x['change_percent']),1)}٪ {direction} دیده می‌شود."
        if mode == "explain":
            return base + " " + comparison + " این داده فقط وجود افت یا رشد را نشان می‌دهد؛ برای گفتن علت واقعی باید جزئیات مشتری، محصول و گزارش ویزیت‌ها را هم بررسی کنیم.", x, "medium"
        return base + " " + comparison, x, "high"

    if mode == "recommend":
        target = target_analysis(conn, user)
        if target["exists"] and target["remaining"] > 0:
            return base + f" برای رسیدن به تارگت فعال {money(target['remaining'])} باقی مانده و با {fa_number(target['days_left'])} روز باقی‌مانده، میانگین فروش لازم حدود {money(target['daily_required'])} در روز است.", {**x, "target": target}, "high"
        return base + " تارگت فعالِ دارای فاصله پیدا نشد؛ برای پیشنهاد اجرایی دقیق‌تر می‌توانم مشتریان غیرفعال، عملکرد تیم یا گزارش‌های ویزیت را بررسی کنم.", x, "medium"

    return base, x, "high"


def answer_for(intent: str, message: str, user: dict) -> tuple[str, dict, str]:
    mode = detect_question_mode(message)
    with engine.connect() as conn:
        if intent == "sales":
            return sales_answer(conn, user, message, mode)

        if intent == "liquidity":
            if user["role"] not in {"ceo", "finance"}:
                return "اطلاعات خزانه و نقدینگی فقط برای مدیرعامل و نقش مالی قابل مشاهده است. من می‌توانم فروش، تارگت و تسک‌های خودتان را تحلیل کنم.", {}, "high"
            x = liquidity_analysis(conn)
            state = "کسری" if x["available_30d"] < 0 else "مازاد"
            base = f"برآورد ۳۰ روزه پس از ذخیره و تعهدات، {state} {money(abs(x['available_30d']))} است. موجودی نقد {money(x['cash'])}، دریافتنی مورد انتظار {money(x['receivable_30d'])} و پرداختنی باز {money(x['payable_30d'])} است."
            if mode == "rank" and x["next_payable"]:
                p = x["next_payable"]
                return base + f" نزدیک‌ترین پرداخت باز مربوط به {p['counterparty']} به مبلغ {money(p['amount'])} و سررسید {p['due_date']} است.", x, "high"
            if x["available_30d"] < 0 and mode in {"recommend", "status", "explain"}:
                actions = []
                if x["receivable_30d"] > 0:
                    actions.append("وصول دریافتنی‌های نزدیک‌سررسید را جلو بیندازید")
                if x["payable_30d"] > 0:
                    actions.append("برای پرداخت‌های قابل‌مذاکره جابه‌جایی سررسید بگیرید")
                if not actions:
                    actions.append("برای افزایش فروش نقدی یا تأمین مالی کوتاه‌مدت برنامه بگذارید")
                return base + " پیشنهاد: " + " و ".join(actions) + "؛ اجرای اقدام فقط بعد از تأیید مدیر انجام می‌شود.", x, "medium"
            return base, x, "high"

        if intent == "debtors":
            if user["role"] not in MANAGEMENT_ROLES:
                return "فهرست بدهکاران شرکت برای نقش شما مجاز نیست. اگر تسک وصولی به شما واگذار شده باشد، آن را در بخش تسک‌ها می‌بینید.", {}, "high"
            x = debtor_analysis(conn)
            if not x["exists"]:
                return "هنوز تصویر مانده بدهکاران وارد نشده است؛ ابتدا فایل Excel بدهکاران را در خزانه‌داری وارد کنید.", x, "high"
            top = "، ".join(f"{r['counterparty']} ({money(r['balance'])})" for r in x["top"])
            if mode in {"rank", "recommend"}:
                return f"برای پیگیری وصول، اولویت فعلی بر اساس بزرگی مانده: {top}. مجموع مانده بدهکاران {money(x['total'])} است. این اولویت‌بندی فقط بر مبنای مبلغ مانده است، نه احتمال وصول یا سابقه مشتری.", x, "high"
            return f"مانده بدهکاران {money(x['total'])} در {fa_number(x['count'])} ردیف است. بزرگ‌ترین مانده‌ها: {top}.", x, "high"

        if intent == "tasks":
            x = task_analysis(conn, user)
            if mode in {"rank", "recommend"} and x["overdue_items"]:
                items = "، ".join(str(item["title"]) for item in x["overdue_items"][:3])
                return f"{fa_number(x['open'])} تسک باز و {fa_number(x['overdue'])} تسک عقب‌افتاده دارید. اولویت شروع: {items}. میانگین پیشرفت تسک‌های باز {fa_number(x['average_progress'],1)}٪ است.", x, "high"
            return f"{fa_number(x['open'])} تسک باز دارید؛ {fa_number(x['overdue'])} مورد عقب‌افتاده است و میانگین پیشرفت تسک‌های باز {fa_number(x['average_progress'],1)}٪ است.", x, "high"

        if intent == "inventory":
            if user["role"] == "salesperson":
                return "نمای تجمیعی ارزش انبار برای نقش ویزیتور نمایش داده نمی‌شود. موجودی قابل فروش باید در نسخه بعد بر اساس مجوز کالا به شما نشان داده شود.", {}, "high"
            x = inventory_analysis(conn)
            low = "، ".join(f"{r['name']} ({fa_number(r['stock'])})" for r in x["low_items"]) or "موردی نیست"
            if mode in {"rank", "recommend"}:
                return f"{fa_number(x['low_count'])} قلم کم‌موجود است. اقلامی که باید زودتر بررسی شوند: {low}. ارزش کل موجودی {money(x['value'])} است.", x, "high"
            return f"ارزش موجودی {money(x['value'])} در {fa_number(x['products'])} قلم است. تعداد اقلام کم‌موجود {fa_number(x['low_count'])} و شامل {low} است.", x, "high"

        if intent == "reports":
            x = report_analysis(conn, user)
            scope = "شما" if user["role"] == "salesperson" else "تیم"
            conversion = round(x["orders"] / x["visits"] * 100, 1) if x["visits"] else 0
            result = {**x, "conversion_percent": conversion}
            if mode in {"explain", "recommend"}:
                if x["visits"] == 0:
                    insight = "ویزیتی ثبت نشده؛ قبل از تحلیل عملکرد باید گزارش‌های روزانه کامل شوند."
                elif conversion < 20:
                    insight = "نرخ تبدیل پایین است؛ بررسی علت‌های سفارش ازدست‌رفته، قیمت، رقبا و کیفیت پیگیری فروش منطقی‌ترین قدم بعدی است."
                else:
                    insight = "نرخ تبدیل فعلی قابل‌قبول‌تر است؛ برای یافتن گلوگاه بعدی باید سفارش‌های ازدست‌رفته و مبلغ فروش هر ویزیت را بررسی کنیم."
                return f"در ۳۰ روز اخیر برای {scope}، {fa_number(x['visits'])} ویزیت و {fa_number(x['orders'])} سفارش ثبت شده و نرخ تبدیل {fa_number(conversion,1)}٪ است. {insight}", result, "medium"
            return f"در ۳۰ روز اخیر برای {scope}، {fa_number(x['reports'])} گزارش، {fa_number(x['visits'])} ویزیت و {fa_number(x['orders'])} سفارش ثبت شده است. نرخ تبدیل ویزیت به سفارش {fa_number(conversion,1)}٪ و سفارش‌های ازدست‌رفته {fa_number(x['lost'])} مورد است.", result, "high"

        if intent == "team":
            if user["role"] == "salesperson":
                x = sales_overview(conn, user)
                return f"فروش ثبت‌شده خودتان {money(x['total_sales'])} در {fa_number(x['invoice_count'])} فاکتور است. اطلاعات سایر ویزیتورها برای حساب شما نمایش داده نمی‌شود.", x, "high"
            x = team_analysis(conn)
            if not x["ranking"]:
                return "برای تیم فروش هنوز داده‌ای ثبت نشده است.", x, "high"
            if mode == "rank":
                value = normalize(message)
                chosen = x["ranking"][-1] if has_any(value, ("ضعیف", "کمترین", "آخر")) else x["ranking"][0]
                label = "کمترین فروش ثبت‌شده" if chosen is x["ranking"][-1] else "بیشترین فروش ثبت‌شده"
                return f"{label} مربوط به {chosen['name']} با {money(chosen['sales'])} در {fa_number(chosen['invoices'])} فاکتور است.", x, "high"
            ranking = "، ".join(f"{r['name']} ({money(r['sales'])})" for r in x["ranking"][:5])
            return f"رتبه‌بندی فروش فعلی: {ranking}.", x, "high"

        if intent == "forecast":
            x = sales_forecast(conn, user)
            if mode == "explain":
                return f"فروش این ماه تا امروز {money(x['current'])} است و پیش‌بینی پایان ماه حدود {money(x['forecast'])}. این عدد از ترکیب نرخ فروش روزانه فعلی و میانگین ماه‌های کامل اخیر ساخته می‌شود؛ بنابراین با سابقه محدود، قطعیت آن {('متوسط' if x['confidence']=='medium' else 'پایین')} است.", x, x["confidence"]
            return f"فروش این ماه تا امروز {money(x['current'])} است. با نرخ فعلی، پیش‌بینی پایان ماه حدود {money(x['forecast'])} است. سطح اطمینان این برآورد {('متوسط' if x['confidence']=='medium' else 'پایین')} است.", x, x["confidence"]

        if intent == "target":
            x = target_analysis(conn, user)
            if not x["exists"]:
                return "تارگت فعال متناسب با دسترسی شما پیدا نشد.", x, "high"
            if mode in {"pace", "recommend"}:
                if x["remaining"] <= 0:
                    return f"هدف «{x['title']}» کامل محقق شده است؛ تحقق فعلی {fa_number(x['achievement'],1)}٪ است.", x, "high"
                if x["days_left"] <= 0:
                    return f"برای هدف «{x['title']}» هنوز {money(x['remaining'])} فاصله وجود دارد، اما بازه هدف به پایان رسیده است؛ باید تارگت جدید تعریف یا وضعیت این هدف تعیین تکلیف شود.", x, "high"
                return f"برای رسیدن به هدف «{x['title']}» {money(x['remaining'])} باقی مانده است. با {fa_number(x['days_left'])} روز باقی‌مانده، میانگین فروش موردنیاز حدود {money(x['daily_required'])} در روز است.", x, "high"
            return f"تحقق هدف «{x['title']}» برابر {fa_number(x['achievement'],1)}٪ است؛ فروش محقق‌شده {money(x['actual'])} و فاصله تا هدف {money(x['remaining'])} است.", x, "high"

        if intent == "overview":
            sales = sales_period_analysis(conn, user, "month")
            target = target_analysis(conn, user)
            tasks = task_analysis(conn, user)
            parts = [f"فروش این ماه {money(sales['amount'])} در {fa_number(sales['invoices'])} فاکتور است."]
            if target["exists"]:
                parts.append(f"تحقق تارگت فعال {fa_number(target['achievement'],1)}٪ است.")
            parts.append(f"{fa_number(tasks['open'])} تسک باز و {fa_number(tasks['overdue'])} تسک عقب‌افتاده ثبت شده است.")
            if user["role"] in {"ceo", "finance"}:
                liquidity = liquidity_analysis(conn)
                state = "کسری" if liquidity["available_30d"] < 0 else "مازاد"
                parts.append(f"برآورد نقدینگی ۳۰ روزه {state} {money(abs(liquidity['available_30d']))} است.")
                return " ".join(parts), {"sales": sales, "target": target, "tasks": tasks, "liquidity": liquidity}, "high"
            return " ".join(parts), {"sales": sales, "target": target, "tasks": tasks}, "high"

    return "می‌توانم درباره فروش، مقایسه دوره‌ها، پیش‌بینی، تارگت، تسک‌ها، گزارش‌های شبانه، عملکرد تیم و—برای نقش مجاز—مطالبات و نقدینگی پاسخ بدهم. سؤال را با جزئیات بپرسید؛ مثلاً «فروش این ماه نسبت به ماه قبل چطور بوده؟»", {}, "high"


def suggestions_for(user: dict) -> list[str]:
    if user["role"] == "salesperson":
        return [
            "فروش این ماه من نسبت به ماه قبل چطور بوده؟",
            "برای رسیدن به تارگت روزی چقدر باید بفروشم؟",
            "کدام تسک‌های من عقب افتاده‌اند؟",
            "چرا نرخ تبدیل ویزیت‌های من پایین است؟",
        ]
    if user["role"] == "finance":
        return [
            "کسری نقدینگی ۳۰ روز آینده چقدر است و چه کار کنیم؟",
            "کدام بدهکاران را اول پیگیری کنیم؟",
            "نزدیک‌ترین پرداخت باز کدام است؟",
            "خلاصه وضعیت شرکت را بگو",
        ]
    return [
        "فروش این ماه نسبت به ماه قبل چطور بوده؟",
        "برای رسیدن به تارگت روزی چقدر باید بفروشیم؟",
        "کدام بدهکاران را اول پیگیری کنیم؟",
        "عملکرد تیم فروش چطور است؟",
    ]


@router.post("/chat")
def chat(data: ChatRequest, user: dict = Depends(current_user)):
    message = data.message.strip()
    intent = detect_intent(message)
    mode = detect_question_mode(message)
    answer, metrics, confidence = answer_for(intent, message, user)
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO assistant_messages
            (user_id, role, content, intent, created_at)
            VALUES (:user_id, 'user', :content, :intent, NOW()),
                   (:user_id, 'assistant', :answer, :intent, NOW())"""),
            {"user_id": user["id"], "content": message, "answer": answer, "intent": intent})
    return {
        "answer": answer,
        "intent": intent,
        "question_mode": mode,
        "metrics": metrics,
        "suggested_questions": suggestions_for(user),
        "mode": "local_analytics_v2",
        "confidence": confidence,
    }


@router.get("/history")
def history(limit: int = Query(default=30, ge=1, le=100), user: dict = Depends(current_user)):
    with engine.connect() as conn:
        rows = conn.execute(text("""SELECT id, role, content, intent, created_at FROM (
            SELECT id, role, content, intent, created_at FROM assistant_messages
            WHERE user_id=:user_id ORDER BY id DESC LIMIT :limit
        ) history ORDER BY id"""), {"user_id": user["id"], "limit": limit}).mappings().all()
    return {"messages": [dict(row) for row in rows], "suggested_questions": suggestions_for(user), "mode": "local_analytics_v2"}


@router.delete("/history")
def clear_history(user: dict = Depends(current_user)):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM assistant_messages WHERE user_id=:user_id"), {"user_id": user["id"]})
    return {"status": "cleared"}
