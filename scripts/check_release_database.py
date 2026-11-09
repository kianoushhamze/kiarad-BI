"""Read-only prerequisite check: baseline does not bootstrap a production DB."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from db import engine

REQUIRED = ("users", "products", "customers")


def missing_tables(connection):
    return [name for name in REQUIRED if connection.execute(
        text("SELECT to_regclass(:table_name)"),
        {"table_name": "public." + name},
    ).scalar() is None]


def main():
    try:
        with engine.connect() as connection:
            missing = missing_tables(connection)
    except SQLAlchemyError:
        print(json.dumps({"status": "failed", "reason": "database_unavailable"}))
        return 1
    if missing:
        print(json.dumps({"status": "failed", "reason": "restore_required", "missing_tables": missing}))
        return 1
    print(json.dumps({"status": "passed", "scope": "core_tables_present_only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
