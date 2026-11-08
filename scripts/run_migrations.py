"""Apply ordered, checksum-protected PostgreSQL migrations."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
sys.path.insert(0, str(ROOT))
NAME_PATTERN = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
LOCK_ID = 4_502_601_101


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migration_files() -> list[Path]:
    files = sorted(path for path in MIGRATIONS.glob("*.sql") if NAME_PATTERN.match(path.name))
    if not files:
        raise RuntimeError("migration_files_missing")
    duplicates = [name for name in {path.name[:4] for path in files}
                  if sum(path.name.startswith(name + "_") for path in files) > 1]
    if duplicates:
        raise RuntimeError("duplicate_migration_version")
    return files


def connection():
    load_dotenv(ROOT / ".env")
    from config import DB_CONFIG
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        connect_timeout=10,
    )


def ensure_history(cur) -> None:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def inspect(cur, files: list[Path]) -> tuple[list[dict], list[dict]]:
    cur.execute("SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version")
    applied = {row[0]: {"checksum": row[1], "applied_at": row[2].isoformat()} for row in cur.fetchall()}
    pending = []
    known = []
    for path in files:
        digest = checksum(path)
        record = applied.get(path.name)
        if record and record["checksum"] != digest:
            raise RuntimeError("applied_migration_checksum_changed:" + path.name)
        item = {"version": path.name, "checksum": digest}
        if record:
            known.append({**item, "applied_at": record["applied_at"]})
        else:
            pending.append(item)
    unknown = sorted(set(applied) - {path.name for path in files})
    if unknown:
        raise RuntimeError("applied_migration_file_missing:" + ",".join(unknown))
    return known, pending


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    files = migration_files()
    report = {"status": "failed", "dry_run": args.dry_run, "applied": [], "pending": []}
    conn = connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
                ensure_history(cur)
                known, pending = inspect(cur, files)
                report.update(status="checked", known=len(known), pending=[item["version"] for item in pending])
                if args.status or args.dry_run:
                    if args.dry_run:
                        conn.rollback()
                    print(json.dumps(report, ensure_ascii=True))
                    return 0
                for item in pending:
                    path = MIGRATIONS / item["version"]
                    cur.execute(path.read_text(encoding="utf-8-sig"))
                    cur.execute(
                        "INSERT INTO schema_migrations(version, checksum) VALUES(%s, %s)",
                        (item["version"], item["checksum"]),
                    )
                    report["applied"].append(item["version"])
                report["status"] = "completed"
                report["pending"] = []
        print(json.dumps(report, ensure_ascii=True))
        return 0
    except Exception as exc:
        conn.rollback()
        report["error_type"] = type(exc).__name__
        print(json.dumps(report, ensure_ascii=True))
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
