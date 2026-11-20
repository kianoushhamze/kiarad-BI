-- Storefront customer, order, banner and marketplace storage.
-- These objects used to be created opportunistically from HTTP requests.
-- Keep existing rows; add only the idempotency/reservation columns required by current code.

CREATE TABLE IF NOT EXISTS site_customers (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE,
    phone TEXT UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS site_orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    phone TEXT,
    city TEXT,
    address TEXT,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_irr BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'جدید',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE site_orders ADD COLUMN IF NOT EXISTS request_key TEXT;
ALTER TABLE site_orders ADD COLUMN IF NOT EXISTS request_fingerprint TEXT;
ALTER TABLE site_orders ADD COLUMN IF NOT EXISTS reservation_managed BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS site_orders_customer_request_key
    ON site_orders(customer_id, request_key) WHERE request_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS site_banners (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    image_base64 TEXT NOT NULL,
    link_url TEXT,
    sort INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS site_banners_active_sort
    ON site_banners(active, sort, id);

CREATE TABLE IF NOT EXISTS platform_listings (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    code TEXT NOT NULL,
    external_id TEXT,
    price_mode TEXT NOT NULL DEFAULT 'auto',
    manual_price_irr BIGINT,
    price_factor NUMERIC(6,3) DEFAULT 1.0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_push_at TIMESTAMPTZ,
    UNIQUE(platform, code)
);

CREATE TABLE IF NOT EXISTS platform_reservations (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    external_ref TEXT NOT NULL,
    code TEXT NOT NULL,
    qty INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(platform, external_ref, code)
);

CREATE INDEX IF NOT EXISTS platform_reservations_code_status
    ON platform_reservations(code, status);

CREATE TABLE IF NOT EXISTS platform_orders_raw (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    order_ref TEXT NOT NULL,
    status TEXT,
    raw JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(platform, order_ref)
);

CREATE TABLE IF NOT EXISTS platform_create_proposals (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL DEFAULT 'digikala',
    code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    suggested_title TEXT NOT NULL,
    category_id BIGINT,
    price_irr BIGINT,
    stock INT NOT NULL DEFAULT 0,
    image_url TEXT,
    gtin TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    payload JSONB,
    receipt JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS platform_order_proformas (
    id SERIAL PRIMARY KEY,
    platform TEXT NOT NULL,
    order_ref TEXT NOT NULL,
    proforma_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'platform',
    status TEXT NOT NULL DEFAULT 'draft',
    holoo_registered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(platform, order_ref)
);
