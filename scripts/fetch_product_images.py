"""Fill missing product images by searching the web (DuckDuckGo images).

Writes cms_product_meta.image_url. Bounded per run so repeated scheduled runs
gradually cover the catalog; only products WITHOUT an image are processed.
DDG rate-limits aggressively, so runs are small and slow (sleep between
queries) and are scheduled hourly as a slow drip.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import DATABASE_URL
from sqlalchemy import create_engine, text  # noqa: E402

DB_URL = DATABASE_URL
BATCH = 8
SLEEP_SECONDS = 12


def main() -> int:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        print("duckduckgo-search not installed")
        return 1
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT m.code, p.name FROM cms_product_meta m
            JOIN products p ON p.code = m.code
            WHERE COALESCE(m.image_url,'') = '' AND m.site_category <> 'متفرقه'
            ORDER BY p.stock DESC LIMIT :n
        """), {"n": BATCH}).mappings().all()
    if not rows:
        print("nothing to fetch")
        return 0
    found = 0
    with DDGS() as ddgs:
        for row in rows:
            query = row["name"][:80]
            try:
                hits = list(ddgs.images(keywords=query, max_results=3, type_image="photo"))
            except Exception as exc:
                print(f"{row['code']}: search failed {type(exc).__name__}")
                time.sleep(SLEEP_SECONDS * 3)
                continue
            time.sleep(SLEEP_SECONDS)
            url = next((h.get("image") for h in hits if h.get("image")), None)
            if url:
                with engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE cms_product_meta SET image_url=:u, updated_at=NOW() WHERE code=:c"),
                        {"u": url, "c": row["code"]})
                found += 1
                print(f"{row['code']}: image found")
            else:
                print(f"{row['code']}: no result")
    print(f"filled {found}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
