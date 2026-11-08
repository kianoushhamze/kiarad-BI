from db import engine
from sqlalchemy import text

with engine.begin() as conn:
    rows = conn.execute(text("SELECT id FROM salespersons ORDER BY id")).fetchall()
    ids = [r[0] for r in rows]
    print(f"salesperson ids: {ids}")

    conn.execute(text("DELETE FROM salesperson_locations"))

    points = [
        (30.2882, 57.0673, 94, "در حال ویزیت داروخانه شبانه‌روزی آزادی کرمان"),
        (30.4067, 55.9939, 78, "ویزیت گالری آرایشی رز رفسنجان"),
        (29.4521, 55.6811, 85, "مراجعه به داروخانه دکتر صادقی سیرجان"),
        (28.6781, 57.7406, 62, "ویزیت کلینیک تخصصی پوست جیرفت"),
    ]

    for i, sp_id in enumerate(ids):
        lat, lng, bat, act = points[i % len(points)]
        conn.execute(
            text("""INSERT INTO salesperson_locations
                    (salesperson_id, latitude, longitude, battery_level, activity, recorded_at)
                    VALUES (:sp, :lat, :lng, :bat, :act, NOW())"""),
            {"sp": sp_id, "lat": lat, "lng": lng, "bat": bat, "act": act}
        )

    print(f"inserted {len(ids)} locations")
