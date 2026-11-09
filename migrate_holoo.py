# -*- coding: utf-8 -*-
"""Database migration for the Holoo sync (safe to run more than once).

Run from the project folder:  python migrate_holoo.py
(create_all in init_db.py does not add columns to existing tables, so this is required.)
"""
from sqlalchemy import text

from db import engine

STATEMENTS = [
    # sales: Holoo invoice link and amounts
    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS holoo_code INTEGER",
    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS holoo_sanad_code INTEGER",
    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS paid_amount DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS credit_amount DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS discount_amount DOUBLE PRECISION DEFAULT 0",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_holoo_code ON sales (holoo_code)",
    # customers: responsible visitor
    "ALTER TABLE customers ADD COLUMN IF NOT EXISTS salesperson_id INTEGER REFERENCES salespersons(id)",
    "CREATE INDEX IF NOT EXISTS ix_customers_salesperson_id ON customers (salesperson_id)",
]

# Arabic yeh/kaf -> Persian in names already stored (the sync now does this on every run)
ARABIC, PERSIAN = "\u064a\u0643\u0649", "\u06cc\u06a9\u06cc"
NORMALIZE = [
    "UPDATE customers SET name = translate(name, :a, :p) WHERE name IS NOT NULL AND name ~ '[\u064a\u0643\u0649]'",
    "UPDATE products SET name = translate(name, :a, :p) WHERE name IS NOT NULL AND name ~ '[\u064a\u0643\u0649]'",
    "UPDATE products SET category = translate(category, :a, :p) WHERE category IS NOT NULL AND category ~ '[\u064a\u0643\u0649]'",
]

with engine.begin() as conn:
    for stmt in STATEMENTS:
        conn.execute(text(stmt))
        print("OK:", stmt[:90])
    for stmt in NORMALIZE:
        n = conn.execute(text(stmt), {"a": ARABIC, "p": PERSIAN}).rowcount
        print(f"OK: {n} rows normalized ->", stmt.split(" SET ")[0])

print("Migration finished.")
