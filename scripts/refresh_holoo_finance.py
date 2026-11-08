"""Capture documented financial sources. Console contains schema/counts only."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)
from holoo_finance import refresh_financial_snapshot


def progress(kind, source):
    print(json.dumps({"source": kind, "ok": source["ok"], "rows": len(source.get("rows", [])), "complete": source["complete"], "error_type": source.get("error_type")}), flush=True)


try:
    result = refresh_financial_snapshot(progress)
    receipt = {"snapshot_id": result["id"], "currency_verified": result["currency_verified"], "from_date": result["from_date"], "to_date": result["to_date"],
               "net_profit_available": result["net_profit_available"], "sources": [{key: value for key, value in row.items() if key != "total_irr"} for row in result["sources"]], "erp_financial_writes": False}
    folder = ROOT / "audit-2026-10-19"
    folder.mkdir(exist_ok=True)
    (folder / "holoo-financial-refresh.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
    raise SystemExit(1)
