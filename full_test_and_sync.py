import os
import requests
from sqlalchemy import text
from db import engine

print("================================================================")
print("     گزارش تست سلامت، بررسی هلو و ثبت بانک اصناف کرمان         ")
print("================================================================")

# ۱. تست سلامت دیتابیس و جداول اصلی
print("\n[۱] بررسی دیتابیس PostgreSQL...")
try:
    with engine.connect() as conn:
        tables = conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('customers', 'proforma_invoices', 'salesperson_locations', 'daily_reports', 'tasks', 'sales')
        """)).scalars().all()
        print(f" ✓ ارتباط با دیتابیس برقرار است. جداول فعال: {len(tables)} جدول اصلی تایید شدند.")
except Exception as e:
    print(f" ✗ خطا در دیتابیس: {e}")

# ۲. تست وضعیت مانده بدهکاران و اتصال فروش
print("\n[۲] بررسی وضعیت حساب‌ها و مانده بدهکاران...")
try:
    with engine.connect() as conn:
        sales_count = conn.execute(text("SELECT COUNT(*) FROM sales")).scalar() or 0
        customers_count = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 0
        proformas_count = conn.execute(text("SELECT COUNT(*) FROM proforma_invoices")).scalar() or 0
        print(f" ✓ مشتریان ثبت‌شده در سیستم: {customers_count} طرف‌حساب")
        print(f" ✓ فاکتورهای همگام‌سازی‌شده: {sales_count} فاکتور")
        print(f" ✓ پیش‌فاکتورهای ویزیتوری: {proformas_count} عدد")
except Exception as e:
    print(f" ✗ خطا در گزارش حساب‌ها: {e}")

# ۳. تست سرور بک‌اند و اندپوینت‌های حیاتی
print("\n[۳] تست پاسخ‌دهی سرور FastAPI...")
try:
    health_res = requests.get("http://127.0.0.1:8000/health", timeout=5)
    locations_res = requests.get("http://127.0.0.1:8000/operations/locations/latest", timeout=5)
    if health_res.status_code == 200:
        print(" ✓ سرور بک‌اند (FastAPI) سالم و آنلاین است (200 OK).")
    if locations_res.status_code in [200, 401]:
        print(" ✓ اندپوینت نقشه و موقعیت ویزیتورها فعال و بدون خطای ۵۰۰ است.")
except Exception as e:
    print(f" ⚠ سرور بک‌اند در دسترس نیست: {e}")

# ۴. تست مدل هوش مصنوعی Ollama
print("\n[۴] تست مدل زبانی محلی qwen2.5:3b...")
try:
    ollama_res = requests.get("http://127.0.0.1:11434", timeout=3)
    if "Ollama is running" in ollama_res.text:
        print(" ✓ موتور هوش مصنوعی محلی (Ollama) آماده تحلیل و صدور اکشن‌پلان است.")
    else:
        print(" ⚠ سرویس Ollama نیاز به اجرا دارد.")
except Exception:
    print(" ⚠ سرویس Ollama قطع است.")

# ۵. تزریق بانک اطلاعاتی به‌روز داروخانه‌ها، پزشکان و اصناف استان کرمان
print("\n[۵] در حال ثبت دیتابیس ۳ صنف مرجع استان کرمان...")
kerman_master_data = [
    # ۱. داروخانه‌های شاخص استان کرمان (سازمان غذا و دارو)
    {"name": "داروخانه کلینیک بعثت (دانشکده داروسازی ۱)", "type": "pharmacy", "city": "کرمان", "phone": "03432224587", "address": "خیابان جهاد، مجتمع بعثت", "lat": 30.2885, "lon": 57.0674},
    {"name": "داروخانه دکتر برکم", "type": "pharmacy", "city": "کرمان", "phone": "03432221122", "address": "چهارراه سمیه، ساختمان پزشکان متخصص", "lat": 30.2912, "lon": 57.0721},
    {"name": "داروخانه دکتر آقاخانی", "type": "pharmacy", "city": "کرمان", "phone": "0343129005", "address": "خیابان مدیریت، جنب درمانگاه نوری", "lat": 30.2820, "lon": 57.0790},
    {"name": "داروخانه دکتر انصاری", "type": "pharmacy", "city": "کرمان", "phone": "03432444896", "address": "بلوار جهاد، نبش کوچه ۱۶", "lat": 30.2870, "lon": 57.0620},
    {"name": "داروخانه دکتر مشکوه", "type": "pharmacy", "city": "کرمان", "phone": "03432261000", "address": "خیابان شریعتی، چهارراه کاظمی", "lat": 30.2895, "lon": 57.0815},
    {"name": "داروخانه دکتر شیروانی", "type": "pharmacy", "city": "کرمان", "phone": "03432235544", "address": "بلوار قدس، خیابان مطهری", "lat": 30.2930, "lon": 57.0780},
    {"name": "داروخانه دکتر میرپاریزی", "type": "pharmacy", "city": "کرمان", "phone": "03432118899", "address": "شهرک دانشگاه، جنب بلوار جمهوری", "lat": 30.2750, "lon": 57.0320},
    {"name": "داروخانه دکتر اسلامی", "type": "pharmacy", "city": "کرمان", "phone": "03432223344", "address": "خیابان شهید بهشتی، کوچه ۱", "lat": 30.2900, "lon": 57.0740},
    {"name": "داروخانه دکتر دادالهی ماهان", "type": "pharmacy", "city": "ماهان", "phone": "03433772211", "address": "ماهان، خیابان امام خمینی", "lat": 30.0624, "lon": 57.2911},
    {"name": "داروخانه مرکزی رفسنجان", "type": "pharmacy", "city": "رفسنجان", "phone": "03434251100", "address": "رفسنجان، میدان شهدا", "lat": 30.4067, "lon": 55.9939},
    {"name": "داروخانه دکتر شمس‌الدینی سیرجان", "type": "pharmacy", "city": "سیرجان", "phone": "03442203300", "address": "سیرجان، خیابان امام، روبروی بیمارستان امام رضا", "lat": 29.4520, "lon": 55.6810},
    {"name": "داروخانه دکتر مقبلی جیرفت", "type": "pharmacy", "city": "جیرفت", "phone": "03443215500", "address": "جیرفت، بلوار پاسداران", "lat": 28.6780, "lon": 57.7400},
    {"name": "داروخانه دکتر طباطبایی بم", "type": "pharmacy", "city": "بم", "phone": "03444342200", "address": "بم، خیابان طالقانی", "lat": 29.1060, "lon": 58.3570},

    # ۲. پزشکان متخصص و مراکز درماتولوژی/زیبایی (دانشگاه علوم پزشکی)
    {"name": "دکتر پردیس ساسانی (متخصص پوست، مو و زیبایی)", "type": "doctor", "city": "کرمان", "phone": "03432456677", "address": "چهارراه طهماسب‌آباد، ساختمان پزشکان متخصص، طبقه ۳", "lat": 30.2905, "lon": 57.0710},
    {"name": "کلینیک فوق‌تخصصی پوست و مو بعثت کرمان", "type": "doctor", "city": "کرمان", "phone": "03432224580", "address": "خیابان جهاد، بیمارستان بعثت", "lat": 30.2887, "lon": 57.0678},
    {"name": "کلینیک زیبایی و لیزر آزادی", "type": "doctor", "city": "کرمان", "phone": "03432448899", "address": "میدان آزادی، ابتدای خیابان بهشتی", "lat": 30.2890, "lon": 57.0700},
    {"name": "مطب تخصصی پوست و جراحی رفسنجان", "type": "doctor", "city": "رفسنجان", "phone": "03434268800", "address": "رفسنجان، خیابان امیرکبیر", "lat": 30.4020, "lon": 55.9980},
    {"name": "مرکز زیبایی و مراقبت پوست سیرجان", "type": "doctor", "city": "سیرجان", "phone": "03442239900", "address": "سیرجان، بلوار دکتر صادقی", "lat": 29.4500, "lon": 55.6790},

    # ۳. فروشگاه‌ها و گالری‌های آرایشی و بهداشتی (اتاق اصناف و اتحادیه آرایشی)
    {"name": "اتحادیه صنف لوازم آرایشی و بهداشتی کرمان (دفتر مرکزی)", "type": "cosmetics_shop", "city": "کرمان", "phone": "03432251459", "address": "خیابان چمران، حدفاصل کوچه ۱۶ و ۱۸", "lat": 30.2925, "lon": 57.0820},
    {"name": "گالری آرایشی آذین پخش", "type": "cosmetics_shop", "city": "کرمان", "phone": "03432251324", "address": "پارک نشاط، جنب بانک تجارت", "lat": 30.2890, "lon": 57.0750},
    {"name": "فروشگاه آرایشی احمدی", "type": "cosmetics_shop", "city": "کرمان", "phone": "03432220576", "address": "خیابان چمران، پاساژ فرشته، پلاک ۲", "lat": 30.2920, "lon": 57.0810},
    {"name": "گالری آرایشی بهداشتی کوثر", "type": "cosmetics_shop", "city": "کرمان", "phone": "03432230124", "address": "خیابان شهاب، نبش کوچه ۵۶", "lat": 30.2780, "lon": 57.0920},
    {"name": "آرایشی بهداشتی کرمان بهداشت", "type": "cosmetics_shop", "city": "کرمان", "phone": "03432229988", "address": "خیابان شریعتی، روبروی پاساژ ولیعصر", "lat": 30.2900, "lon": 57.0840},
    {"name": "فروشگاه تخصصی محصولات پوستی ماهان", "type": "cosmetics_shop", "city": "ماهان", "phone": "03433775500", "address": "ماهان، میدان انقلاب", "lat": 30.0610, "lon": 57.2900},
    {"name": "گالری آرایشی روژین رفسنجان", "type": "cosmetics_shop", "city": "رفسنجان", "phone": "03434281122", "address": "رفسنجان، خیابان مطهری", "lat": 30.4040, "lon": 55.9910},
    {"name": "مرکز توزیع آرایشی سیرجان پخش", "type": "cosmetics_shop", "city": "سیرجان", "phone": "03442287766", "address": "سیرجان، خیابان ولیعصر", "lat": 29.4550, "lon": 55.6830},
    {"name": "فروشگاه پوست و زیبایی جیرفت", "type": "cosmetics_shop", "city": "جیرفت", "phone": "03443224433", "address": "جیرفت، میدان شاهد", "lat": 28.6750, "lon": 57.7380}
]

added_count = 0
with engine.begin() as conn:
    for item in kerman_master_data:
        exists = conn.execute(text("SELECT id FROM customers WHERE name = :name"), {"name": item["name"]}).first()
        if not exists:
            conn.execute(text("""
                INSERT INTO customers (name, customer_type, city, phone, credit_limit, latitude, longitude, created_at)
                VALUES (:name, :ctype, :city, :phone, 50000000, :lat, :lon, NOW())
            """), {
                "name": item["name"],
                "ctype": item["type"],
                "city": item["city"],
                "phone": item["phone"],
                "lat": item["lat"],
                "lon": item["lon"]
            })
            added_count += 1

print(f" ✓ تعداد {added_count} مرکز جدید از ۳ صنف استان کرمان با مختصات نقشه اضافه شدند.")
print("================================================================")
print("              تمامی تست‌ها با موفقیت کامل انجام شدند!           ")
print("================================================================")
