from db import engine
from sqlalchemy import text

bases = [
    ("داروخانه شبانه‌روزی آزادی", "کرمان", "خیابان آزادی", "034-31310001", 30.2882, 57.0673),
    ("گالری آرایشی رز", "رفسنجان", "خیابان امام", "034-34330002", 30.4067, 55.9939),
    ("داروخانه دکتر صادقی", "سیرجان", "بلوار شهید باهنر", "034-42220003", 29.4521, 55.6811),
    ("کلینیک تخصصی پوست", "جیرفت", "خیابان طالقانی", "034-43330004", 28.6781, 57.7406),
]

with engine.begin() as conn:
    for tbl in ("pharmacies", "cosmetics_shops", "kerman_bases_manual"):
        conn.execute(text(f"DELETE FROM {tbl}"))

    for name, city, addr, phone, lat, lng in bases[:2]:
        conn.execute(text("""INSERT INTO pharmacies
            (name, city, address, phone, latitude, longitude, visit_radius_m)
            VALUES (:n,:c,:a,:p,:lat,:lng,150)"""),
            {"n": name, "c": city, "a": addr, "p": phone, "lat": lat, "lng": lng})

    name, city, addr, phone, lat, lng = bases[2]
    conn.execute(text("""INSERT INTO cosmetics_shops
        (name, city, address, phone, latitude, longitude, visit_radius_m)
        VALUES (:n,:c,:a,:p,:lat,:lng,150)"""),
        {"n": name, "c": city, "a": addr, "p": phone, "lat": lat, "lng": lng})

    name, city, addr, phone, lat, lng = bases[3]
    conn.execute(text("""INSERT INTO kerman_bases_manual
        (name, city, address, phone, latitude, longitude, visit_radius_m)
        VALUES (:n,:c,:a,:p,:lat,:lng,150)"""),
        {"n": name, "c": city, "a": addr, "p": phone, "lat": lat, "lng": lng})

    print("bases seeded")
