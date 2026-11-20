"""Rebuild site/data.json from the live products table with clean UTF-8.

Replaces the PowerShell pipeline whose cp1252 round-trip corrupted Persian
titles/categories. Only the final consumer price in Toman and a boolean stock flag are published.
"""
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402
OUT = ROOT / "site" / "data.json"


def public_image_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or "\\\\" in value or any(ord(ch) < 32 or ch.isspace() for ch in value):
        return None
    if value.startswith("/") and not value.startswith("//"):
        return value
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return None
    if (parsed.scheme.lower() == "https" and parsed.hostname
            and parsed.username is None and parsed.password is None):
        return value
    return None


def main() -> int:
    with engine.connect() as conn:
        rows = conn.execute(text(
            """
            SELECT p.code, p.name,
                   COALESCE(NULLIF(m.site_category, ''), p.category) AS category,
                   p.price, p.stock, m.image_url
            FROM products p
            LEFT JOIN cms_product_meta m ON m.code = p.code
            WHERE p.is_active = 1 AND COALESCE(m.hidden, FALSE) = FALSE
              AND COALESCE(p.name, '') <> ''
            ORDER BY p.name
            """
        )).mappings().all()
    products = []
    for row in rows:
        price = row["price"]
        try:
            numeric_price = float(price) if price is not None else None
            base_toman = (math.floor(numeric_price / 10 + 0.5)
                          if numeric_price is not None and math.isfinite(numeric_price) and numeric_price >= 0
                          else None)
        except (TypeError, ValueError, OverflowError):
            base_toman = None
        consumer_price = math.floor(base_toman * 1.15 + 0.5) if base_toman is not None else None
        products.append({
            "holoo_code": row["code"],
            "title": row["name"],
            "category": row["category"] or "بدون دسته",
            "image_url": public_image_url(row["image_url"]),
            "consumer_price_toman": consumer_price,
            "in_stock": float(row["stock"] or 0) > 0,
        })
    payload = {
        "store": {"name": "Ordibeauty", "tagline": "اردی‌بیوتی — زیبایی اورجینال، با قیمت و موجودی زنده"},
        "currency": "TOMAN",
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": "postgres.products",
        "products": products,
    }
    temporary = OUT.with_name(OUT.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(OUT)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"wrote {OUT} with {len(products)} products (clean UTF-8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
