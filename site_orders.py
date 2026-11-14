"""سفارش‌های سایت (site storefront orders) — خرید مشتری از فروشگاه عمومی.

Customer checkout: POST /site-orders with site-customer JWT (site_auth).
Totals are ALWAYS recomputed server-side from products/cms_product_meta —
client totals are never trusted. Consumer price = holoo price × 1.15, or the
CMS discount price (discount_price_irr, IRR) when present and lower.

Manager endpoints (GET /all, PATCH status) require an employee JWT with
role manager/ceo — same policy as site_cms (_ceo).
"""
import json
import logging
import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from operations import current_user
from site_auth import current_site_customer
from site_cms import ensure as ensure_catalog
from platform_sync import ensure as ensure_platforms, reserved_count, push_stock_many

logger = logging.getLogger("kiarad_site_orders")
router = APIRouter(prefix="/site-orders", tags=["site_orders"])

CONSUMER_FACTOR = 1.15
ORDER_STATUSES = ("جدید", "تأیید شده", "ارسال شد", "لغو شد")


def ensure(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS site_orders(
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT,
            city TEXT,
            address TEXT,
            items JSONB NOT NULL DEFAULT '[]'::jsonb,
            total_irr BIGINT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'جدید',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""))
    conn.execute(text("ALTER TABLE site_orders ADD COLUMN IF NOT EXISTS request_key TEXT"))
    conn.execute(text("ALTER TABLE site_orders ADD COLUMN IF NOT EXISTS request_fingerprint TEXT"))
    conn.execute(text("ALTER TABLE site_orders ADD COLUMN IF NOT EXISTS reservation_managed BOOLEAN NOT NULL DEFAULT FALSE"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS site_orders_customer_request_key "
                      "ON site_orders(customer_id, request_key) WHERE request_key IS NOT NULL"))


class OrderItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=100)
    qty: int = Field(ge=1, le=999)


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=20)
    city: str = Field(min_length=1, max_length=80)
    address: str = Field(min_length=5, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)
    request_id: str | None = Field(default=None, min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class StatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


def _consumer_unit_irr(price: int | None, discount: int | None) -> int | None:
    """Unit price in IRR the site customer pays (never trusts client)."""
    base = round(price * CONSUMER_FACTOR) if price is not None and price >= 0 else None
    if discount is not None and 0 < discount < (base or 0):
        return discount
    return base


def _recompute(conn, items: list[OrderItemIn]) -> tuple[list[dict], int]:
    totals: list[dict] = []
    total_irr = 0
    # A client can submit the same SKU on multiple lines. Check the combined
    # quantity, otherwise each line independently passes the stock check.
    quantities: dict[str, int] = {}
    for it in items:
        quantities[it.code] = quantities.get(it.code, 0) + it.qty
    for code, qty in sorted(quantities.items()):
        row = conn.execute(text(
            "SELECT p.name, p.price, p.stock, m.discount_price_irr "
            "FROM products p LEFT JOIN cms_product_meta m ON m.code = p.code "
            "WHERE p.code = :c AND COALESCE(p.is_active, 1) = 1 "
            "AND COALESCE(m.hidden, FALSE) = FALSE FOR UPDATE OF p"
        ), {"c": code}).mappings().first()
        if not row:
            raise HTTPException(400, f"کالای {code} در فروشگاه موجود نیست.")
        unit = _consumer_unit_irr(row["price"], row["discount_price_irr"])
        if unit is None:
            raise HTTPException(400, f"قیمت کالای {code} مشخص نیست؛ سفارش ثبت نشد.")
        if max(0, (row["stock"] or 0) - reserved_count(conn, code)) < qty:
            raise HTTPException(400, f"موجودی کالای {row['name']} ({code}) کافی نیست.")
        line_total = unit * qty
        total_irr += line_total
        totals.append({"code": code, "name": row["name"], "qty": qty,
                       "unit_price_irr": unit, "line_total_irr": line_total})
    return totals, total_irr


def _fingerprint(data: OrderIn) -> str:
    payload = data.model_dump(exclude={"request_id", "items"})
    payload = {key: value.strip() for key, value in payload.items()}
    quantities: dict[str, int] = {}
    for item in data.items:
        quantities[item.code] = quantities.get(item.code, 0) + item.qty
    payload["items"] = sorted(quantities.items())
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _publish_stock(codes):
    try:
        results = push_stock_many(codes)
        if any(result.get("errors") for result in results):
            logger.warning("Storefront stock publication needs scheduled retry")
    except Exception:
        logger.exception("Storefront stock publication failed; reservation remains committed")


def _reserve_items(conn, order_id, items):
    for item in items:
        conn.execute(text("""INSERT INTO platform_reservations(platform, external_ref, code, qty, status)
            VALUES ('site', :ref, :code, :qty, 'active')
            ON CONFLICT(platform, external_ref, code) DO UPDATE SET qty=EXCLUDED.qty, status='active'"""),
            {"ref": f"storefront:{order_id}", "code": item["code"], "qty": item["qty"]})


def _reserve_legacy_pending(conn):
    """Account for pre-upgrade pending orders before admitting a new checkout.

    Already shipped legacy orders are deliberately not inferred from Holoo stock.
    """
    rows = conn.execute(text("""SELECT id, items FROM site_orders
        WHERE NOT reservation_managed AND status IN ('جدید', 'تأیید شده')
        ORDER BY id FOR UPDATE""")).mappings().all()
    codes = set()
    snapshots = []
    for row in rows:
        items = row["items"] if isinstance(row["items"], list) else json.loads(row["items"])
        quantities = {}
        for item in items:
            code, qty = item["code"], int(item["qty"])
            if qty <= 0:
                raise HTTPException(409, "سفارش قدیمی نامعتبر است؛ ابتدا آن را بررسی یا لغو کنید.")
            quantities[code] = quantities.get(code, 0) + qty
        snapshots.append((row["id"], [{"code": code, "qty": qty} for code, qty in quantities.items()]))
        codes.update(quantities)
    for code in sorted(codes):
        conn.execute(text("SELECT code FROM products WHERE code=:code FOR UPDATE"), {"code": code}).all()
    for order_id, items in snapshots:
        _reserve_items(conn, order_id, items)
        conn.execute(text("UPDATE site_orders SET reservation_managed=TRUE WHERE id=:id"), {"id": order_id})
    return codes


def _order_response(row, replayed=False):
    items = row["items"] if isinstance(row["items"], list) else json.loads(row["items"])
    return {"ok": True, "order_id": int(row["id"]), "total_irr": row["total_irr"],
            "items": items, "created_at": row["created_at"].isoformat(), "replayed": replayed}


@router.post("")
def create_order(data: OrderIn, background_tasks: BackgroundTasks, customer: dict = Depends(current_site_customer)):
    with engine.begin() as conn:
        ensure(conn)
        ensure_catalog(conn)
        ensure_platforms(conn)
        fingerprint = _fingerprint(data)
        if data.request_id:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                         {"key": f"site-checkout:{customer['id']}:{data.request_id}"})
            existing = conn.execute(text("SELECT * FROM site_orders WHERE customer_id=:cid AND request_key=:key"),
                                    {"cid": customer["id"], "key": data.request_id}).mappings().first()
            if existing:
                if existing["request_fingerprint"] != fingerprint:
                    raise HTTPException(409, "شناسهٔ درخواست قبلاً برای سفارش دیگری استفاده شده است.")
                return _order_response(existing, replayed=True)
        touched = _reserve_legacy_pending(conn)
        items, total_irr = _recompute(conn, data.items)
        row = conn.execute(text(
            "INSERT INTO site_orders(customer_id, customer_name, phone, city, address, items, total_irr, "
            "request_key, request_fingerprint, reservation_managed) "
            "VALUES (:cid, :name, :phone, :city, :addr, CAST(:items AS jsonb), :total, :key, :fingerprint, TRUE) "
            "RETURNING id, created_at, items, total_irr"
        ), {"cid": customer["id"], "name": data.customer_name.strip(),
            "phone": data.phone.strip(), "city": data.city.strip(),
            "addr": data.address.strip(),
            "items": json.dumps(items, ensure_ascii=False), "total": total_irr,
            "key": data.request_id, "fingerprint": fingerprint}
        ).mappings().first()
        _reserve_items(conn, row["id"], items)
        touched.update(item["code"] for item in items)
    background_tasks.add_task(_publish_stock, sorted(touched))
    logger.info("site order created: id=%s customer=%s total_irr=%s items=%s",
                row["id"], customer["id"], total_irr, len(items))
    return _order_response(row)


