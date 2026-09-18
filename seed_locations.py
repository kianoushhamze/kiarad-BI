from db import engine
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text("""
        INSERT INTO salesperson_locations (salesperson_id, latitude, longitude, battery_level, activity, recorded_at) VALUES
        (1, 30.2882, 57.0673, 92, 'ویزیت داروخانه آزادی کرمان', NOW()),
        (1, 30.2915, 57.0812, 88, 'خیابان شریعتی کرمان', NOW() - INTERVAL '20 minutes'),
        (2, 30.4067, 55.9939, 75, 'ویزیت گالری رز رفسنجان', NOW() - INTERVAL '10 minutes')
    """))
    print("✓ نقاط جغرافیایی ویزیتورها در استان کرمان ثبت شد.")
