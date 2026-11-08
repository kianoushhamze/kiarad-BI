"""Store Holoo ERP identifiers separately from local/business codes."""

from sqlalchemy import text


def ensure_holoo_entity_mappings(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS holoo_entity_mappings (
            entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('customer', 'product')),
            local_id INTEGER NOT NULL,
            holoo_erp_code VARCHAR(200) NOT NULL,
            source VARCHAR(20) NOT NULL DEFAULT 'sync',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (entity_type, local_id)
        )
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_holoo_entity_mappings_code
        ON holoo_entity_mappings(entity_type, holoo_erp_code)
    """))


def save_holoo_entity_mapping(db, entity_type, local_id, erp_code):
    normalized = str(erp_code or "").strip()
    if not normalized:
        return False
    if entity_type not in {"customer", "product"}:
        raise ValueError("Unsupported Holoo mapping type")
    db.execute(text("""
        INSERT INTO holoo_entity_mappings(entity_type, local_id, holoo_erp_code, source, updated_at)
        VALUES (:entity_type, :local_id, :erp_code, 'sync', NOW())
        ON CONFLICT (entity_type, local_id) DO UPDATE
        SET holoo_erp_code=EXCLUDED.holoo_erp_code, source='sync', updated_at=NOW()
    """), {"entity_type": entity_type, "local_id": int(local_id), "erp_code": normalized})
    return True
