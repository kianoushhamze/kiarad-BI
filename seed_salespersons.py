from db import engine
from sqlalchemy import text

with engine.begin() as conn:
    cur = conn.execute(text("SELECT COUNT(*) FROM salespersons"))
    count = cur.scalar()
    if count > 0:
        print(f"salespersons already has {count} rows")
    else:
        visitors = [
            ("علی حسینی",  "09131980001"),
            ("رضا مرادی",  "09131980002"),
            ("مهدی صادقی", "09131980003"),
            ("سارا احمدی", "09131980004"),
        ]
        for name, phone in visitors:
            conn.execute(
                text("INSERT INTO salespersons (name, phone) VALUES (:n, :p)"),
                {"n": name, "p": phone},
            )
        print(f"inserted {len(visitors)} salespersons")
