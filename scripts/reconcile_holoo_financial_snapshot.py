"""Independent source reconciliation. Output counts/check results, never personal rows."""
import json
from pathlib import Path
import sys
from decimal import Decimal
import re
from datetime import date
import jdatetime
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)
from db import engine
from holoo_finance import summarize_snapshot


with engine.connect() as connection:
    row = connection.execute(text("SELECT id,payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1")).mappings().one()
payload = row["payload"]
factor = Decimal(str(payload["currency_factor"]))
sources = payload["sources"]
start, end = date.fromisoformat(payload["from_date"]), date.fromisoformat(payload["to_date"])
findings = []
displayed_sources = {item["kind"]: item for item in summarize_snapshot(payload)["sources"]}
for kind in ("purchases", "sales", "purchase_returns", "sales_returns"):
    source = sources[kind]
    records = source["rows"]
    keys, invalid_dates, outside, invalid_amounts, missing_details, invalid_lines = set(), 0, 0, 0, 0, 0
    duplicate_keys, amount_total = 0, Decimal(0)
    for invoice in records:
        key = str(invoice.get("ErpCode") or invoice.get("SanadCode") or "")
        duplicate_keys += int(not key or key in keys)
        keys.add(key)
        try:
            y,m,d = map(int, re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(invoice.get("Date", ""))).groups())
            actual_date = jdatetime.date(y,m,d).togregorian() if y < 1700 else date(y,m,d)
            outside += int(not start <= actual_date <= end)
        except (ValueError, AttributeError):
            invalid_dates += 1
        try:
            amount = Decimal(str(invoice["SumPrice"]))
            if not amount.is_finite() or amount < 0: raise ValueError()
            amount_total += amount * factor
        except (KeyError, ValueError):
            invalid_amounts += 1
        details = invoice.get("Detail", [])
        missing_details += int(not details)
        for item in details:
            try:
                price, quantity = Decimal(str(item["Price"])), Decimal(str(item["Few"]))
                if not price.is_finite() or not quantity.is_finite() or price < 0 or quantity < 0:
                    raise ValueError()
            except (KeyError, ValueError):
                invalid_lines += 1
    findings.append({"source":kind,"rows":len(records),"duplicate_or_missing_keys":duplicate_keys,
                     "invalid_dates":invalid_dates,"outside_requested_period":outside,"invalid_amounts":invalid_amounts,
                     "missing_details":missing_details,"invalid_detail_price_or_quantity":invalid_lines,
                     "collection_complete":source["complete"],"amounts_recomputed_independently":True,
                     "displayed_total_matches_source": displayed_sources[kind]["total_irr"] is not None and abs(amount_total - Decimal(str(displayed_sources[kind]["total_irr"]))) <= Decimal("0.5"),
                     "displayed_row_count_matches":displayed_sources[kind]["count"] == len(records)})
report = {"snapshot_id":row["id"],"source_currency_verified":payload["currency_factor"] in (1,10),
          "financial_writes":False,"checks":findings,
          "profit_validation":"unavailable_without_historical_cogs_and_complete_expenses"}
output = ROOT / "audit-2026-10-19" / "holoo-financial-reconciliation.json"
output.write_text(json.dumps(report, ensure_ascii=False, indent=2),encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))
