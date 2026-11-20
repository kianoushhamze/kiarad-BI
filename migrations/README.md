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
- Apply the migration before deploying code that reads the public catalog or Torob/Emalls feeds. Public GET requests no longer attempt schema changes.
- Verify first with python scripts/run_migrations.py --status and python scripts/run_migrations.py --dry-run against the intended environment. The migration is additive and must not be run against the company database without the normal backup and acceptance procedure.
