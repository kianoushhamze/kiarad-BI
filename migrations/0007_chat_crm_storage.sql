-- Chat and CRM storage used by authenticated employee workflows.
-- Move schema creation out of API startup; preserve legacy CRM ownership labels
-- exactly once when owner_user_id is first introduced.

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    sender VARCHAR(100),
    message TEXT,
    room VARCHAR(50) DEFAULT 'general',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attachment_key VARCHAR(80),
    attachment_name VARCHAR(180),
    attachment_type VARCHAR(120),
    attachment_size BIGINT
);

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_key VARCHAR(80);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_name VARCHAR(180);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(120);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachment_size BIGINT;

CREATE TABLE IF NOT EXISTS customer_interactions (
    id SERIAL PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    visitor_name VARCHAR(100),
    interaction_type VARCHAR(50),
    product_discussed VARCHAR(150),
    notes TEXT,
    next_followup_date DATE,
    followup_time VARCHAR(20),
    status VARCHAR(50) NOT NULL DEFAULT 'در انتظار تماس',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    owner_user_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_customer_interactions_followup
    ON customer_interactions(next_followup_date, status);

DO $$
DECLARE
    had_owner BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM pg_attribute
        WHERE attrelid = 'customer_interactions'::regclass
          AND attname = 'owner_user_id'
          AND NOT attisdropped
    ) INTO had_owner;

    IF NOT had_owner THEN
        ALTER TABLE customer_interactions ADD COLUMN owner_user_id INTEGER;

        -- Resolve only unambiguous legacy labels. Ambiguous/unmatched labels
        -- stay manager-only; future display-name changes never transfer ownership.
        WITH candidates AS (
            SELECT ci.id, MIN(u.id) AS user_id
            FROM customer_interactions ci
            JOIN users u ON (
                (ci.visitor_name LIKE '@%' AND ci.visitor_name = '@' || u.username)
                OR (ci.visitor_name NOT LIKE '@%' AND ci.visitor_name = u.full_name)
            )
            GROUP BY ci.id
            HAVING COUNT(*) = 1
        )
        UPDATE customer_interactions ci
        SET owner_user_id = candidates.user_id
        FROM candidates
        WHERE ci.id = candidates.id;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_customer_interactions_owner
    ON customer_interactions(owner_user_id);
