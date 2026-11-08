"""Read the last stored Holoo snapshot in a read-only DB transaction.

Print/save aggregate validation only: no parties, invoice identifiers, product
identifiers, credentials, or network requests to Holoo.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import jdatetime
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(ROOT / ".env", override=False)
from db import engine
from purchase_profit import estimate_purchase_profit


def number(value):
    translated = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    result = Decimal(translated.replace(",", "").replace("٬", ""))
    if not result.is_finite():
        raise ValueError("nonfinite")
    return result


def rounded(value):
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def month_of(value):
    normalized = str(value).replace("/", "-")[:10]
    year, month, day = map(int, normalized.split("-"))
    return jdatetime.date(year, month, day).strftime("%Y-%m") if year < 1700 else jdatetime.date.fromgregorian(year=year, month=month, day=day).strftime("%Y-%m")


def run():
    with engine.connect() as conn:
        with conn.begin():
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql("SET LOCAL statement_timeout = '15s'")
            row = conn.execute(text("SELECT id,captured_at,payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1")).mappings().one()
    payload = dict(row["payload"])
    kinds = ("purchases", "sales", "purchase_returns", "sales_returns")
    payload["invoice_amount_semantics"] = {
        kind: {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"}
        for kind in kinds}
    result = estimate_purchase_profit(payload, monthly_expense_irr=3000000000)
    independent = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    factor = number(payload["currency_factor"])
    for kind in kinds:
        for invoice in payload["sources"][kind]["rows"]:
            month = month_of(invoice["Date"])
            gross = number(invoice["SumPrice"]) * factor
            discount = number(invoice.get("SumDiscount", 0)) * factor
            net = gross - discount
            if kind == "sales":
                independent[month]["net_sales_irr"] += net
                independent[month]["sales_gross_irr"] += gross
                independent[month]["sales_discount_irr"] += discount
            elif kind == "sales_returns":
                independent[month]["net_sales_irr"] -= net
                independent[month]["sales_return_net_irr"] += net
            elif kind == "purchases":
                independent[month]["purchase_gross_irr"] += gross
                independent[month]["purchase_discount_irr"] += discount
                independent[month]["purchase_net_irr"] += net
            else:
                independent[month]["purchase_return_net_irr"] += net
    checks = []
    for month in result["months"]:
        for key in ("net_sales_irr", "sales_gross_irr", "sales_discount_irr", "sales_return_net_irr",
                    "purchase_gross_irr", "purchase_discount_irr", "purchase_net_irr", "purchase_return_net_irr"):
            actual, expected = month.get(key), rounded(independent[month["month"]][key])
            checks.append({"month": month["month"], "metric": key, "actual": actual,
                           "expected": expected, "matched": actual == expected})
    reasons_by_month = defaultdict(Counter)
    for blocker in result["blockers"]:
        reasons_by_month[blocker.get("month", "global")][blocker["code"]] += 1
    allowed_month_keys = ("month", "days_in_month", "covered_days", "partial_month", "sales_invoices",
                          "sales_return_invoices", "sales_lines", "costed_sales_lines", "purchase_invoices",
                          "purchase_return_invoices", "net_sales_irr", "purchase_gross_irr", "purchase_discount_irr",
                          "purchase_net_irr", "purchase_return_net_irr", "sales_gross_irr", "sales_discount_irr",
                          "sales_return_net_irr", "estimated_cogs_irr", "estimated_net_profit_irr",
                          "estimated_profit_before_unverified_purchase_tax_irr", "coverage_complete",
                          "purchase_tax_policy_verified_for_costed_sales", "budget_full_month_expense_irr",
                          "budget_expense_for_period_irr")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "snapshot_id": row["id"],
              "captured_at": row["captured_at"].isoformat(), "from_date": payload["from_date"],
              "to_date": payload["to_date"], "read_only_database_transaction": True,
              "holoo_requests": 0, "financial_writes": 0,
              "source_counts": {kind: len(payload["sources"][kind]["rows"]) for kind in kinds},
              "status": result["status"], "coverage": result["coverage"],
              "opening_inventory_known": result["opening_inventory_known"],
              "approved_profit": result["approved_profit"],
              "growth_attainment_available": result["growth_attainment_available"],
              "reason_counts": dict(Counter(item["code"] for item in result["blockers"])),
              "reason_counts_by_month": {month: dict(counts) for month, counts in reasons_by_month.items()},
              "months": [{key: month.get(key) for key in allowed_month_keys} for month in result["months"]],
              "independent_arithmetic_checks": checks,
              "independent_checks_total": len(checks), "independent_checks_passed": sum(check["matched"] for check in checks),
              "independent_checks_failed": sum(not check["matched"] for check in checks),
              "limitations": result["limitations"]}
    target = ROOT / "audit-2026-10-19" / "purchase-profit-validation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("snapshot_id", "status", "coverage", "independent_checks_total", "independent_checks_passed", "independent_checks_failed")}, ensure_ascii=True, allow_nan=False))
    return 0 if report["independent_checks_failed"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        print(json.dumps({"failed": True, "error_type": type(exc).__name__}))
        sys.exit(2)
