"""Read raw invoice schemas to identify explicit salesperson evidence; no writes."""
import json
import csv
import re
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from db import engine
from holoo_router import login_holoo, get_holoo
from holoo_finance import records

with engine.connect() as conn:
    payload = conn.execute(text("SELECT payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1")).scalar_one()
    unassigned = conn.execute(text("SELECT count(*) FROM sales WHERE holoo_erp_code IS NOT NULL AND salesperson_id IS NULL")).scalar_one()
    assignment_rows = [dict(r) for r in conn.execute(text("SELECT id, holoo_kind, holoo_erp_code, holoo_sanad, date FROM sales WHERE holoo_erp_code IS NOT NULL AND salesperson_id IS NULL ORDER BY date,id")).mappings()]
token = login_holoo()
report = {"unassigned_documents": unassigned, "erp_writes": False, "local_assignments": 0, "feeds": []}
for kind in (2, 4):
    keys, candidates = Counter(), Counter()
    total = 0
    complete = False
    for page in range(1, 26):
        data = get_holoo(f"/Invoice/Invoice?type={kind}&Date.from={payload['from_date']}&Date.to={payload['to_date']}&page={page}&itemsperpage=200", token, timeout=30)
        rows = records(data, ("invoice", "Invoice"))
        for row in rows:
            keys.update(row.keys())
            for key, value in row.items():
                if re.search(r"sales.?person|sales.?man|visitor|seller|agent|بازاریاب|ویزیتور|فروشنده", key, re.I) and value not in (None, "", 0):
                    candidates[key] += 1
        total += len(rows)
        if len(rows) < 200:
            complete = True
            break
    report["feeds"].append({"kind": kind, "documents": total, "complete": complete, "keys": sorted(keys), "explicit_candidate_fields": dict(candidates)})
target = Path(__file__).resolve().parents[1] / "docs" / "invoice-salesperson-field-audit-20261102.json"
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
export = target.parents[1] / "private_exports" / "invoice-salesperson-assignment-20261102.csv"
export.parent.mkdir(exist_ok=True)
with export.open("w", encoding="utf-8-sig", newline="") as output:
    writer = csv.writer(output)
    writer.writerow(["sale_id", "holoo_kind", "holoo_erp_code", "invoice_number", "date", "salesperson_id"])
    for row in assignment_rows:
        cells = [row["id"], row["holoo_kind"], row["holoo_erp_code"], row["holoo_sanad"], row["date"], ""]
        writer.writerow([("'" + str(v)) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in cells])
print(json.dumps(report, ensure_ascii=True))
