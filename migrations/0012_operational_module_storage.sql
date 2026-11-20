-- Versioned storage for remaining operational, route-planning, marketing and integration modules.
-- Additive only: existing records are retained; application startup and requests no longer create these schemas.

-- Task workflow and campaign management.
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
    priority VARCHAR(20) NOT NULL DEFAULT 'normal', status VARCHAR(20) NOT NULL DEFAULT 'new',
    progress INTEGER NOT NULL DEFAULT 0, assigned_to INTEGER NOT NULL REFERENCES users(id),
    created_by INTEGER NOT NULL REFERENCES users(id), customer_id INTEGER REFERENCES customers(id),
    due_date TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS task_updates (
    id SERIAL PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
    user_id INTEGER NOT NULL REFERENCES users(id), progress INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL, note TEXT, created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS review_status VARCHAR(30) NOT NULL DEFAULT 'not_submitted',
    ADD COLUMN IF NOT EXISTS reviewed_by INTEGER REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS review_note TEXT;

CREATE TABLE IF NOT EXISTS role_permissions (
    role TEXT NOT NULL, module TEXT NOT NULL,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    can_write BOOLEAN NOT NULL DEFAULT FALSE,
    can_delete BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (role, module)
);
CREATE TABLE IF NOT EXISTS campaigns (
    id SERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT,
    starts_at DATE NOT NULL, ends_at DATE NOT NULL,
    target_amount NUMERIC NOT NULL DEFAULT 0,
    reward_type TEXT NOT NULL DEFAULT 'fixed',
    reward_value NUMERIC NOT NULL DEFAULT 0, reward_note TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS campaign_assignments (
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    assigned_by INTEGER NOT NULL REFERENCES users(id),
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (campaign_id, user_id)
);
CREATE TABLE IF NOT EXISTS notification_reads (
    user_id INTEGER NOT NULL REFERENCES users(id),
    notification_key TEXT NOT NULL,
    read_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, notification_key)
);

-- Route assignments are created before monthly plan stops reference them.
CREATE TABLE IF NOT EXISTS visit_route_assignments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    base_source VARCHAR(40) NOT NULL,
    base_id INTEGER NOT NULL,
    visit_date DATE NOT NULL,
    stop_order INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    assigned_by INTEGER NOT NULL REFERENCES users(id),
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, base_source, base_id, visit_date)
);
CREATE INDEX IF NOT EXISTS ix_visit_routes_user_date
    ON visit_route_assignments(user_id, visit_date, stop_order);
ALTER TABLE visit_route_assignments
    ADD COLUMN IF NOT EXISTS start_time TIME,
    ADD COLUMN IF NOT EXISTS end_time TIME;

