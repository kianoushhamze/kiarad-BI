"""Read documented Holoo endpoints; output schema/row counts only, never tokens."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)
from holoo_router import login_holoo, get_holoo


def shape(value):
    if isinstance(value, dict):
        return {"kind": "object", "keys": list(value)[:45], "children": {key: shape(child) for key, child in value.items() if isinstance(child, (list, dict))}}
    if isinstance(value, list):
        keys = sorted({key for row in value[:50] if isinstance(row, dict) for key in row})
        return {"kind": "list", "rows": len(value), "row_keys": keys[:90]}
    return {"kind": type(value).__name__}


def main():
    report = {"source": "holoo_read_only", "financial_writes": False, "endpoints": []}
    try:
        token = login_holoo()
    except Exception as exc:
        report["login"] = {"ok": False, "error_type": type(exc).__name__}
        print(json.dumps(report))
        return 1
    report["login"] = {"ok": True}
    for path in ("/Report/GetCash", "/Payment/Account", "/Customer", "/Product"):
        started = time.monotonic()
        try:
            payload = get_holoo(path, token, timeout=25)
            result = {"path": path, "ok": True, "shape": shape(payload)}
        except Exception as exc:
            result = {"path": path, "ok": False, "error_type": type(exc).__name__}
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report["endpoints"].append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    folder = ROOT / "audit-2026-10-19"
    folder.mkdir(exist_ok=True)
    (folder / "holoo-financial-shapes.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
