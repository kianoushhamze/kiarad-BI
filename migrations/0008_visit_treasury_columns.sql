-- Additive columns for structured visit outcomes and treasury expense linkage.
-- IF EXISTS keeps the migration safe for installations where a module is not yet provisioned.

ALTER TABLE IF EXISTS monthly_visit_plan_stops
    ADD COLUMN IF NOT EXISTS outcome_status VARCHAR(50);
ALTER TABLE IF EXISTS monthly_visit_plan_stops
    ADD COLUMN IF NOT EXISTS holoo_preinvoice_code VARCHAR(100);
ALTER TABLE IF EXISTS monthly_visit_plan_stops
    ADD COLUMN IF NOT EXISTS order_amount_rial BIGINT DEFAULT 0;
ALTER TABLE IF EXISTS monthly_visit_plan_stops
    ADD COLUMN IF NOT EXISTS outcome_notes TEXT;
ALTER TABLE IF EXISTS monthly_visit_plan_stops
    ADD COLUMN IF NOT EXISTS follow_up_date DATE;

ALTER TABLE IF EXISTS financial_documents
    ADD COLUMN IF NOT EXISTS fixed_expense_id INTEGER;
