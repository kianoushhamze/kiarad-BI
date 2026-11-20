-- Persistent storage for imported treasury workbooks and manual report batches.
CREATE TABLE IF NOT EXISTS treasury_excel_batches (
    id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(30) NOT NULL,
    title VARCHAR(200) NOT NULL,
    source_note TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'preview',
    created_by INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    committed_by INTEGER,
    committed_at TIMESTAMPTZ,
    UNIQUE(kind, content_hash)
);
