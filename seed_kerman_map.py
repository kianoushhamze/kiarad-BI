from db import engine
from sqlalchemy import text

with engine.begin() as conn:
    # ثبت ویزیتورهای مناطق مختلف
    visitors = [
        ("علی حسینی", "09131980001"),
        ("رضا مرادی", "09131980002"),
        ("مهدی صادقی", "09131980003"),
        ("سارا احمدی", "09131980004")
    ]
    for name, phone in visitors:
        conn.execute(text("""
            INSERT INTO salespersons (name, phone) VALUES (:name, :phone)
            ON CONFLICT DO NOTHING
        """), {"name": name, "phone": phone})

    # ثبت آخرین موقعیت‌های مکانی در استان کرمان
    conn.execute(text("""
        DELETE FROM salesperson_locations;
        INSERT INTO salesperson_locations (salesperson_id, latitude, longitude, battery_level, activity, recorded_at) VALUES
        (1, 30.2882, 57.0673, 94, 'در حال ویزیت داروخانه شبانه‌روزی آزادی کرمان', NOW()),
        (2, 30.4067, 55.9939, 78, 'ویزیت گالری آرایشی رز رفسنجان', NOW() - INTERVAL '12 minutes'),
        (3, 29.4521, 55.6811, 85, 'مراجعه به داروخانه دکتر صادقی سیرجان', NOW() - INTERVAL '25 minutes'),
        (4, 28.6781, 57.7406, 62, 'ویزیت کلینیک تخصصی پوست جیرفت', NOW() - INTERVAL '5 minutes');
    """))
    print("✓ موقعیت ویزیتورها در کرمان، سیرجان، رفسنجان و جیرفت ثبت شد.")
