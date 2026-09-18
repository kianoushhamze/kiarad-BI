from db import engine
from sqlalchemy import text


with engine.begin() as conn:

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS targets (
            id SERIAL PRIMARY KEY,
            title VARCHAR(100),
            target_amount FLOAT,
            month INTEGER,
            year INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """))

print("targets table created")