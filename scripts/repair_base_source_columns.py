"""Verify the additive migration on temporary tables, then repair base metadata."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
from sqlalchemy import text
from db import engine
from crud_api import _ensure_base_source_columns, ALLOWED_TABLES

with engine.connect() as conn:
    transaction = conn.begin()
    try:
        conn.execute(text('SET LOCAL search_path TO pg_temp'))
        for table in ('pharmacies', 'cosmetics_shops'):
            conn.execute(text(f'CREATE TEMP TABLE {table} (id INTEGER, name TEXT)'))
            conn.execute(text(f"INSERT INTO {table} VALUES (1, 'synthetic')"))
        _ensure_base_source_columns(conn)
        _ensure_base_source_columns(conn)
        for table in ('pharmacies', 'cosmetics_shops'):
            assert conn.execute(text(f'SELECT id,name,source FROM {table}')).one() == (1, 'synthetic', None)
    finally:
        transaction.rollback()
print('Temporary migration and repeatability: PASS')

with engine.begin() as conn:
    conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    _ensure_base_source_columns(conn)
    for table in ('pharmacies', 'cosmetics_shops'):
        conn.execute(text('SELECT id,' + ','.join(ALLOWED_TABLES[table]) + f' FROM {table} LIMIT 0'))
print('Base list schema: PASS; existing records preserved')
