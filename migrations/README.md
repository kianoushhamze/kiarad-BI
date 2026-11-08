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
