-- CMS product metadata shared by the admin UI, public catalog and marketplace feeds.
-- Safe for both fresh installations and legacy installations that already have the table.
CREATE TABLE IF NOT EXISTS cms_product_meta (
    code VARCHAR(100) PRIMARY KEY,
    site_category TEXT,
    image_url TEXT,
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE cms_product_meta
    ADD COLUMN IF NOT EXISTS discount_price_irr BIGINT;
