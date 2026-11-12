-- Additive Traccar device bindings and explicit shift ownership.
ALTER TABLE tracking_sessions ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'kiarad';

CREATE TABLE IF NOT EXISTS traccar_devices(id UUID PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
        identifier TEXT NOT NULL UNIQUE,platform TEXT NOT NULL,label TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),revoked_at TIMESTAMPTZ,last_received_at TIMESTAMPTZ,last_recorded_at TIMESTAMPTZ);

CREATE UNIQUE INDEX IF NOT EXISTS traccar_active_owner ON traccar_devices(user_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS traccar_shifts(session_id UUID PRIMARY KEY REFERENCES tracking_sessions(id),
        device_id UUID NOT NULL REFERENCES traccar_devices(id),auth_version INTEGER NOT NULL DEFAULT 0);

ALTER TABLE traccar_shifts ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS traccar_shifts_device ON traccar_shifts(device_id);

CREATE TABLE IF NOT EXISTS traccar_device_events(id BIGSERIAL PRIMARY KEY,device_id UUID NOT NULL REFERENCES traccar_devices(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW());