def _shape(r) -> dict:
    return {"id": r["id"], "customer_id": r["customer_id"], "customer_name": r["customer_name"],
            "phone": r["phone"], "city": r["city"], "address": r["address"],
            "items": r["items"] if isinstance(r["items"], list) else json.loads(r["items"] or "[]"),
            "total_irr": r["total_irr"], "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None}


@router.get("/mine")
def my_orders(customer: dict = Depends(current_site_customer)):
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text(
            "SELECT * FROM site_orders WHERE customer_id = :cid ORDER BY id DESC LIMIT 100"
        ), {"cid": customer["id"]}).mappings().all()
    return {"count": len(rows), "orders": [_shape(r) for r in rows]}


def _manager(user):
    if not user or user.get("role") not in ("ceo", "manager"):
        raise HTTPException(403, "این بخش فقط برای مدیر/مدیرعامل امکان‌پذیر است.")


@router.get("/all")
def all_orders(status: str = "", user: dict = Depends(current_user)):
    _manager(user)
    sql = "SELECT * FROM site_orders"
    params: dict = {}
    if status:
        sql += " WHERE status = :s"
        params["s"] = status
    sql += " ORDER BY id DESC LIMIT 500"
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text(sql), params).mappings().all()
    return {"count": len(rows), "orders": [_shape(r) for r in rows]}


@router.patch("/{order_id}/status")
def set_status(order_id: int, data: StatusIn, background_tasks: BackgroundTasks, user: dict = Depends(current_user)):
    _manager(user)
    if data.status not in ORDER_STATUSES:
        raise HTTPException(400, f"وضعیت باید یکی از {list(ORDER_STATUSES)} باشد.")
    with engine.begin() as conn:
        ensure(conn)
        ensure_platforms(conn)
        old = conn.execute(text("SELECT status FROM site_orders WHERE id=:id FOR UPDATE"), {"id": order_id}).mappings().first()
        if not old:
            raise HTTPException(404, "سفارشی با این شناسه پیدا نشد.")
        if old["status"] == "لغو شد" and data.status != "لغو شد":
            raise HTTPException(409, "سفارش لغوشده قابل بازگشایی نیست؛ سفارش جدید ثبت کنید.")
        # A shipped order has already left the warehouse. Releasing its stock
        # reservation or moving it back to a pending state could oversell stock.
        if old["status"] == "ارسال شد" and data.status != "ارسال شد":
            raise HTTPException(409, "سفارش ارسال‌شده قابل لغو یا بازگشت به مراحل قبلی نیست.")
        touched = []
        if data.status == "لغو شد":
            touched = [r[0] for r in conn.execute(text(
                "SELECT code FROM platform_reservations WHERE platform='site' AND external_ref=:ref ORDER BY code"
            ), {"ref": f"storefront:{order_id}"}).all()]
            for code in touched:
                conn.execute(text("SELECT code FROM products WHERE code=:code FOR UPDATE"), {"code": code}).all()
            conn.execute(text("UPDATE platform_reservations SET status='released' "
                              "WHERE platform='site' AND external_ref=:ref"), {"ref": f"storefront:{order_id}"})
        row = conn.execute(text(
            "UPDATE site_orders SET status = :s WHERE id = :id RETURNING id, status"
        ), {"s": data.status, "id": order_id}).mappings().first()
    if not row:
        raise HTTPException(404, "سفارشی با این شناسه پیدا نشد.")
    logger.info("site order status: id=%s -> %s by user=%s", order_id, data.status, user.get("id"))
    if touched:
        background_tasks.add_task(_publish_stock, touched)
    return {"ok": True, "id": int(row["id"]), "status": row["status"]}
