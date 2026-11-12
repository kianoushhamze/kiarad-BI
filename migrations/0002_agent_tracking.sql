-- Persistent reviewed missions and consented work-shift location. No company data changes.

CREATE TABLE IF NOT EXISTS agent_missions(id UUID PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),
          title TEXT NOT NULL,objective TEXT NOT NULL,domains JSONB NOT NULL,plan JSONB NOT NULL,plan_digest TEXT NOT NULL,
          policy JSONB NOT NULL,state TEXT NOT NULL DEFAULT 'draft',approved_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          next_run_at TIMESTAMPTZ,lease_until TIMESTAMPTZ,last_monitor_at TIMESTAMPTZ);

CREATE TABLE IF NOT EXISTS agent_steps(id UUID PRIMARY KEY,mission_id UUID NOT NULL REFERENCES agent_missions(id),
          step_key TEXT NOT NULL,spec JSONB NOT NULL,state TEXT NOT NULL DEFAULT 'planned',proposal_id UUID,
          receipt JSONB,step_approved BOOLEAN NOT NULL DEFAULT FALSE,error TEXT,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(mission_id,step_key));

CREATE TABLE IF NOT EXISTS agent_events(id BIGSERIAL PRIMARY KEY,mission_id UUID NOT NULL REFERENCES agent_missions(id),
          kind TEXT NOT NULL,message TEXT NOT NULL,detail JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());

CREATE TABLE IF NOT EXISTS agent_feedback(id BIGSERIAL PRIMARY KEY,mission_id UUID NOT NULL REFERENCES agent_missions(id),
          owner_id INTEGER NOT NULL REFERENCES users(id),rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
          note TEXT NOT NULL,outcome JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());

CREATE TABLE IF NOT EXISTS agent_lessons(id BIGSERIAL PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),domain TEXT NOT NULL,
          text TEXT NOT NULL,feedback_id BIGINT NOT NULL REFERENCES agent_feedback(id),active BOOLEAN NOT NULL DEFAULT TRUE,
          version INTEGER NOT NULL DEFAULT 1,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());

CREATE TABLE IF NOT EXISTS agent_sources(id UUID PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),
          title TEXT NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL,source_date TEXT,url TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());

CREATE TABLE IF NOT EXISTS agent_alerts(id UUID PRIMARY KEY,mission_id UUID NOT NULL REFERENCES agent_missions(id),
          user_id INTEGER NOT NULL REFERENCES users(id),fingerprint TEXT NOT NULL,message TEXT NOT NULL,
          severity TEXT NOT NULL DEFAULT 'warning',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(mission_id,user_id,fingerprint));

CREATE INDEX IF NOT EXISTS agent_missions_due ON agent_missions(next_run_at) WHERE state='active';

CREATE INDEX IF NOT EXISTS agent_alerts_recipient ON agent_alerts(user_id,created_at DESC);

CREATE INDEX IF NOT EXISTS agent_steps_mission ON agent_steps(mission_id,state);

CREATE TABLE IF NOT EXISTS tracking_sessions(
        id UUID PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),device_id TEXT NOT NULL,
        platform TEXT NOT NULL,started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,ended_at TIMESTAMPTZ,consent_version TEXT NOT NULL,
        last_upload_at TIMESTAMPTZ,last_device_status TEXT NOT NULL DEFAULT 'starting');

CREATE INDEX IF NOT EXISTS tracking_sessions_owner_time ON tracking_sessions(user_id,started_at DESC);

CREATE TABLE IF NOT EXISTS tracking_points(
        id BIGSERIAL PRIMARY KEY,session_id UUID NOT NULL REFERENCES tracking_sessions(id),
        event_id UUID NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),
        recorded_at TIMESTAMPTZ NOT NULL,received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        latitude DOUBLE PRECISION NOT NULL,longitude DOUBLE PRECISION NOT NULL,
        accuracy_m DOUBLE PRECISION NOT NULL,speed_mps DOUBLE PRECISION,battery_level DOUBLE PRECISION,
        mocked BOOLEAN,UNIQUE(session_id,event_id));

CREATE INDEX IF NOT EXISTS tracking_points_owner_time ON tracking_points(user_id,recorded_at DESC,id DESC);

CREATE INDEX IF NOT EXISTS tracking_points_session_time ON tracking_points(session_id,recorded_at DESC);
