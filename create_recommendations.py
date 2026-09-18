from db import engine
from sqlalchemy import text


with engine.begin() as conn:

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recommendations (

            id SERIAL PRIMARY KEY,

            customer_id INTEGER,

            category VARCHAR(50),

            priority VARCHAR(20),

            message TEXT,

            created_at TIMESTAMP DEFAULT NOW()

        );
    """))

    conn.execute(text("""
        ALTER TABLE recommendations
        ADD COLUMN IF NOT EXISTS category VARCHAR(50);
    """))


print("recommendations table created")
