# -*- coding: utf-8 -*-
"""Create a private UTF-8 CSV export of one day's proformas for manager review."""
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from iran_time import iran_now, iran_today

from sqlalchemy import text
from db import engine

ROOT = Path(__file__).resolve().parent
EXPORT_DIR = ROOT / "private_exports" / "proformas"


def safe_csv_cell(value):
    # User-entered names/notes must remain text when the manager opens Excel.
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def build_export(export_date: date) -> tuple[Path, int]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / ("proformas_" + export_date.isoformat() + ".csv")
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.created_at, c.name AS customer_name, sp.name AS salesperson_name,
                   p.total_amount, p.status, p.credit_grade, p.notes, p.items_json
            FROM proforma_invoices p
            LEFT JOIN customers c ON c.id=p.customer_id
            LEFT JOIN salespersons sp ON sp.id=p.salesperson_id
            WHERE p.created_at::date=:export_date
            ORDER BY p.id
        """), {"export_date": export_date}).mappings().all()
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["شماره", "زمان ثبت", "مشتری", "ویزیتور", "مبلغ ریال", "وضعیت", "اعتبار", "اقلام", "توضیحات"])
        for row in rows:
            raw_items = row.get("items_json") or []
            if isinstance(raw_items, str):
                try: raw_items = json.loads(raw_items)
                except ValueError: raw_items = []
            item_text = " | ".join(
                str(item.get("product_name") or item.get("product_id")) + " × " + str(item.get("quantity") or 0)
                for item in raw_items if isinstance(item, dict)
            )
            writer.writerow([safe_csv_cell(value) for value in [row.get("id"), row.get("created_at"), row.get("customer_name"),
                             row.get("salesperson_name"), row.get("total_amount"), row.get("status"),
                             row.get("credit_grade"), item_text, row.get("notes") or ""]])
    return path, len(rows)


if __name__ == "__main__":
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else iran_today() - timedelta(days=1)
    output_path, count = build_export(target)
    print(iran_now().isoformat(timespec="seconds"), output_path.name, count)
