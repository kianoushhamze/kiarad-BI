from db import engine
from sqlalchemy import text

STMT = [
# ---- موقعیت ویزیتورها ----
"""CREATE TABLE IF NOT EXISTS salesperson_locations (
    id SERIAL PRIMARY KEY,
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    battery_level INTEGER,
    activity TEXT,
    accuracy DOUBLE PRECISION,
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW()
)""",
"CREATE INDEX IF NOT EXISTS ix_sp_locations_sp_time ON salesperson_locations(salesperson_id, recorded_at DESC)",

# ---- پایگاه‌های مرجع (سه دسته) ----
"""CREATE TABLE IF NOT EXISTS pharmacies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    city VARCHAR(100),
    address TEXT,
    phone VARCHAR(40),
    type VARCHAR(50) DEFAULT 'pharmacy',
    source TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    visit_radius_m INTEGER DEFAULT 150
)""",
"""CREATE TABLE IF NOT EXISTS cosmetics_shops (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    city VARCHAR(100),
    address TEXT,
    phone VARCHAR(40),
    type VARCHAR(50) DEFAULT 'cosmetics',
    source TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    visit_radius_m INTEGER DEFAULT 150
)""",
"""CREATE TABLE IF NOT EXISTS kerman_bases_manual (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    city VARCHAR(100),
    address TEXT,
    phone VARCHAR(40),
    type VARCHAR(50) DEFAULT 'manual',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    visit_radius_m INTEGER DEFAULT 150
)""",

# ---- قرارداد و هدف ----
"""CREATE TABLE IF NOT EXISTS salesperson_contracts (
    id SERIAL PRIMARY KEY,
    salesperson_id INTEGER NOT NULL UNIQUE REFERENCES salespersons(id),
    hourly_rate NUMERIC(14,2) DEFAULT 0,
    min_monthly_hours NUMERIC(8,2) DEFAULT 176,
    settlement_commission_percent NUMERIC(5,2) DEFAULT 0,
    daily_mission_allowance NUMERIC(14,2) DEFAULT 0,
    per_km_rate NUMERIC(14,2) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
)""",
"""CREATE TABLE IF NOT EXISTS salesperson_targets (
    id SERIAL PRIMARY KEY,
    contract_id INTEGER NOT NULL REFERENCES salesperson_contracts(id) ON DELETE CASCADE,
    target_type VARCHAR(40),
    item_identifier VARCHAR(120),
    item_title VARCHAR(200),
    target_amount NUMERIC(14,2) DEFAULT 0,
    target_quantity INTEGER DEFAULT 0,
    commission_percent NUMERIC(5,2) DEFAULT 0
)""",

# ---- حضور و تیک پایگاه ----
"""CREATE TABLE IF NOT EXISTS attendance_sessions (
    id SERIAL PRIMARY KEY,
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    start_time TIMESTAMP NOT NULL DEFAULT NOW(),
    end_time TIMESTAMP,
    start_lat DOUBLE PRECISION,
    start_lng DOUBLE PRECISION,
    end_lat DOUBLE PRECISION,
    end_lng DOUBLE PRECISION,
    duration_hours NUMERIC(8,2),
    is_active BOOLEAN DEFAULT TRUE
)""",
"""CREATE TABLE IF NOT EXISTS base_checkins (
    id SERIAL PRIMARY KEY,
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    base_source VARCHAR(40) NOT NULL,
    base_id INTEGER NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    accuracy_m DOUBLE PRECISION,
    distance_m DOUBLE PRECISION,
    status VARCHAR(24) NOT NULL,
    note TEXT,
    checked_in_at TIMESTAMP NOT NULL DEFAULT NOW()
)""",
"CREATE INDEX IF NOT EXISTS ix_base_checkins_sp_time ON base_checkins(salesperson_id, checked_in_at DESC)",

# ---- یکپارچه‌سازی کانال‌ها (پیش‌نویس‌ها) ----
"""CREATE TABLE IF NOT EXISTS integration_drafts (
    id SERIAL PRIMARY KEY,
    channel VARCHAR(50) NOT NULL UNIQUE,
    public_identifier VARCHAR(200),
    notes TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
)""",
]

with engine.begin() as conn:
    for s in STMT:
        conn.execute(text(s))
print(f"OK: {len(STMT)} statements applied")
