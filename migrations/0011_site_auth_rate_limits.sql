-- Shared, privacy-preserving rate-limit buckets for public customer authentication.
-- Keys are HMACs of endpoint + client IP; raw addresses are never stored.
CREATE TABLE IF NOT EXISTS site_auth_rate_limits (
    bucket_key VARCHAR(64) PRIMARY KEY,
    window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS site_auth_rate_limits_updated_at
    ON site_auth_rate_limits(updated_at);
