"""Rebuild site/data.json from the live products table with clean UTF-8.

Replaces the PowerShell pipeline whose cp1252 round-trip corrupted Persian
titles/categories. Prices are stored in Toman (Rial / 10) as the site expects.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db import engine  # noqa: E402
OUT = ROOT / "site" / "data.json"


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
        products.append({
            "holoo_code": row["code"],
            "title": row["name"],
            "category": row["category"] or "بدون دسته",
            "image_url": row["image_url"],
            "price_holoo": round(price / 10) if price is not None else None,
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