CREATE TABLE IF NOT EXISTS base_portfolio_assignments (
    id SERIAL PRIMARY KEY,
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    base_source TEXT NOT NULL,
    base_id INTEGER NOT NULL,
    assigned_by INTEGER NOT NULL REFERENCES users(id),
    assigned_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
    ended_at TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_active_base_portfolio
    ON base_portfolio_assignments(base_source, base_id) WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS base_proposals (
    id SERIAL PRIMARY KEY,
    created_by INTEGER NOT NULL REFERENCES users(id),
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    submission_key UUID NOT NULL,
    payload_hash TEXT NOT NULL,
    name VARCHAR(160) NOT NULL,
    city VARCHAR(100) NOT NULL,
    address TEXT NOT NULL,
    phone VARCHAR(30),
    category VARCHAR(24) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    accuracy_m DOUBLE PRECISION,
    note TEXT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_note TEXT,
    approved_base_id INTEGER REFERENCES kerman_bases_manual(id),
    holoo_status VARCHAR(40) NOT NULL DEFAULT 'not_requested',
    UNIQUE(created_by, submission_key)
);

CREATE TABLE IF NOT EXISTS physicians (
    id SERIAL PRIMARY KEY, name TEXT NOT NULL, level TEXT, specialty TEXT, city TEXT, area TEXT,
    address TEXT, phone TEXT, source TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_physicians_name_city
    ON physicians(name, (COALESCE(city, '')));
CREATE INDEX IF NOT EXISTS ix_physicians_city ON physicians(city);

-- Social channel credentials remain private and are never returned in plaintext.
CREATE TABLE IF NOT EXISTS social_channels (
    platform TEXT PRIMARY KEY,
    credentials JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'disconnected',
    last_checked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Marketing intelligence.
CREATE TABLE IF NOT EXISTS market_questions (
    id SERIAL PRIMARY KEY,
    asked_on DATE NOT NULL DEFAULT CURRENT_DATE,
    topic TEXT NOT NULL DEFAULT 'عمومی',
    question TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'web',
    signal_score INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_market_questions_q
    ON market_questions(lower(question));
CREATE TABLE IF NOT EXISTS market_demand (
    code TEXT PRIMARY KEY, category TEXT, kerman_sales_pct NUMERIC(6,2),
    web_signal INT NOT NULL DEFAULT 0, sales_source TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS marketing_content (
    id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
    based_on JSONB NOT NULL DEFAULT '{}'::jsonb, status TEXT NOT NULL DEFAULT 'draft'
);
CREATE TABLE IF NOT EXISTS marketing_leads (
    id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'manual', name TEXT NOT NULL, city TEXT,
    phone TEXT, address TEXT, detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_marketing_leads_name_city
    ON marketing_leads(name, (COALESCE(city, '')));
CREATE INDEX IF NOT EXISTS ix_marketing_leads_source ON marketing_leads(source);
CREATE INDEX IF NOT EXISTS ix_marketing_leads_city ON marketing_leads(city);

-- Integration drafts, calendar and connection-check evidence.
CREATE TABLE IF NOT EXISTS integration_drafts (
    channel VARCHAR(40) PRIMARY KEY,
    account_label VARCHAR(160) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL
);
DO $$
DECLARE
    had_account_label BOOLEAN;
    has_public_identifier BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'public.integration_drafts'::regclass
          AND attname = 'account_label' AND NOT attisdropped
    ) INTO had_account_label;

    ALTER TABLE public.integration_drafts
        ADD COLUMN IF NOT EXISTS account_label VARCHAR(160) NOT NULL DEFAULT '';

    SELECT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'public.integration_drafts'::regclass
          AND attname = 'public_identifier' AND NOT attisdropped
    ) INTO has_public_identifier;

    IF has_public_identifier AND NOT had_account_label THEN
        EXECUTE 'UPDATE public.integration_drafts
                 SET account_label = COALESCE(public_identifier, '''')
                 WHERE account_label = ''''
                   AND COALESCE(public_identifier, '''') <> ''''';
    END IF;

    IF has_public_identifier THEN
        ALTER TABLE public.integration_drafts
            ALTER COLUMN public_identifier SET DEFAULT '';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS social_content_calendar (
    id SERIAL PRIMARY KEY,
    channel VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_by INTEGER NOT NULL,
    reviewed_by INTEGER,
    review_note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS integration_connection_checks (
    channel TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    http_status INT,
    checked_at TIMESTAMPTZ NOT NULL,
    checked_by INT NOT NULL
);

-- Monthly visit plans and evidence-based workday reviews.
CREATE TABLE IF NOT EXISTS monthly_visit_plans (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
    month TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_by INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'draft',
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    review_note TEXT,
    UNIQUE(user_id, month, revision)
);
CREATE TABLE IF NOT EXISTS monthly_visit_plan_stops (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES monthly_visit_plans(id),
    visit_date DATE NOT NULL,
    base_source TEXT NOT NULL,
    base_id INTEGER NOT NULL,
    stop_order INTEGER NOT NULL,
    objective TEXT NOT NULL,
    route_id INTEGER REFERENCES visit_route_assignments(id),
    outcome_status VARCHAR(50),
    holoo_preinvoice_code VARCHAR(100),
    order_amount_rial BIGINT DEFAULT 0,
    outcome_notes TEXT,
    follow_up_date DATE,
    start_time TIME,
    end_time TIME,
    UNIQUE(plan_id, visit_date, base_source, base_id),
    UNIQUE(plan_id, visit_date, stop_order)
);
ALTER TABLE monthly_visit_plan_stops
    ADD COLUMN IF NOT EXISTS outcome_status VARCHAR(50),
    ADD COLUMN IF NOT EXISTS holoo_preinvoice_code VARCHAR(100),
    ADD COLUMN IF NOT EXISTS order_amount_rial BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS outcome_notes TEXT,
    ADD COLUMN IF NOT EXISTS follow_up_date DATE,
    ADD COLUMN IF NOT EXISTS start_time TIME,
    ADD COLUMN IF NOT EXISTS end_time TIME;
CREATE TABLE IF NOT EXISTS monthly_visit_plan_events (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES monthly_visit_plans(id),
    actor_id INTEGER NOT NULL REFERENCES users(id),
    event TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS monthly_visit_workday_reviews (
    id BIGSERIAL PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES monthly_visit_plans(id),
    work_date DATE NOT NULL,
    credited_days NUMERIC(5,3) NOT NULL CHECK(credited_days >= 0 AND credited_days <= 1),
    evidence JSONB NOT NULL,
    review_note TEXT NOT NULL,
    reviewed_by INTEGER NOT NULL REFERENCES users(id),
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fact_id INTEGER,
    UNIQUE(plan_id, work_date)
);
CREATE UNIQUE INDEX IF NOT EXISTS monthly_visit_one_approved
    ON monthly_visit_plans(user_id, month) WHERE status = 'approved';

-- Treasury strategy revisions, deterministic morning briefs and AI campaign proposals.
CREATE TABLE IF NOT EXISTS treasury_strategy_revisions (
    id BIGSERIAL PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,
    revision INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_by INTEGER NOT NULL,
    approved_by INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(scope, revision)
);
CREATE TABLE IF NOT EXISTS morning_briefs (
    id SERIAL PRIMARY KEY,
    biz_date DATE NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS morning_brief_views (
    id SERIAL PRIMARY KEY,
    biz_date DATE NOT NULL,
    viewed_by INT NOT NULL,
    viewed_by_name TEXT NOT NULL DEFAULT '',
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(biz_date, viewed_by)
);
CREATE TABLE IF NOT EXISTS ai_suggestions (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    payload JSONB NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    suggested_by INTEGER,
    decided_by INTEGER,
    decided_at TIMESTAMPTZ,
    approved_campaign_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Optional target columns are added without replacing any existing values.
ALTER TABLE IF EXISTS targets
    ADD COLUMN IF NOT EXISTS period_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS product_focus VARCHAR(150),
    ADD COLUMN IF NOT EXISTS bonus_reward NUMERIC(15,2);
