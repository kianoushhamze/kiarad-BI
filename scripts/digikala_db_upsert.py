"""Upsert the scheduled Digikala variant pulls (logs/digikala_variants_p*.json)
into the existing digikala_variants table (dkp_id-keyed schema), applying the
reviewed holoo_code mappings from scripts/variant_map.csv.

Run by scripts/digikala_sync_task.ps1 right after a successful pull, so the
dashboard and public site read variants/prices from the database instead of
log files.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from iran_time import iran_now  # noqa: E402

from db import engine  # noqa: E402


def load_mappings() -> dict:
    """dkp_id (supplier_code column) -> holoo_code, from the reviewed variant_map.csv."""
    mapping: dict[str, str] = {}
    path = ROOT / "scripts" / "variant_map.csv"
    if not path.exists():
        return mapping
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            supplier, holoo = row[0].strip(), row[1].strip()
            if not supplier or not holoo or supplier.lower() == "supplier_code" or supplier.startswith("#"):
                continue
            if supplier in mapping and mapping[supplier] != holoo:
                print(f"ambiguous mapping for {supplier}; first wins", flush=True)
                continue
            mapping[supplier] = holoo
    return mapping


def main() -> int:
    mapping = load_mappings()
    upserted = 0
    files = sorted(ROOT.glob("logs/digikala_variants_p*.json"))
    if not files:
        print("no variant dumps found", flush=True)
        return 0
    now = iran_now()
    with engine.begin() as conn:
        # ON CONFLICT needs a real unique constraint; add it idempotently.
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_digikala_variants_dkp ON digikala_variants(dkp_id)"))
        for path in files:
            try:
                payload = json.load(open(path, encoding="utf-8-sig"))
            except Exception as exc:
                print(f"skip {path.name}: {type(exc).__name__}", flush=True)
                continue
            items = ((payload.get("data") or {}).get("items")) or []
            for item in items:
                dkp_id = item.get("product_id")
                if not dkp_id:
                    continue
                active = bool(item.get("active", True)) and not bool(item.get("is_archived"))
                conn.execute(text("""
                    INSERT INTO digikala_variants
                        (dkp_id, title, holoo_code, status, price_selling, stock, source, raw, updated_at)
                    VALUES (:dkp, :title, :hc, :status, :price, :stock, 'sync_task',
                            CAST(:raw AS JSONB), :updated)
                    ON CONFLICT (dkp_id) DO UPDATE SET
                        title=EXCLUDED.title,
                        holoo_code=COALESCE(digikala_variants.holoo_code, EXCLUDED.holoo_code),
                        status=EXCLUDED.status,
                        price_selling=EXCLUDED.price_selling,
                        stock=EXCLUDED.stock,
                        source='sync_task',
                        raw=EXCLUDED.raw,
                        updated_at=EXCLUDED.updated_at
                """), {
                    "dkp": dkp_id,
                    "title": (item.get("product_title") or item.get("title") or "")[:500],
                    "hc": mapping.get(str(dkp_id)),
                    "status": "active" if active else "inactive",
                    "price": item.get("cash_selling_price") or item.get("price_sale") or 0,
                    "stock": item.get("marketplace_seller_stock") or 0,
                    "raw": json.dumps(item, ensure_ascii=False),
                    "updated": now,
                })
                upserted += 1
    print(f"upserted {upserted} variant rows at {now.isoformat()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
