"""Multi-platform virtual inventory & price management.

Central available stock = Holoo stock minus active reservations. When any
platform's order consumes an item, reservations rise and the new available
count is pushed to every connected platform (no overselling). Prices per
platform are 'auto' (from Holoo, optional factor), 'manual', or Excel-imported.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from stock_reservations import lock_products, reservation_totals, reserved_quantity
from operations import current_user, role_has_module_permission

logger = logging.getLogger("kiarad_platforms")
router = APIRouter(prefix="/platforms", tags=["platforms"])

PLATFORMS = ["digikala", "site"]  # extend with basalam, torob, ... as connectors land


def ensure(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_listings(
        id SERIAL PRIMARY KEY, platform TEXT NOT NULL, code TEXT NOT NULL,
        external_id TEXT, price_mode TEXT NOT NULL DEFAULT 'auto',
        manual_price_irr BIGINT, price_factor NUMERIC(6,3) DEFAULT 1.0,
        active BOOLEAN NOT NULL DEFAULT TRUE, last_push_at TIMESTAMPTZ,
        UNIQUE(platform, code))"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_reservations(
        id SERIAL PRIMARY KEY, platform TEXT NOT NULL, external_ref TEXT NOT NULL,
        code TEXT NOT NULL, qty INT NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(platform, external_ref, code))"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_orders_raw(
        id SERIAL PRIMARY KEY, platform TEXT NOT NULL, order_ref TEXT NOT NULL,
        status TEXT, raw JSONB, fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(platform, order_ref))"""))
    # Side table linking platform orders to internal proforma drafts.
    # Holoo is NEVER written from this flow: the owner invoices manually in
    # Holoo and then ticks holoo_registered in the dashboard.
    # Product-creation proposals are drafts for manual Seller Center listing.
    # Seller Open API v1 has no verified create route; variants are mapped only
    # after the seller creates the listing manually. Never issue a guessed POST.
    conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_create_proposals(
        id SERIAL PRIMARY KEY, platform TEXT NOT NULL DEFAULT 'digikala',
        code TEXT NOT NULL, product_name TEXT NOT NULL,
        suggested_title TEXT NOT NULL, category_id BIGINT,
        price_irr BIGINT, stock INT NOT NULL DEFAULT 0,
        image_url TEXT, gtin TEXT, notes TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        payload JSONB, receipt JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        confirmed_at TIMESTAMPTZ)"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS platform_order_proformas(
        id SERIAL PRIMARY KEY, platform TEXT NOT NULL, order_ref TEXT NOT NULL,
        proforma_id INTEGER NOT NULL, source TEXT NOT NULL DEFAULT 'platform',
        status TEXT NOT NULL DEFAULT 'draft',
        holoo_registered BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(platform, order_ref))"""))


def _require_manager(user):
    if user.get("role") != "ceo" and not role_has_module_permission(str(user.get("role", "")), "online-sales", "can_write"):
        raise HTTPException(403, "این عملیات فقط برای مدیر فروش آنلاین است.")


def _ensure_platform_proforma_storage(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS proforma_invoices (
        id SERIAL PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        salesperson_id INTEGER REFERENCES salespersons(id),
        total_amount NUMERIC(18, 2) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        credit_grade VARCHAR(20),
        notes TEXT,
        items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))


def _platform_customer_id(conn, platform: str) -> int:
    """Find-or-create the internal customer used for platform order drafts."""
    code = "PLATFORM:" + platform
    name = "سکوی " + ("سایت کیاراد" if platform == "site" else platform)
    row = conn.execute(text("SELECT id FROM customers WHERE code=:c"), {"c": code}).scalar()
    if row:
        return int(row)
    return int(conn.execute(text(
        "INSERT INTO customers(code, name, credit_limit) VALUES (:c,:n,0) "
        "ON CONFLICT(code) DO UPDATE SET code=EXCLUDED.code RETURNING id"),
        {"c": code, "n": name}).scalar())


def _create_platform_order_proforma(conn, platform: str, order_ref: str, items: list[dict]) -> int:
    """Create one internal proforma DRAFT per order. This never writes to Holoo;
    the official invoice is made manually in Holoo by the owner."""
    existing = conn.execute(text("""SELECT op.proforma_id, op.holoo_registered,
        p.status AS invoice_status FROM platform_order_proformas op
        JOIN proforma_invoices p ON p.id=op.proforma_id
        WHERE op.platform=:p AND op.order_ref=:r FOR UPDATE OF op, p"""),
        {"p": platform, "r": order_ref}).mappings().first()
    if existing and (existing["holoo_registered"] or existing["invoice_status"] != "draft"):
        # Never rewrite a manually approved/registered financial document.
        return int(existing["proforma_id"])
    customer_id = _platform_customer_id(conn, platform)
    normalized, total = [], 0.0
    for item in items:
        code = item.get("code")
        qty = int(item.get("qty") or 0)
        if not code or qty <= 0:
            continue
        product = conn.execute(text("SELECT id, name, price FROM products WHERE code=:c"),
                               {"c": code}).mappings().first()
        if not product:
            continue
        price = item.get("price_irr")
        if price in (None, ""):
            listing = conn.execute(text(
                "SELECT price_mode, manual_price_irr, price_factor FROM platform_listings "
                "WHERE platform=:p AND code=:c"), {"p": platform, "c": code}).mappings().first()
            if listing:
                price = target_price_irr(conn, listing)
        unit_price = float(price) if price not in (None, "") else float(product["price"] or 0)
        line_total = unit_price * qty
        total += line_total
        normalized.append({"product_id": int(product["id"]), "product_name": product["name"],
                           "quantity": float(qty), "unit_price": unit_price, "line_total": line_total})
    if not normalized or total <= 0:
        raise ValueError("سفارش سکو قلم قابل فاکتور ندارد")
    if existing:
        proforma_id = int(existing["proforma_id"])
        conn.execute(text("""UPDATE proforma_invoices
            SET total_amount=:amount, items_json=CAST(:items AS JSONB), status='draft'
            WHERE id=:id AND status='draft'"""),
            {"id": proforma_id, "amount": total, "items": json.dumps(normalized, ensure_ascii=False)})
        conn.execute(text("""UPDATE platform_order_proformas SET status='draft'
            WHERE platform=:p AND order_ref=:r AND NOT holoo_registered"""),
            {"p": platform, "r": order_ref})
        return proforma_id
    proforma_id = int(conn.execute(text("""
        INSERT INTO proforma_invoices(customer_id, salesperson_id, total_amount, status, credit_grade, notes, items_json)
        VALUES (:cid, NULL, :amount, 'draft', NULL, :notes, CAST(:items AS JSONB))
        RETURNING id"""), {
            "cid": customer_id, "amount": total,
            "notes": f"پیش‌نویس سفارش سکو {platform} / {order_ref} — ثبت رسمی فاکتور دستی در هلو انجام می‌شود.",
            "items": json.dumps(normalized, ensure_ascii=False),
        }).scalar())
    conn.execute(text("""INSERT INTO platform_order_proformas(platform, order_ref, proforma_id, source, status, holoo_registered)
        VALUES (:p,:r,:pid,'platform','draft',FALSE)
        ON CONFLICT (platform, order_ref) DO UPDATE SET proforma_id=EXCLUDED.proforma_id"""),
        {"p": platform, "r": order_ref, "pid": proforma_id})
    return proforma_id


def holoo_stock(conn, code: str) -> float:
    return float(conn.execute(text("SELECT COALESCE(stock,0) FROM products WHERE code=:c"), {"c": code}).scalar() or 0)


def reserved_count(conn, code: str) -> float:
    product_id = conn.execute(text('SELECT id FROM products WHERE code=:code'), {'code': code}).scalar()
    return reserved_quantity(conn, product_id) if product_id is not None else 0.0


def available_stock(conn, code: str) -> int:
    return int(max(0, holoo_stock(conn, code) - reserved_count(conn, code)))


def auto_price_irr(conn, code: str, factor=1.0) -> int | None:
    price = conn.execute(text("SELECT price FROM products WHERE code=:c"), {"c": code}).scalar()
    return int(round(price * float(factor or 1.0))) if price is not None else None


def target_price_irr(conn, listing) -> int | None:
    if listing["price_mode"] == "manual":
        return int(listing["manual_price_irr"]) if listing["manual_price_irr"] else None
    return auto_price_irr(conn, listing["code"], listing["price_factor"])


# ------------------------------------------------------------- order ingestion

def apply_order(platform: str, order_ref: str, items: list[dict], status: str | None = None) -> dict:
    """Reconcile a complete order snapshot, then publish committed stock.

    Repeated polls are idempotent. Cancellation releases all previous lines;
    reinstatement reactivates them, and removed lines stop reserving stock.
    """
    if platform not in PLATFORMS:
        raise ValueError('Unsupported platform')
    quantities: dict[str, int] = {}
    prices: dict[str, object] = {}
    for item in items:
        code = item.get("code")
        raw_qty = item.get('qty')
        if isinstance(raw_qty, bool) or (isinstance(raw_qty, float) and not raw_qty.is_integer()):
            raise ValueError('Order quantities must be integers')
        qty = int(raw_qty or 0)
        if not isinstance(code, str) or not code.strip() or not 0 < qty <= 2147483647:
            raise ValueError("Order lines require a product code and positive quantity")
        quantities[code] = quantities.get(code, 0) + qty
        if quantities[code] > 2147483647:
            raise ValueError('Combined order quantity exceeds storage range')
        if item.get("price_irr") is not None:
            if code in prices and prices[code] != item["price_irr"]:
                raise ValueError("Duplicate order lines have conflicting prices")
            prices[code] = item["price_irr"]
    normalized = [{"code": code, "qty": qty, **({"price_irr": prices[code]} if code in prices else {})}
                  for code, qty in quantities.items()]
    released = (status or "").strip().lower() in {"canceled", "cancelled", "returned"}
    if not normalized and not released:
        raise ValueError("An active order snapshot must contain at least one line")
    proforma_id: int | None = None
    with engine.begin() as conn:
        ensure(conn)
        _ensure_platform_proforma_storage(conn)
        # The unique order upsert also serializes concurrent snapshots of this order.
        conn.execute(text("""INSERT INTO platform_orders_raw(platform, order_ref, status, raw)
            VALUES (:p,:r,:s,CAST(:raw AS JSONB))
            ON CONFLICT (platform, order_ref) DO UPDATE SET status=EXCLUDED.status, raw=EXCLUDED.raw, fetched_at=NOW()"""),
            {"p": platform, "r": order_ref, "s": status, "raw": json.dumps(normalized, ensure_ascii=False)})
        previous = [row[0] for row in conn.execute(text(
            "SELECT code FROM platform_reservations WHERE platform=:p AND external_ref=:r"
        ), {"p": platform, "r": order_ref}).all()]
        lock_products(conn, codes=set(previous) | set(quantities))
        conn.execute(text("""UPDATE platform_reservations SET status='released'
            WHERE platform=:p AND external_ref=:r"""), {"p": platform, "r": order_ref})
        if not released:
            for item in normalized:
                conn.execute(text("""INSERT INTO platform_reservations(platform, external_ref, code, qty, status)
                    VALUES (:p,:r,:c,:q,'active')
                    ON CONFLICT (platform, external_ref, code)
                    DO UPDATE SET qty=EXCLUDED.qty, status='active'"""),
                    {"p": platform, "r": order_ref, "c": item["code"], "q": item["qty"]})
            try:
                proforma_id = _create_platform_order_proforma(conn, platform, order_ref, normalized)
            except ValueError:
                proforma_id = None
        else:
            conn.execute(text("""UPDATE proforma_invoices SET status='cancelled'
                WHERE status='draft' AND id IN (
                  SELECT proforma_id FROM platform_order_proformas
                  WHERE platform=:p AND order_ref=:r AND NOT holoo_registered)"""),
                {"p": platform, "r": order_ref})
            conn.execute(text("""UPDATE platform_order_proformas SET status='cancelled'
                WHERE platform=:p AND order_ref=:r AND NOT holoo_registered"""),
                {"p": platform, "r": order_ref})
    touched = list(dict.fromkeys([*previous, *quantities]))
    pushed = push_stock_many(touched)
    if released:
        return {"order": order_ref, "released": True, "pushed": pushed}
    return {"order": order_ref, "reserved": list(quantities), "proforma_id": proforma_id, "pushed": pushed}


def _dk_client():
    from digikala_api import DigikalaClient
    return DigikalaClient()


def _dk_variant_id(conn, code: str) -> tuple[int | None, int | None]:
    """(variant_id_for_api, dkp_id) from the synced digikala_variants table."""
    row = conn.execute(text("""SELECT raw->>'id' AS vid, dkp_id FROM digikala_variants
        WHERE holoo_code=:c AND status='active' ORDER BY updated_at DESC NULLS LAST LIMIT 1"""),
        {"c": code}).mappings().first()
    if not row:
        return None, None
    vid = int(row["vid"]) if row["vid"] else None
    return vid, row["dkp_id"]


def push_stock_many(codes: list[str]) -> list[dict]:
    """Push available stock to each platform listing."""
    results = []
    with engine.begin() as conn:
        ensure(conn)
        listings = conn.execute(text(
            "SELECT * FROM platform_listings WHERE active AND code = ANY(:codes)"),
            {"codes": codes}).mappings().all()
    for listing in listings:
        with engine.connect() as conn:
            available = available_stock(conn, listing["code"])
        errors = []
        if listing["platform"] == "digikala":
            try:
                with engine.connect() as conn:
                    vid, _ = _dk_variant_id(conn, listing["code"])
                if vid is None:
                    errors.append("no digikala variant mapped")
                else:
                    client = _dk_client()
                    resp = client.update_stock(vid, available)
                    if resp.status_code not in (200, 201, 204):
                        errors.append(f"stock push {resp.status_code}")
            except Exception as exc:
                errors.append(type(exc).__name__)
        else:
            errors.append("no connector yet")
        with engine.begin() as conn:
            conn.execute(text("UPDATE platform_listings SET last_push_at=NOW() WHERE id=:i"),
                         {"i": listing["id"]})
        results.append({"platform": listing["platform"], "code": listing["code"],
                        "available": available, "errors": errors})
    return results


# ------------------------------------------------------------------- API

class ListingUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(pattern=r"^[a-z_]{2,30}$")
    code: str = Field(min_length=1, max_length=100)
    external_id: str | None = Field(default=None, max_length=100)
    price_mode: str = Field(default="auto", pattern=r"^(auto|manual)$")
    manual_price_irr: int | None = Field(default=None, ge=0)
    price_factor: float | None = Field(default=None, gt=0, le=10)
    active: bool = True


@router.get("/overview")
def overview(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        rows = conn.execute(text("""
            SELECT l.*, p.id AS product_id, COALESCE(p.stock,0) AS holoo_stock,
                   COALESCE(p.name,'') AS product_name
            FROM platform_listings l LEFT JOIN products p ON p.code=l.code
            ORDER BY l.platform, p.name
        """)).mappings().all()
        items = [dict(r) for r in rows]
        totals = reservation_totals(conn, [r['product_id'] for r in items if r['product_id'] is not None])
        for item in items:
            item['available'] = int(max(0, float(item['holoo_stock']) - totals.get(item['product_id'], 0)))
    return {"items": items}


@router.post("/listing")
def upsert_listing(data: ListingUpsert, user: dict = Depends(current_user)):
    _require_manager(user)
    if data.price_mode == "manual" and not data.manual_price_irr:
        raise HTTPException(422, "برای قیمت دستی، manual_price_irr لازم است.")
    with engine.begin() as conn:
        ensure(conn)
        conn.execute(text("""
            INSERT INTO platform_listings (platform, code, external_id, price_mode, manual_price_irr, price_factor, active)
            VALUES (:p,:c,:e,:m,:mp,:pf,:a)
            ON CONFLICT (platform, code) DO UPDATE SET external_id=EXCLUDED.external_id,
                price_mode=EXCLUDED.price_mode, manual_price_irr=EXCLUDED.manual_price_irr,
                price_factor=EXCLUDED.price_factor, active=EXCLUDED.active
        """), {"p": data.platform, "c": data.code, "e": data.external_id, "m": data.price_mode,
               "mp": data.manual_price_irr, "pf": data.price_factor, "a": data.active})
    pushed = push_stock_many([data.code])
    return {"status": "saved", "push": pushed[0] if pushed else None}


@router.post("/prices/import")
async def import_prices(file: UploadFile = File(...), user: dict = Depends(current_user)):
    """Excel/CSV with columns: code, price_irr (یا price_toman) — optional platform."""
    _require_manager(user)
    import csv
    import io
    raw = await file.read()
    rows: list[dict] = []
    name = (file.filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(c or "").strip().lower() for c in next(it)]
        for values in it:
            rows.append(dict(zip(header, values)))
    else:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))
        header = [h.strip().lower() for h in next(reader)]
        for values in reader:
            rows.append(dict(zip(header, values)))
    applied, skipped = 0, []
    with engine.begin() as conn:
        ensure(conn)
        for row in rows:
            code = str(row.get("code") or "").strip()
            price_irr = row.get("price_irr")
            if price_irr in (None, ""):
                toman = row.get("price_toman")
                price_irr = (float(toman) * 10) if toman not in (None, "") else None
            if not code or price_irr in (None, ""):
                skipped.append({"code": code, "reason": "missing fields"})
                continue
            updated = conn.execute(text("""UPDATE platform_listings SET price_mode='manual',
                manual_price_irr=:v WHERE code=:c AND active"""), {"v": int(float(price_irr)), "c": code}).rowcount
            if updated:
                applied += 1
            else:
                skipped.append({"code": code, "reason": "no active listing"})
    codes = [r["code"] for r in rows if r.get("code")][:200]
    pushed = push_stock_many(list(dict.fromkeys(codes)))
    return {"applied": applied, "skipped": skipped[:20], "pushed": pushed}


@router.post("/orders/ingest")
def ingest_order(payload: dict, user: dict = Depends(current_user)):
    """Manual/testing order ingestion: {platform, order_ref, status, items:[{code,qty}]}."""
    _require_manager(user)
    try:
        return apply_order(str(payload["platform"]), str(payload["order_ref"]),
                           list(payload.get("items") or []), payload.get("status"))
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise HTTPException(422, "ساختار سفارش نامعتبر است.") from exc


@router.post("/push-stock")
def push_all(user: dict = Depends(current_user)):
    """Full reconciliation push for every active listing."""
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        codes = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT code FROM platform_listings WHERE active")).all()]
    return {"pushed": push_stock_many(codes)}


@router.get("/orders")
def list_platform_orders(user: dict = Depends(current_user)):
    """Platform orders with their internal proforma draft id and Holoo tick state."""
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        _ensure_platform_proforma_storage(conn)
        rows = conn.execute(text("""
            SELECT o.platform, o.order_ref, o.status AS order_status, o.fetched_at,
                   op.proforma_id, op.status AS proforma_status,
                   op.holoo_registered, p.total_amount,
                   (SELECT COUNT(*) FROM platform_reservations r
                     WHERE r.platform=o.platform AND r.external_ref=o.order_ref
                       AND r.status='active') AS reserved_lines
            FROM platform_orders_raw o
            LEFT JOIN platform_order_proformas op
                ON op.platform=o.platform AND op.order_ref=o.order_ref
            LEFT JOIN proforma_invoices p ON p.id=op.proforma_id
            ORDER BY o.fetched_at DESC
            LIMIT 200
        """)).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/orders/{platform}/{order_ref}/holoo-registered")
def mark_holoo_registered(platform: str, order_ref: str, user: dict = Depends(current_user)):
    """Tick one platform's order after manual Holoo invoicing.

    Order references are only unique within a platform; always scope this
    update by both platform and order_ref. This is local bookkeeping only.
    """
    _require_manager(user)
    if platform not in PLATFORMS:
        raise HTTPException(400, "سکوی فروش نامعتبر است.")
    with engine.begin() as conn:
        ensure(conn)
        _ensure_platform_proforma_storage(conn)
        updated = conn.execute(text("""
            UPDATE platform_order_proformas SET holoo_registered=TRUE, status='registered'
            WHERE platform=:p AND order_ref=:r
        """), {"p": platform, "r": order_ref}).rowcount
        if not updated:
            raise HTTPException(404, "سفارش این سکو پیدا نشد یا پیش‌نویس پیش‌فاکتور ندارد.")
    return {"platform": platform, "order_ref": order_ref, "holoo_registered": True}


# ------------------------------------------------- product creation proposals
# These are preparation records only. New Digikala listings are created
# manually in Seller Center; the resulting variant is then mapped to Holoo.
# Do not add an API write until Digikala publishes a documented create route.


class CreateProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=100)
    suggested_title: str = Field(min_length=3, max_length=200)
    category_id: int | None = Field(default=None, ge=1)
    price_irr: int | None = Field(default=None, ge=0)
    stock: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    gtin: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)


@router.get("/create-product-proposals/unlisted")
def unlisted_products(user: dict = Depends(current_user)):
    """Holoo products with no digikala_variants row (not yet listed on DK)."""
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        rows = conn.execute(text("""
            SELECT p.code, p.name, p.price, COALESCE(p.stock,0) AS stock
            FROM products p
            WHERE p.is_active=1
              AND NOT EXISTS (SELECT 1 FROM digikala_variants dv
                              WHERE dv.holoo_code=p.code AND dv.status='active')
            ORDER BY p.name
        """)).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.get("/create-product-proposals")
def list_create_proposals(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        rows = conn.execute(text(
            "SELECT * FROM platform_create_proposals ORDER BY created_at DESC LIMIT 200")).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/create-product-proposals")
def create_proposal(data: CreateProposalInput, user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        product = conn.execute(text("SELECT code, name, price, stock FROM products WHERE code=:c"),
                               {"c": data.code}).mappings().first()
        if not product:
            raise HTTPException(404, "کالایی با این کد در هلو پیدا نشد.")
        dup = conn.execute(text("""SELECT id FROM platform_create_proposals
            WHERE code=:c AND status='pending'"""), {"c": data.code}).scalar()
        if dup:
            raise HTTPException(409, "برای این کالا قبلاً پیشنهاد ثبت در انتظار تایید وجود دارد.")
        price = data.price_irr if data.price_irr is not None else product["price"]
        pid = int(conn.execute(text("""
            INSERT INTO platform_create_proposals(platform, code, product_name, suggested_title,
                category_id, price_irr, stock, image_url, gtin, notes)
            VALUES ('digikala',:c,:n,:t,:cat,:pr,:st,:img,:gtin,:notes) RETURNING id"""),
            {"c": data.code, "n": product["name"], "t": data.suggested_title, "cat": data.category_id,
             "pr": price, "st": data.stock, "img": data.image_url, "gtin": data.gtin,
             "notes": data.notes}).scalar())
    return {"status": "pending", "id": pid}


@router.post("/create-product-proposals/{proposal_id}/confirm")
def confirm_create_proposal(proposal_id: int, user: dict = Depends(current_user)):
    """Fail closed until Digikala publishes a verified product-creation API."""
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        prop = conn.execute(text("SELECT * FROM platform_create_proposals WHERE id=:i"),
                            {"i": proposal_id}).mappings().first()
        if not prop:
            raise HTTPException(404, "پیشنهاد پیدا نشد.")
        if prop["status"] != "pending":
            raise HTTPException(409, "این پیشنهاد دیگر در انتظار اقدام نیست.")
    raise HTTPException(
        409,
        "ثبت خودکار کالای جدید از API رسمی دیجی‌کالا پشتیبانی نمی‌شود. "
        "کالا را در پنل فروشنده ثبت کنید و سپس متغیر آن را در صفحه نگاشت دیجی‌کالا به کالای هلو متصل کنید."
    )

@router.post("/create-product-proposals/{proposal_id}/reject")
def reject_create_proposal(proposal_id: int, user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        updated = conn.execute(text(
            "UPDATE platform_create_proposals SET status='rejected', confirmed_at=NOW() WHERE id=:i AND status='pending'"),
            {"i": proposal_id}).rowcount
        if not updated:
            raise HTTPException(404, "پیشنهاد در انتظار تایید پیدا نشد.")
    return {"id": proposal_id, "status": "rejected"}
