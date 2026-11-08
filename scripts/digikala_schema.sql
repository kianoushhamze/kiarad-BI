CREATE TABLE IF NOT EXISTS digikala_variants (
  dkp_id BIGINT PRIMARY KEY,
  holoo_code TEXT,
  title TEXT,
  status TEXT,
  price_rrp BIGINT,
  price_selling BIGINT,
  stock INTEGER,
  source TEXT NOT NULL DEFAULT 'digikala',
  raw JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_digikala_variants_holoo ON digikala_variants (holoo_code);
CREATE TABLE IF NOT EXISTS variant_map (
  supplier_code TEXT PRIMARY KEY,
  holoo_code TEXT NOT NULL,
  note TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);