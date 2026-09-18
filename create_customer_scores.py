from db import engine
from sqlalchemy import text


with engine.begin() as conn:

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS customer_scores (

            id SERIAL PRIMARY KEY,

            customer_id INTEGER,

            score INTEGER,

            status VARCHAR(50),

            created_at TIMESTAMP DEFAULT NOW()

        );
    """))


print("customer_scores table created")