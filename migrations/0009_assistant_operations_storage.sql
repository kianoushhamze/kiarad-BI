-- Versioned storage for assistant operations and scheduled automations.
-- These tables are read by multiple routes; provision them before application startup.

CREATE TABLE IF NOT EXISTS assistant_operation_proposals (
    id UUID PRIMARY KEY,
    actor_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    payload JSONB NOT NULL,
    baseline JSONB,
    status TEXT NOT NULL DEFAULT 'preview',
    receipt JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '20 minutes'
);

CREATE INDEX IF NOT EXISTS ix_assistant_operation_proposals_actor_status
    ON assistant_operation_proposals(actor_id, status, expires_at);

CREATE TABLE IF NOT EXISTS assistant_automations (
    id SERIAL PRIMARY KEY,
    owner_user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_type TEXT NOT NULL DEFAULT 'interval',
    interval_hours INTEGER,
    daily_time TEXT,
    weekdays JSONB,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_assistant_automations_due
    ON assistant_automations(enabled, next_run_at);

CREATE TABLE IF NOT EXISTS assistant_automation_runs (
    id SERIAL PRIMARY KEY,
    automation_id INTEGER NOT NULL REFERENCES assistant_automations(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    summary TEXT,
    proposals JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_assistant_automation_runs_latest
    ON assistant_automation_runs(automation_id, started_at DESC);
