"""Scheduled platform stock reconciler (run every 5 minutes).

1. Poll recent Digikala orders; ingest each into platform reservations.
2. Push recomputed available stock + prices for every active listing.

Runs on the host (needs network + secrets) and writes to the same Postgres.
Failures are soft: the next cycle retries; nothing destructive.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from platform_sync import apply_order, push_stock_many, _dk_client  # noqa: E402
from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402
LOG = ROOT / "logs" / "platform_stock_task.log"


def log(message: str) -> None:
    line = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + message
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def extract_items(order: dict) -> list[dict]:
    """Heuristic: Digikala order payloads nest items under several shapes."""
    data = order.get("data") or order
    candidates = (data.get("order_items") or data.get("items")
                  or (data.get("order") or {}).get("order_items") or [])
    items = []
    for entry in candidates:
        variant = entry.get("variant") or entry
        dkp = (variant.get("product_id") or entry.get("dkp_id")
               or entry.get("product_id") or variant.get("dkp_id"))
        qty = entry.get("quantity") or entry.get("qty") or 1
        if dkp:
            items.append({"dkp": int(dkp), "qty": int(qty), "status": entry.get("status")})
    return items


def dkp_to_code(conn, dkp: int) -> str | None:
    return conn.execute(text(
        "SELECT holoo_code FROM digikala_variants WHERE dkp_id=:d AND holoo_code IS NOT NULL "
        "ORDER BY updated_at DESC NULLS LAST LIMIT 1"), {"d": dkp}).scalar()


def main() -> int:
    with engine.begin() as conn:
    try:
        client = _dk_client()
        probe = client.get_profile()
        if probe.status_code != 200:
            log(f"gate closed ({probe.status_code}); skipping cycle")
            return 0
    except Exception as exc:
        log(f"gate error {type(exc).__name__}; skipping cycle")
        return 0

    ingested = 0
    for page in (1, 2):
        try:
            resp = client.get_orders(page=page, size=30)
            if resp.status_code != 200:
                log(f"orders page {page} http {resp.status_code}")
                continue
            payload = resp.json()
            data = payload.get("data") or payload
            orders = data.get("orders") or data.get("items") or []
            for order in orders:
                order_ref = str(order.get("id") or order.get("order_id") or "")
                if not order_ref:
                    continue
                status = str(order.get("status") or "")
                items = extract_items(order)
                if not items:
                    # order detail may carry the lines; store raw anyway
                    with engine.begin() as conn:
                        conn.execute(text("""INSERT INTO platform_orders_raw(platform, order_ref, status, raw)
                            VALUES ('digikala',:r,:s,CAST(:raw AS JSONB))
                            ON CONFLICT (platform, order_ref) DO UPDATE SET raw=EXCLUDED.raw, fetched_at=NOW()"""),
                            {"r": order_ref, "s": status, "raw": json.dumps(order, ensure_ascii=False)})
                    continue
                resolved = []
                with engine.connect() as conn:
                    for item in items:
                        code = dkp_to_code(conn, item["dkp"])
                        if code:
                            resolved.append({"code": code, "qty": item["qty"]})
                if resolved:
                    result = apply_order("digikala", order_ref, resolved, status)
                    ingested += 1
                    log(f"order {order_ref}: reserved={result.get('reserved')}")
        except Exception as exc:
            log(f"orders page {page} failed {type(exc).__name__}")
    with engine.begin() as conn:
        codes = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT code FROM platform_listings WHERE active")).all()]
    pushed = push_stock_many(codes)
    log(f"ingested={ingested} pushed={len(pushed)} errors={[p['errors'] for p in pushed if p['errors']]}")
    return 0


from datetime import datetime  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
