from db import engine
from sqlalchemy import text

with engine.begin() as conn:
    # ثبت یا به‌روزرسانی مشتریان
    customers = [
        ("C101", "داروخانه شبانه‌روزی دکتر کرمانی", "03432221100", "کرمان", 120000000),
        ("C102", "داروخانه دکتر ابراهیمی", "03432456789", "کرمان", 80000000),
        ("C103", "کلینیک پوست و زیبایی بهار", "03433334455", "کرمان", 200000000),
        ("C104", "داروخانه دکتر صادقی", "03442223344", "سیرجان", 60000000),
        ("C105", "گالری آرایشی رز", "03432112233", "رفسنجان", 40000000)
    ]
    for code, name, phone, city, limit in customers:
        conn.execute(text("""
            INSERT INTO customers (code, name, phone, city, credit_limit, created_at)
            VALUES (:code, :name, :phone, :city, :limit, NOW())
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, credit_limit = EXCLUDED.credit_limit
        """), {"code": code, "name": name, "phone": phone, "city": city, "limit": limit})

    # ثبت یا به‌روزرسانی کالاها و قیمت‌ها
    products = [
        ("P101", "کرم ترمیم‌کننده سوالین ویرا ۳۰ میل", "ترمیم‌کننده", 3800000, 150),
        ("P102", "ژل شستشوی پوست درمالیست ۱۵۰ میل", "شوینده", 2100000, 200),
        ("P103", "ضدآفتاب رنگی توتال درم ۵۰ میل", "ضدآفتاب", 4500000, 120),
        ("P104", "کوکتل مزوتراپی ضدلک ام‌سی کازمتیک", "مزوتراپی", 12500000, 50),
        ("P105", "کوکتل جوانساز ام‌سی کازمتیک", "مزوتراپی", 14000000, 45),
        ("P106", "کرم مرطوب‌کننده قوی درمالیست", "مرطوب‌کننده", 2900000, 180)
    ]
    for code, name, cat, price, stock in products:
        conn.execute(text("""
            INSERT INTO products (code, name, category, price, stock)
            VALUES (:code, :name, :cat, :price, :stock)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, price = EXCLUDED.price, stock = EXCLUDED.stock
        """), {"code": code, "name": name, "cat": cat, "price": price, "stock": stock})

    c_cnt = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
    p_cnt = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
    print(f"تعداد نهایی مشتریان در دیتابیس: {c_cnt}")
    print(f"تعداد نهایی کالاها در دیتابیس: {p_cnt}")
