# Kiarad database migrations

Migration files are applied in lexical order by `scripts/run_migrations.py`.

Rules:

- Use names such as `0002_add_example_column.sql`.
- Never edit an applied migration. Add a new migration instead.
- All pending migration files in one invocation run inside a single database transaction guarded by a PostgreSQL advisory transaction lock. If any migration fails, the invocation is rolled back.
- The runner stores a SHA-256 checksum and rejects changed applied files or applied versions whose source file is missing.
- `--dry-run` executes pending migration SQL in that transaction and rolls it back. `--status` creates `schema_migrations` if it does not already exist, so it is not strictly read-only on a fresh database.
- Do not put credentials or production data in migrations.

Commands:

```powershell
.\.venv\Scripts\python.exe scripts\run_migrations.py --status
.\.venv\Scripts\python.exe scripts\run_migrations.py --dry-run
.\.venv\Scripts\python.exe scripts\run_migrations.py
```


## Marketplace feeds and public catalog

- 0005_cms_product_meta.sql creates the shared CMS product metadata table when absent and adds the optional discount_price_irr column to legacy installations.
- 0006_storefront_platform_storage.sql creates the site-customer, storefront-order, banner, platform reservation/listing/proposal, platform-order/proforma, and stock-reservation tables, and adds the order idempotency/reservation columns to existing installations. Existing rows are preserved.
- Apply migrations 0005 and 0006 before deploying the storefront/CMS/platform code. HTTP requests and the storefront catalog rebuild no longer create or alter these tables.
- Verify first with python scripts/run_migrations.py --status and python scripts/run_migrations.py --dry-run against the intended environment. The migration is additive and must not be run against the company database without the normal backup and acceptance procedure.


## Employee chat and CRM storage

- 0007_chat_crm_storage.sql provisions the shared employee chat and CRM interaction tables and their indexes.
- Legacy CRM ownership is transferred only when visitor_name exactly matches one unique username, with or without the leading @. Display/full-name matching is deliberately not used. Ambiguous or unmatched rows remain unassigned and manager-visible only.
- API startup no longer creates or alters chat/CRM tables. Apply the migration through the normal backup, dry-run and release process before deploying this code.


## Visit outcomes and treasury linkage

- 0008_visit_treasury_columns.sql adds structured visit-outcome fields and the fixed-expense link used by treasury documents.
- Fresh monthly-visit tables include the same outcome fields in their startup schema definition; existing installations receive them additively from the migration.
- The reconciliation API and treasury routes no longer execute these schema changes during a request. Apply the migration before deploying this code.


## Assistant operations and scheduled automations

- 0009_assistant_operations_storage.sql provisions actor-bound assistant proposals and scheduled automation/run storage, including the due/latest indexes.
- Assistant proposal and automation request handlers no longer create or alter these tables. Apply the migration before deploying the updated API.


## Remaining startup-provisioned module schemas

- Traccar storage is provisioned by migration 0004; request handlers no longer create or alter device/shift tables.
- 0010_treasury_excel_storage.sql provisions Treasury Excel batch storage. Preview, commit, list, export, and forecasting requests do not run schema DDL.

- Apply migration 0010 before deploying Treasury Excel import and forecasting changes.


## Public customer authentication rate limits

- `0011_site_auth_rate_limits.sql` provisions shared PostgreSQL buckets for `POST /site-auth/login` and `POST /site-auth/register`; no request-time schema creation is used.
- The default limits are 10 login attempts per 15 minutes and 5 registration attempts per hour, per client IP. Exceeded requests receive HTTP 429 with a `Retry-After` header.
- Bucket keys are HMAC-SHA256 values derived from the client IP and endpoint using `KIARAD_JWT_SECRET`; raw client addresses are not stored. Stale buckets are pruned opportunistically.
- Forwarded client-IP headers are used only when the immediate peer matches an explicit CIDR in `KIARAD_TRUSTED_PROXY_CIDRS`. An empty setting means the TCP peer address is used and forwarded headers are ignored.
- Apply migration 0011 before deploying the rate-limited customer authentication code. Keep complementary rate limits at the trusted ingress.
