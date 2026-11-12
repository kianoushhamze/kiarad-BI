-- Reviewed recurring workflows, contact consent, receipts and source-cited education.
-- Existing task workflow is supplied by baseline migration 0001.

CREATE TABLE IF NOT EXISTS outbound_contacts(id UUID PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customers(id),
        channel TEXT NOT NULL,destination TEXT NOT NULL,consent_scope TEXT NOT NULL,evidence TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,created_by INTEGER NOT NULL REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),
        revoked_at TIMESTAMPTZ,UNIQUE(customer_id,channel,destination,consent_scope));

CREATE TABLE IF NOT EXISTS outbound_messages(id UUID PRIMARY KEY,created_by INTEGER NOT NULL REFERENCES users(id),
        submission_key UUID NOT NULL,contact_id UUID NOT NULL REFERENCES outbound_contacts(id),payload JSONB NOT NULL,digest TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'draft',scheduled_at TIMESTAMPTZ NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW(),
        approved_at TIMESTAMPTZ,approval_expires_at TIMESTAMPTZ,attempted_at TIMESTAMPTZ,finished_at TIMESTAMPTZ,
        receipt JSONB,error_code TEXT,UNIQUE(created_by,submission_key));

CREATE TABLE IF NOT EXISTS outbound_events(id BIGSERIAL PRIMARY KEY,message_id UUID REFERENCES outbound_messages(id),
        actor_id INTEGER REFERENCES users(id),kind TEXT NOT NULL,detail JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW());

CREATE INDEX IF NOT EXISTS outbound_due ON outbound_messages(scheduled_at) WHERE state='approved';

CREATE TABLE IF NOT EXISTS prospect_runs(id UUID PRIMARY KEY,created_by INTEGER NOT NULL REFERENCES users(id),
        submission_key UUID NOT NULL,state TEXT NOT NULL DEFAULT 'started',started_at TIMESTAMPTZ DEFAULT NOW(),finished_at TIMESTAMPTZ,
        summary JSONB,error_code TEXT,UNIQUE(created_by,submission_key));

CREATE TABLE IF NOT EXISTS prospect_candidates(id UUID PRIMARY KEY,source TEXT NOT NULL,source_key TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,payload JSONB NOT NULL,payload_hash TEXT NOT NULL,identity_hint TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'unverified',first_seen_at TIMESTAMPTZ DEFAULT NOW(),last_seen_at TIMESTAMPTZ DEFAULT NOW(),
        reviewed_by INTEGER REFERENCES users(id),reviewed_at TIMESTAMPTZ,review_note TEXT,base_source TEXT,base_id INTEGER,
        UNIQUE(source,source_key));

CREATE TABLE IF NOT EXISTS prospect_observations(id BIGSERIAL PRIMARY KEY,candidate_id UUID NOT NULL REFERENCES prospect_candidates(id),
        run_id UUID NOT NULL REFERENCES prospect_runs(id),revision INTEGER NOT NULL,payload JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(candidate_id,run_id));

CREATE TABLE IF NOT EXISTS prospect_reviews(id BIGSERIAL PRIMARY KEY,candidate_id UUID NOT NULL REFERENCES prospect_candidates(id),
        revision INTEGER NOT NULL,actor_id INTEGER NOT NULL REFERENCES users(id),decision TEXT NOT NULL,note TEXT NOT NULL,
        payload JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW());

CREATE INDEX IF NOT EXISTS prospect_review_queue ON prospect_candidates(review_status,last_seen_at DESC);

CREATE INDEX IF NOT EXISTS prospect_identity_hint ON prospect_candidates(identity_hint);

CREATE TABLE IF NOT EXISTS agent_routines(id UUID PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,
        kind TEXT NOT NULL,spec JSONB NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft',created_at TIMESTAMPTZ DEFAULT NOW(),
        approved_at TIMESTAMPTZ,next_run_at TIMESTAMPTZ,lease_until TIMESTAMPTZ,UNIQUE(owner_id,name));

CREATE TABLE IF NOT EXISTS agent_routine_cycles(id UUID PRIMARY KEY,routine_id UUID NOT NULL REFERENCES agent_routines(id),
        scheduled_for TIMESTAMPTZ NOT NULL,state TEXT NOT NULL DEFAULT 'running',started_at TIMESTAMPTZ DEFAULT NOW(),finished_at TIMESTAMPTZ,
        result JSONB,error_code TEXT,UNIQUE(routine_id,scheduled_for));

CREATE TABLE IF NOT EXISTS agent_routine_events(id BIGSERIAL PRIMARY KEY,routine_id UUID NOT NULL REFERENCES agent_routines(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,detail JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW());

CREATE INDEX IF NOT EXISTS routines_due ON agent_routines(next_run_at) WHERE state='active';

CREATE TABLE IF NOT EXISTS specialist_contract_reviews(id UUID PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),
    source_id UUID NOT NULL REFERENCES agent_sources(id),source_digest TEXT NOT NULL,report JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW());

CREATE TABLE IF NOT EXISTS specialist_obligation_tasks(review_id UUID NOT NULL REFERENCES specialist_contract_reviews(id),
    obligation_index INTEGER NOT NULL,task_id INTEGER NOT NULL REFERENCES tasks(id),created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),PRIMARY KEY(review_id,obligation_index));

CREATE TABLE IF NOT EXISTS training_programmes(id UUID PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),submission_key UUID NOT NULL,
        title TEXT NOT NULL,payload JSONB NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft',created_at TIMESTAMPTZ DEFAULT NOW(),
        published_at TIMESTAMPTZ,UNIQUE(owner_id,submission_key));

CREATE TABLE IF NOT EXISTS training_enrollments(id UUID PRIMARY KEY,programme_id UUID NOT NULL REFERENCES training_programmes(id),
        user_id INTEGER NOT NULL REFERENCES users(id),task_id INTEGER NOT NULL REFERENCES tasks(id),due_date TIMESTAMPTZ NOT NULL,
        enrolled_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(programme_id,user_id));

CREATE TABLE IF NOT EXISTS training_attempts(id UUID PRIMARY KEY,enrollment_id UUID NOT NULL REFERENCES training_enrollments(id),
        submission_key UUID NOT NULL,answers JSONB NOT NULL,score NUMERIC NOT NULL,passed BOOLEAN NOT NULL,receipt JSONB NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(enrollment_id,submission_key));

CREATE TABLE IF NOT EXISTS training_events(id BIGSERIAL PRIMARY KEY,programme_id UUID NOT NULL REFERENCES training_programmes(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,detail JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW());
