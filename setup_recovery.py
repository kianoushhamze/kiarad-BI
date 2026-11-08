"""Idempotent schema setup for email recovery. Run with manager contact environment variables."""

import os
from sqlalchemy import text
from db import engine


email = os.environ.get("KIARAD_MANAGER_RECOVERY_EMAIL", "").strip().lower()
phone = os.environ.get("KIARAD_MANAGER_RECOVERY_PHONE", "").strip()
if not email or not phone:
    raise SystemExit("Manager recovery email and phone are required")

with engine.begin() as conn:
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_email VARCHAR(254)"))
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_phone VARCHAR(30)"))
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_version INTEGER NOT NULL DEFAULT 0"))
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS users_recovery_email_unique
        ON users (lower(recovery_email)) WHERE recovery_email IS NOT NULL
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS password_reset_tokens_user_created
        ON password_reset_tokens (user_id, created_at DESC)
    """))
    result = conn.execute(text("""
        UPDATE users SET recovery_email = :email, recovery_phone = :phone
        WHERE username = 'manager'
    """), {"email": email, "phone": phone})
    if result.rowcount != 1:
        raise RuntimeError("Manager user was not found")

print("Recovery schema and manager contact configured")
