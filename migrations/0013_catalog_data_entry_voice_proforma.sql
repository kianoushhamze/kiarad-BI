-- Versioned storage for catalog batches/media, manual data authority, voice reports and proforma queues.
-- Existing records are retained; request handlers and startup hooks do not create these schemas.

CREATE TABLE IF NOT EXISTS inventory_batches (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    batch_code VARCHAR(100) NOT NULL,
    expiry_date DATE NOT NULL,
    quantity NUMERIC(14,3) NOT NULL CHECK (quantity > 0),
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, batch_code)
);
CREATE INDEX IF NOT EXISTS ix_inventory_batches_expiry
    ON inventory_batches(expiry_date, product_id);

CREATE TABLE IF NOT EXISTS data_field_overrides (
    entity TEXT NOT NULL,
    local_id INT NOT NULL,
    field TEXT NOT NULL,
    value JSONB NOT NULL,
    updated_by INT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(entity, local_id, field)
);
CREATE TABLE IF NOT EXISTS data_change_audit (
    id BIGSERIAL PRIMARY KEY,
    entity TEXT NOT NULL,
    local_id INT NOT NULL,
    source TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS data_entry_batches (
    id BIGSERIAL PRIMARY KEY,
    entity TEXT NOT NULL,
    created_by INT NOT NULL,
    input_mode TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'preview',
    receipt JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    committed_at TIMESTAMPTZ,
    UNIQUE(entity, created_by, content_hash)
);

CREATE TABLE IF NOT EXISTS product_media (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    media_type VARCHAR(20) NOT NULL,
    file_path TEXT NOT NULL,
    file_name TEXT,
    mime_type VARCHAR(120),
    size_bytes BIGINT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    caption TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_product_media_product_id ON product_media(product_id);
ALTER TABLE IF EXISTS pharmacies ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE IF EXISTS cosmetics_shops ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS price2 NUMERIC;

CREATE TABLE IF NOT EXISTS holoo_entity_mappings (
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('customer', 'product')),
    local_id INTEGER NOT NULL,
    holoo_erp_code VARCHAR(200) NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'sync',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entity_type, local_id)
);
CREATE INDEX IF NOT EXISTS ix_holoo_entity_mappings_code
    ON holoo_entity_mappings(entity_type, holoo_erp_code);

CREATE TABLE IF NOT EXISTS proforma_holoo_queue (
    id SERIAL PRIMARY KEY,
    proforma_id INTEGER NOT NULL UNIQUE REFERENCES proforma_invoices(id) ON DELETE CASCADE,
    operation_key VARCHAR(120) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    external_invoice_id VARCHAR(120),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proforma_holoo_queue_status
    ON proforma_holoo_queue(status, created_at);

ALTER TABLE IF EXISTS daily_reports
    ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id);
CREATE TABLE IF NOT EXISTS voice_report_entries (
    id SERIAL PRIMARY KEY,
    created_by INTEGER NOT NULL REFERENCES users(id),
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    report_id INTEGER NOT NULL REFERENCES daily_reports(id),
    task_id INTEGER REFERENCES tasks(id),
    customer_id INTEGER REFERENCES customers(id),
    customer_name TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    visits_count INTEGER NOT NULL,
    orders_count INTEGER NOT NULL,
    reported_sales_amount NUMERIC NOT NULL,
    reported_collections_amount NUMERIC NOT NULL,
    submission_key UUID NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
    UNIQUE(created_by, submission_key)
);
