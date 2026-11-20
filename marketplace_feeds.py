"""Public, read-only product feeds for Iranian price-comparison engines.

Torob and Emalls crawl or poll a store URL; they never need credentials from
us. The feeds expose only what the public storefront already shows (name,
price, availability, image, URL) - no cost price, no customer data, no stock
numbers (only instock/outofstock).

Torob: JSON in the "API v2" shape (count/max_pages/products, single-product
lookup by page_unique or page_url, GET and POST). The exact acceptance test is
done by Torob's team after the store is registered, so treat the shape as
"prepared", not "approved".
Generic: products.json and products.csv for any other channel.
"""
import csv
import io
import os
from typing import Any, Iterable, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db import engine
from stock_reservations import reservation_totals

router = APIRouter(prefix="/public/feeds", tags=["marketplace_feeds"])

PAGE_SIZE = 100
DEFAULT_BASE_URL = "https://shop.kiaradhealer.ir"


def site_base_url() -> str:
    return (os.getenv("KIARAD_SITE_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")


def _absolute(url: Optional[str], base: str) -> str:
    if not url:
        return ""
    url = str(url).strip()
    if url.startswith(("http://", "https://")):
        return url
    return base + "/" + url.lstrip("/")


def _toman(irr: Any) -> int:
    try:
        return int(round(float(irr) / 10))
    except (TypeError, ValueError):
        return 0


def build_item(row: dict, base: str, available: float) -> Optional[dict]:
    """Map one catalog row to a feed item; None when it must not be published."""
    price_irr = row.get("price")
    if not price_irr or float(price_irr) <= 0:
        return None
    discount = row.get("discount_price_irr")
    use_discount = discount is not None and 0 < float(discount) < float(price_irr)
    code = str(row["code"])
    image = _absolute(row.get("image_url"), base)
    return {
        "title": str(row.get("name") or code).strip(),
        "subtitle": "",
        "page_unique": code,
        "page_url": f"{base}/buy/?p={code}",
        "current_price": _toman(discount if use_discount else price_irr),
        "old_price": _toman(price_irr) if use_discount else 0,
        "availability": "instock" if available > 0 else "outofstock",
        "image_link": image,
        "image_links": [image] if image else [],
        "category_name": str(row.get("category") or ""),
        "guarantee": "ضمانت اصالت کالا",
        "short_desc": "",
    }


def page_slice(items: list, page: int, size: int = PAGE_SIZE) -> dict:
    page = max(1, page)
    max_pages = max(1, -(-len(items) // size))
    start = (page - 1) * size
    chunk = items[start:start + size]
    return {"count": len(chunk), "max_pages": max_pages, "products": chunk}


CSV_COLUMNS = ["page_unique", "title", "category_name", "current_price", "old_price", "availability", "page_url", "image_link"]


def to_csv(items: Iterable[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow(item)
    return "\ufeff" + out.getvalue()


def load_items() -> list[dict]:
    base = site_base_url()
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT p.id, p.code, p.name,
                       COALESCE(NULLIF(m.site_category, ''), p.category) AS category,
                       p.price, p.stock, m.image_url, m.discount_price_irr
                FROM products p
                LEFT JOIN cms_product_meta m ON m.code = p.code
                WHERE p.is_active = 1 AND COALESCE(m.hidden, FALSE) = FALSE
                ORDER BY p.code""")).mappings().all()
            totals = reservation_totals(conn, [r["id"] for r in rows])
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="feed unavailable")
    items = []
    for row in rows:
        available = max(0.0, float(row["stock"] or 0) - totals.get(row["id"], 0))
        item = build_item(dict(row), base, available)
        if item:
            items.append(item)
    return items


def _find_single(items: list[dict], page_unique: Optional[str], page_url: Optional[str]) -> Optional[dict]:
    for item in items:
        if page_unique and item["page_unique"] == page_unique:
            return item
        if page_url and item["page_url"].rstrip("/") == page_url.strip().rstrip("/"):
            return item
    return None


def _json_headers(response: Response):
    response.headers["Cache-Control"] = "no-store"


@router.get("/torob")
def torob_get(response: Response, page: int = Query(1, ge=1, le=10000),
              page_unique: Optional[str] = None, page_url: Optional[str] = None):
    _json_headers(response)
    items = load_items()
    if page_unique or page_url:
        found = _find_single(items, page_unique, page_url)
        return {"count": 1 if found else 0, "max_pages": 1, "products": [found] if found else []}
    return page_slice(items, page)


@router.post("/torob")
async def torob_post(request: Request, response: Response):
    """Single-product lookup (and paging) via JSON or form body."""
    _json_headers(response)
    data: dict = {}
    try:
        if "json" in (request.headers.get("content-type") or ""):
            data = await request.json()
        else:
            data = dict(await request.form())
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    items = load_items()
    unique, url = data.get("page_unique"), data.get("page_url")
    if unique or url:
        found = _find_single(items, str(unique) if unique else None, str(url) if url else None)
        return {"count": 1 if found else 0, "max_pages": 1, "products": [found] if found else []}
    try:
        page = int(data.get("page") or 1)
    except (TypeError, ValueError):
        page = 1
    return page_slice(items, page)


@router.get("/products.json")
def products_json(response: Response):
    _json_headers(response)
    items = load_items()
    return {"currency": "IRT", "count": len(items), "products": items}


@router.get("/products.csv")
def products_csv():
    return Response(to_csv(load_items()), media_type="text/csv; charset=utf-8",
                    headers={"Cache-Control": "no-store"})
