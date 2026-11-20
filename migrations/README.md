# Kiarad database migrations

Migration files are applied in lexical order by `scripts/run_migrations.py`.

Rules:

- Use names such as `0002_add_example_column.sql`.
- Never edit an applied migration. Add a new migration instead.
- Each file runs in its own transaction.
- The runner stores a SHA-256 checksum and rejects changed applied files.
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
- Existing CRM rows are assigned to an employee only when the legacy visitor label maps unambiguously to exactly one user. Ambiguous or unmatched rows remain unassigned and manager-visible only.
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
