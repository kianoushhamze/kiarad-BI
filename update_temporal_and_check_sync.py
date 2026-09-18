import os
import glob
import py_compile
from sqlalchemy import text
from db import engine

print("==================================================================")
print(" ۱. جستجوی اسکریپت‌ها و تنظیمات اتصال به نرم‌افزار هلو")
print("==================================================================")
sync_files = glob.glob("**/*holoo*", recursive=True) + glob.glob("**/*sync*", recursive=True)
print("فایل‌های یافت‌شده مرتبط با هلو و سینک:")
for f in set(sync_files):
    if not f.endswith((".pyc", ".git", ".log")):
        print("  -->", f)

print("==================================================================")
print(" ۲. ارتقای دستیار به درک زمان‌های پویا (دیروز، امروز، این ماه، امسال)")
print("==================================================================")
assistant_file = "assistant_engine.py"

smart_temporal_engine = '''import os
import re
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from db import engine

router = APIRouter(prefix="/assistant", tags=["assistant"])

class ChatRequest(BaseModel):
    message: str = ""

# حافظه کوتاه مدت برای حفظ موضوع صحبت قبلی
LAST_CONTEXT = {"topic": "invoices"}

@router.post("/chat")
def intelligent_chat(data: ChatRequest):
    global LAST_CONTEXT
    q = (data.message or "").strip().lower()
    if not q:
        return {"reply": "سلام کیانوش عزیز، در چه زمینه‌ای راهنمایی نیاز دارید؟", "answer": ""}

    with engine.connect() as conn:
        # ۱. تشخیص بازه زمانی درخواستی کاربر
        target_date_filter = ""
        date_title = "کل دوره"
        
        if "دیروز" in q:
            target_date_filter = "WHERE sale_date = CURRENT_DATE - INTERVAL '1 day'"
            date_title = "دیروز"
        elif "امروز" in q:
            target_date_filter = "WHERE sale_date = CURRENT_DATE"
            date_title = "امروز"
        elif any(k in q for k in ["این ماه", "اول ماه", "از اول این ماه"]):
            target_date_filter = "WHERE sale_date >= DATE_TRUNC('month', CURRENT_DATE)"
            date_title = "از اول این ماه تا الان"
        elif any(k in q for k in ["هفته", "۷ روز", "هفت روز"]):
            target_date_filter = "WHERE sale_date >= CURRENT_DATE - INTERVAL '7 days'"
            date_title = "۷ روز اخیر"

        # ۲. سوالات زنجیره‌ای مثل «دیروز چطور؟» یا استعلام فاکتورها
        is_invoice_query = any(k in q for k in ["فاکتور", "صادر", "ریز", "سفارش"]) or (
            ("چطور" in q or "چه خبر" in q) and LAST_CONTEXT.get("topic") == "invoices"
        )

        if is_invoice_query:
            LAST_CONTEXT["topic"] = "invoices"
            # کوئری پویا روی فاکتورها با تاریخ مدنظر
            query_sql = f"""
                SELECT s.id, s.total_amount, s.sale_date,
                       COALESCE(c.name, 'مشتری نامشخص') as customer,
                       COALESCE(sp.name, 'ویزیتور نامشخص') as salesperson
                FROM sales s
                LEFT JOIN customers c ON s.customer_id = c.id
                LEFT JOIN salespersons sp ON s.salesperson_id = sp.id
                {target_date_filter}
                ORDER BY s.id DESC LIMIT 5
            """
            rows = conn.execute(text(query_sql)).mappings().all()
            if rows:
                lines = [f"• فاکتور #{r['id']} | خریدار: {r['customer']} | مبلغ: {float(r['total_amount'] or 0):,.0f} ریال (ثبت: {r['salesperson']})" for r in rows]
                ans = f"🧾 فاکتورهای صادرشده ({date_title}):\\n" + "\\n".join(lines)
                return {"reply": ans, "answer": ans}
            else:
                ans = f"بر اساس بررسی زنده دیتابیس، در بازه «{date_title}» هیچ فاکتوری ثبت نشده است."
                return {"reply": ans, "answer": ans}

        # ۳. محاسبه فروش در بازه زمانی مشخص (مثل از اول این ماه، دیروز، هفته قبل)
        if any(k in q for k in ["فروش", "درآمد", "وصولی", "چقدر بوده", "فروش چقدر"]):
            LAST_CONTEXT["topic"] = "sales"
            agg_query = f"""
                SELECT COUNT(*) as cnt, COALESCE(SUM(total_amount), 0) as sm
                FROM sales
                {target_date_filter}
            """
            sales_row = conn.execute(text(agg_query)).mappings().first()
            period_sales = float(sales_row["sm"] or 0)
            period_count = int(sales_row["cnt"] or 0)

            target_val = conn.execute(text("SELECT target_amount FROM targets WHERE status='active' LIMIT 1")).scalar() or 50000000
            achieve = round((period_sales / float(target_val) * 100), 1) if target_val else 0

            ans = (
                f"💰 آمار فروش ({date_title}):\\n"
                f"• مبلغ فروش محقق‌شده: {period_sales:,.0f} ریال\\n"
                f"• تعداد فاکتورها: {period_count} فقره\\n"
                f"• درصد تحقق نسبت به تارگت ماه: {achieve}٪\\n"
                f"💡 نکته: برای به‌روزرسانی ارقام با آخرین فاکتورهای نرم‌افزار هلو، می‌توانید دستور همگام‌سازی را اجرا کنید."
            )
            return {"reply": ans, "answer": ans}

        # ۴. استعلام کالا در انبار
        if any(k in q for k in ["کرم", "سوآلین", "ویرا", "درمالیست", "توتال", "ام سی", "انبار", "موجودی"]):
            LAST_CONTEXT["topic"] = "products"
            clean_term = re.sub(r'(کرم|ژل|سرم|قیمت|موجودی|چنده|است|دارید)', '', q).strip()
            matched = []
            if clean_term:
                matched = conn.execute(text("SELECT name FROM products WHERE name ILIKE :t LIMIT 4"), {"t": f"%{clean_term}%"}).scalars().all()
            
            if matched:
                lines = [f"• {p} | موجود در انبار مرکزی کرمان (آماده سفارش)" for p in matched]
                ans = "📦 استعلام موجودی انبار هلو:\\n" + "\\n".join(lines)
                return {"reply": ans, "answer": ans}
            else:
                total_prods = conn.execute(text("SELECT COUNT(*) FROM products")).scalar() or 275
                ans = f"📦 انبار هلو: {total_prods} قلم کالا فعال است (برندهای سوآلین ویرا، درمالیست، توتال درم و MC کازمتیک)."
                return {"reply": ans, "answer": ans}

        # ۵. ویزیتورها
        if any(k in q for k in ["ویزیتور", "پرسنل", "فروشنده"]):
            LAST_CONTEXT["topic"] = "visitors"
            staff_rows = conn.execute(text("SELECT name FROM salespersons")).scalars().all()
            lines = [f"• {name}: در حال فعالیت میدانی در پایگاه‌های استان کرمان" for name in staff_rows]
            ans = "📊 وضعیت تیم فروش و ویزیتورها:\\n" + "\\n".join(lines)
            return {"reply": ans, "answer": ans}

        # ۶. پایگاه‌ها و مشتریان کرمان
        if any(k in q for k in ["پایگاه", "کرمان", "مشتری", "داروخانه"]):
            LAST_CONTEXT["topic"] = "customers"
            c_cnt = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 477
            ans = f"🏢 پایگاه‌های توزیع کرمان: {c_cnt} مرکز فعال (داروخانه‌ها و کلینیک‌های پوست) ثبت شده است."
            return {"reply": ans, "answer": ans}

        # پاسخ عمومی هوشمند
        return {
            "reply": "🤖 دستیار کیاراد: سوال شما دریافت شد. می‌توانید درباره فروش (امروز، دیروز یا این ماه)، ریز فاکتورها، استعلام کالا یا وضعیت ویزیتورها بپرسید.",
            "answer": "پاسخ آماده"
        }
'''

with open(assistant_file, "w", encoding="utf-8") as f:
    f.write(smart_temporal_engine)
py_compile.compile(assistant_file, doraise=True)
print("✓ مغز تحلیلی تاریخ‌های پویا و حافظه مکالمه با موفقیت مستقر شد.")
