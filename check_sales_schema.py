from sqlalchemy import text
from db import engine

with engine.connect() as conn:
    print("=== ستون‌های واقعی جدول sales ===")
    cols = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='sales'")).scalars().all()
    print(cols)
    
    print("\n=== ۳ نمونه از آخرین فاکتورهای ثبت شده ===")
    sample = conn.execute(text("SELECT * FROM sales ORDER BY id DESC LIMIT 3")).mappings().all()
    for s in sample:
        print(dict(s))
