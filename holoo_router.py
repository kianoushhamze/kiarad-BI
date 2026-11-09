# -*- coding: utf-8 -*-
"""Holoo integration: customers, products and sales invoices -> Kiarad BI.

Access: manager JWT (ceo / sales_manager) or the X-API-Key used by the hourly sync script.

How invoice fields are stored (sales table):
  total_amount    = SumPrice - SumDiscount   (net sales, before levy/tax)
  discount_amount = SumDiscount
  credit_amount   = SumNesiyeh               (on credit; Holoo includes levy + tax in it)
  paid_amount     = SumNaghd + SumCard + SumCheck
Salesperson is NOT taken from Holoo's UserName (that is the Holoo operator login, the same for
every invoice). It comes from customers.salesperson_id, set with POST /holoo/assign-visitor.
"""
import hmac
import json
import os
from datetime import date, datetime, timedelta
from typing import List, Optional

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text as sql
from sqlalchemy.orm import sessionmaker

from db import engine
from models import Customer, Payment, Product, Sale, SaleItem, SyncError, SyncRun
from operations import MANAGER_ROLES, current_user, require_manager

load_dotenv()

router = APIRouter(prefix="/holoo", tags=["Holoo"])
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
LOCK_KEY = 7731001  # PostgreSQL advisory lock: only one Holoo sync at a time


class HolooError(Exception):
    pass


class SyncBusy(Exception):
    pass


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
def require_sync_access(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    expected = os.getenv("KIARAD_API_KEY", "")
    if expected and x_api_key and hmac.compare_digest(x_api_key.encode(), expected.encode()):
        return {"role": "automation"}
    user = current_user(authorization)
    if user["role"] not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_FA = str.maketrans({"\u064a": "\u06cc", "\u0649": "\u06cc", "\u0643": "\u06a9", "\u0640": None})


def norm_fa(value) -> str:
    """Arabic yeh/kaf -> Persian, drop tatweel, collapse spaces."""
    if value is None:
        return ""
    return " ".join(str(value).translate(_FA).split())


def _code(value) -> str:
    return "" if value is None else str(value).strip()


def _f(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dt(d, t) -> datetime:
    d = (d or "").strip().replace("-", "/")
    t = (t or "00:00:00").strip()
    if not d:
        raise ValueError("invoice has no date")
    if int(d.split("/")[0]) < 1700:
        raise ValueError(f"Jalali date not supported: {d}")
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(f"{d} {t}", fmt)
        except ValueError:
            pass
    return datetime.strptime(d, "%Y/%m/%d")


def _amounts(inv: dict) -> dict:
    gross = _f(inv.get("SumPrice"))
    discount = _f(inv.get("SumDiscount"))
    naghd, card, check = _f(inv.get("SumNaghd")), _f(inv.get("SumCard")), _f(inv.get("SumCheck"))
    return {
        "gross": gross,
        "discount": discount,
        "net": gross - discount,
        "naghd": naghd,
        "card": card,
        "check": check,
        "paid": naghd + card + check,
        "credit": _f(inv.get("SumNesiyeh")),
        "tax": _f(inv.get("SumLevy")) + _f(inv.get("SumScot")),
    }


class _Lookup:
    """code -> row, with a zero-stripped fallback ("00375" matches "375")."""

    def __init__(self, rows):
        self.exact, self.loose = {}, {}
        for r in rows:
            self.add(r)

    @staticmethod
    def _loose_key(code: str) -> str:
        return code.lstrip("0") or "0"

    def add(self, row):
        if row.code:
            self.exact[row.code] = row
            self.loose.setdefault(self._loose_key(row.code), row)

    def get(self, code):
        code = _code(code)
        if not code:
            return None
        return self.exact.get(code) or self.loose.get(self._loose_key(code))


def _log(db, run_id, entity, external_id, message):
    try:
        db.add(SyncError(
            sync_run_id=run_id, channel="holoo", entity=entity,
            external_id=None if external_id is None else str(external_id),
            message=str(message)[:2000],
        ))
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# Holoo HTTP client
# ---------------------------------------------------------------------------
def _cfg() -> dict:
    url = (os.getenv("HOLO_API_URL") or "").rstrip("/")
    password = os.getenv("HOLO_PASSWORD", "")
    if not url:
        raise HolooError("HOLO_API_URL is not set in .env")
    if not password:
        raise HolooError("HOLO_PASSWORD is not set in .env")
    return {
        "url": url,
        "user": os.getenv("HOLO_USERNAME", "web"),
        "password": password,
        "db": os.getenv("HOLO_DB_NAME", "Holoo2"),
        "invoice_type": str(os.getenv("HOLO_SALE_INVOICE_TYPE", "1")),
    }


def _decode(resp) -> dict:
    # Holoo does not always declare a charset, so decode the bytes explicitly as UTF-8.
    return json.loads(resp.content.decode("utf-8-sig", errors="replace"))


def login_holoo() -> str:
    c = _cfg()
    try:
        r = requests.post(
            c["url"] + "/Login",
            json={"userinfo": {"username": c["user"], "userpass": c["password"], "dbname": c["db"]}},
            timeout=30,
        )
        r.raise_for_status()
        data = _decode(r)
    except (requests.RequestException, ValueError) as e:
        raise HolooError(f"Holoo connection failed: {e}")
    login = data.get("Login") or {}
    if not login.get("State") or not login.get("Token"):
        raise HolooError("Holoo login rejected (check HOLO_USERNAME / HOLO_PASSWORD / HOLO_DB_NAME)")
    return login["Token"]


def get_holoo(path: str, token: str, timeout: int = 180) -> dict:
    try:
        r = requests.get(_cfg()["url"] + path, headers={"Authorization": token}, timeout=timeout)
        r.raise_for_status()
        return _decode(r)
    except (requests.RequestException, ValueError) as e:
        raise HolooError(f"Holoo request failed ({path.split('?')[0]}): {e}")


def _fetch_invoices(token: str, days: int):
    today = date.today()
    start = today - timedelta(days=days)
    path = (f"/Invoice/Invoice?type={_cfg()['invoice_type']}"
            f"&date.from={start.isoformat()}&date.to={today.isoformat()}")
    return get_holoo(path, token).get("invoice") or [], start


# ---------------------------------------------------------------------------
# Sync: customers / products
# ---------------------------------------------------------------------------
def sync_customers(db, token: str) -> int:
    items = get_holoo("/Customer", token).get("Customer") or []
    by_code = {c.code: c for c in db.query(Customer).filter(Customer.code.isnot(None)).all()}
    n = 0
    for x in items:
        code = _code(x.get("Code") or x.get("ErpCode"))
        if not code:
            continue
        c = by_code.get(code)
        if c is None:
            c = Customer(code=code)
            db.add(c)
            by_code[code] = c
        c.name = norm_fa(x.get("Name")) or c.name
        c.phone = _code(x.get("Mobile") or x.get("Tel")) or c.phone
        c.city = norm_fa(x.get("CityName")) or c.city
        n += 1
    db.commit()
    return n


def sync_products(db, token: str) -> int:
    items = get_holoo("/Product", token).get("product") or []
    by_code = {p.code: p for p in db.query(Product).filter(Product.code.isnot(None)).all()}
    n = 0
    for x in items:
        code = _code(x.get("Code") or x.get("ArticleId"))
        if not code:
            continue
        p = by_code.get(code)
        if p is None:
            p = Product(code=code)
            db.add(p)
            by_code[code] = p
        p.name = norm_fa(x.get("Name")) or p.name
        p.category = norm_fa(x.get("MainGroupName")) or p.category
        p.price = _f(x.get("SellPrice"))
        p.stock = _f(x.get("Few"))
        p.is_active = 1 if x.get("IsActive", True) else 0
        p.updated_at = datetime.utcnow()
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------------------
# Sync: invoices
# ---------------------------------------------------------------------------
def sync_invoices(db, token: str, days: int = 90, run_id: Optional[int] = None) -> dict:
    invoices, start = _fetch_invoices(token, days)

    customers = _Lookup(db.query(Customer).filter(Customer.code.isnot(None)).all())
    products = _Lookup(db.query(Product).filter(Product.code.isnot(None)).all())
    codes = [c for c in (inv.get("Code") for inv in invoices) if c is not None]
    existing = {s.holoo_code: s for s in db.query(Sale).filter(Sale.holoo_code.in_(codes)).all()} if codes else {}

    stats = {"fetched": len(invoices), "inserted": 0, "updated": 0, "unchanged": 0,
             "skipped_zero": 0, "skipped_no_code": 0, "errors": 0,
             "customers_created": 0, "products_created": 0}
    seen, type_names = set(), set()

    def get_customer(inv):
        code = _code(inv.get("customerCodeC"))
        if not code:
            return None
        c = customers.get(code)
        if c is None:
            c = Customer(code=code, name=norm_fa(inv.get("CustomerName")), phone=_code(inv.get("Mobile")) or None)
            db.add(c)
            db.flush()
            customers.add(c)
            stats["customers_created"] += 1
        return c

    def get_product(row):
        code = _code(row.get("ProductCode"))
        if not code:
            return None
        p = products.get(code)
        if p is None:
            p = Product(code=code, name=norm_fa(row.get("ProductName")) or "unnamed",
                        price=_f(row.get("Price")), stock=0, is_active=1)
            db.add(p)
            db.flush()
            products.add(p)
            stats["products_created"] += 1
        return p

    def write_items(sale_id, inv):
        for row in inv.get("Detail") or []:
            p = get_product(row)
            if p:
                db.add(SaleItem(sale_id=sale_id, product_id=p.id,
                                quantity=_f(row.get("Few")), price=_f(row.get("Price"))))

    for inv in invoices:
        code = inv.get("Code")
        try:
            if code is None:
                stats["skipped_no_code"] += 1
                continue
            seen.add(code)
            type_names.add(norm_fa(inv.get("TypeName")))
            a = _amounts(inv)
            if a["gross"] == 0:
                stats["skipped_zero"] += 1
                continue

            dt = _dt(inv.get("Date"), inv.get("Time"))
            cust = get_customer(inv)
            sale = existing.get(code)

            if sale is None:
                sale = Sale(
                    customer_id=cust.id if cust else None,
                    salesperson_id=cust.salesperson_id if cust else None,
                    date=dt, total_amount=a["net"], holoo_code=code,
                    holoo_sanad_code=_int(inv.get("SanadCode")),
                    paid_amount=a["paid"], credit_amount=a["credit"], discount_amount=a["discount"],
                )
                db.add(sale)
                db.flush()
                write_items(sale.id, inv)
                for amount in (a["naghd"], a["card"]):
                    if amount > 0:
                        db.add(Payment(customer_id=cust.id if cust else None, amount=amount, payment_date=dt))
                db.commit()
                stats["inserted"] += 1
                if a["check"] > 0:
                    _log(db, run_id, "invoice_check", code,
                         f"invoice has check amount {a['check']:.0f}: enter the check with its due date in Treasury")
                continue

            changed = False
            for field, value in (("total_amount", a["net"]), ("discount_amount", a["discount"]),
                                 ("credit_amount", a["credit"]), ("paid_amount", a["paid"])):
                if abs((getattr(sale, field) or 0) - value) > 0.5:
                    setattr(sale, field, value)
                    changed = True
            if changed:
                sale.date = dt
                db.query(SaleItem).filter(SaleItem.sale_id == sale.id).delete()
                write_items(sale.id, inv)
            if sale.salesperson_id is None and cust is not None and cust.salesperson_id:
                sale.salesperson_id = cust.salesperson_id
                changed = True
            if sale.customer_id is None and cust is not None:
                sale.customer_id = cust.id
                changed = True
            db.commit()
            stats["updated" if changed else "unchanged"] += 1

        except Exception as e:
            db.rollback()
            stats["errors"] += 1
            _log(db, run_id, "invoice", code, e)
            # rows created inside the failed invoice were rolled back: rebuild the caches
            customers = _Lookup(db.query(Customer).filter(Customer.code.isnot(None)).all())
            products = _Lookup(db.query(Product).filter(Product.code.isnot(None)).all())

    window_start = datetime.combine(start, datetime.min.time())
    in_db = db.query(Sale.holoo_code).filter(Sale.holoo_code.isnot(None), Sale.date >= window_start).all()
    missing = sorted(c for (c,) in in_db if c not in seen)
    stats.update({
        "period_days": days,
        "invoice_type": _cfg()["invoice_type"],
        "type_names": sorted(t for t in type_names if t),
        "missing_in_holoo_count": len(missing),
        "missing_in_holoo": missing[:50],
    })
    return stats


# ---------------------------------------------------------------------------
# Full sync (shared by the API and any script)
# ---------------------------------------------------------------------------
def _acquire_lock():
    conn = engine.connect()
    try:
        got = conn.execute(sql("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar()
    except Exception:
        conn.close()
        raise
    if not got:
        conn.close()
        return None
    return conn


def _release_lock(conn):
    try:
        conn.execute(sql("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
        conn.commit()
    finally:
        conn.close()


def run_full_sync(days: int = 90) -> dict:
    lock = _acquire_lock()
    if lock is None:
        raise SyncBusy()
    db = SessionLocal()
    run = SyncRun(channel="holoo", direction="import", status="running")
    db.add(run)
    db.commit()
    try:
        token = login_holoo()
        c = sync_customers(db, token)
        p = sync_products(db, token)
        inv = sync_invoices(db, token, days, run.id)
        run.records_read = c + p + inv["fetched"]
        run.records_written = c + p + inv["inserted"] + inv["updated"]
        run.status = "success" if inv["errors"] == 0 else "partial"
        run.finished_at = datetime.utcnow()
        db.commit()
        return {"status": run.status, "customers": c, "products": p, "invoices": inv}
    except Exception as e:
        db.rollback()
        run.status = "failed"
        run.finished_at = datetime.utcnow()
        db.add(SyncError(sync_run_id=run.id, channel="holoo", entity="sync", message=str(e)[:2000]))
        db.commit()
        raise
    finally:
        db.close()
        _release_lock(lock)


def _http_error(e: Exception) -> HTTPException:
    if isinstance(e, SyncBusy):
        return HTTPException(status_code=409, detail="A Holoo sync is already running")
    if isinstance(e, HolooError):
        return HTTPException(status_code=502, detail=str(e))
    return HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/sync")
def sync_holoo(days: int = Query(90, ge=1, le=365), _: dict = Depends(require_sync_access)):
    try:
        return run_full_sync(days)
    except Exception as e:
        raise _http_error(e)


@router.post("/sync-invoices-only")
def sync_invoices_only(days: int = Query(90, ge=1, le=365), _: dict = Depends(require_sync_access)):
    lock = None
    try:
        lock = _acquire_lock()
        if lock is None:
            raise SyncBusy()
        db = SessionLocal()
        try:
            return {"status": "success", **sync_invoices(db, login_holoo(), days)}
        finally:
            db.close()
    except Exception as e:
        raise _http_error(e)
    finally:
        if lock is not None:
            _release_lock(lock)


@router.get("/preview-invoices")
def preview_invoices(days: int = Query(30, ge=1, le=365), _: dict = Depends(require_sync_access)):
    """Read-only check of what Holoo returns, before anything is written."""
    try:
        invoices, _start = _fetch_invoices(login_holoo(), days)
    except Exception as e:
        raise _http_error(e)

    db = SessionLocal()
    try:
        customers = _Lookup(db.query(Customer).filter(Customer.code.isnot(None)).all())
        products = _Lookup(db.query(Product).filter(Product.code.isnot(None)).all())
    finally:
        db.close()

    type_names, operators = {}, {}
    gross = discount = net = 0.0
    zero, unknown_customers, unknown_products, sample = [], set(), set(), []
    for inv in invoices:
        a = _amounts(inv)
        gross, discount, net = gross + a["gross"], discount + a["discount"], net + a["net"]
        tn, op = norm_fa(inv.get("TypeName")), norm_fa(inv.get("UserName"))
        type_names[tn] = type_names.get(tn, 0) + 1
        operators[op] = operators.get(op, 0) + 1
        if a["gross"] == 0:
            zero.append(inv.get("Code"))
        if customers.get(inv.get("customerCodeC")) is None:
            unknown_customers.add(_code(inv.get("customerCodeC")))
        for row in inv.get("Detail") or []:
            pc = _code(row.get("ProductCode"))
            if pc and products.get(pc) is None:
                unknown_products.add(pc)
        if len(sample) < 3:
            sample.append({"code": inv.get("Code"), "date": inv.get("Date"),
                           "customer": norm_fa(inv.get("CustomerName")), "gross": a["gross"],
                           "discount": a["discount"], "net": a["net"], "tax": a["tax"],
                           "credit": a["credit"], "items": len(inv.get("Detail") or [])})
    return {
        "configured_invoice_type": _cfg()["invoice_type"],
        "invoices": len(invoices),
        "type_names": type_names,
        "holoo_operators": operators,
        "totals": {"gross": gross, "discount": discount, "net": net},
        "zero_amount_invoice_codes": zero,
        "customer_codes_not_in_db": sorted(unknown_customers)[:30],
        "product_codes_not_in_db": sorted(unknown_products)[:30],
        "sample": sample,
    }


class AssignVisitor(BaseModel):
    salesperson_id: int
    customer_codes: List[str] = Field(min_length=1, max_length=500)


@router.post("/assign-visitor")
def assign_visitor(data: AssignVisitor, _: dict = Depends(require_manager)):
    """Set the responsible visitor for customers and fill in past Holoo sales that have none."""
    codes = [c.strip() for c in data.customer_codes if c and c.strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="customer_codes is empty")
    with engine.begin() as conn:
        if not conn.execute(sql("SELECT 1 FROM salespersons WHERE id=:i"), {"i": data.salesperson_id}).first():
            raise HTTPException(status_code=404, detail="Salesperson not found")
        customers = conn.execute(
            sql("UPDATE customers SET salesperson_id=:sp WHERE code = ANY(:codes)"),
            {"sp": data.salesperson_id, "codes": codes},
        ).rowcount
        sales = conn.execute(
            sql("""UPDATE sales SET salesperson_id=:sp
                   WHERE holoo_code IS NOT NULL AND salesperson_id IS NULL
                     AND customer_id IN (SELECT id FROM customers WHERE code = ANY(:codes))"""),
            {"sp": data.salesperson_id, "codes": codes},
        ).rowcount
    return {"customers_updated": customers, "sales_filled": sales}


@router.get("/unassigned-customers")
def unassigned_customers(_: dict = Depends(require_manager)):
    """Customers with Holoo sales but no responsible visitor, biggest first."""
    with engine.connect() as conn:
        rows = conn.execute(sql("""
            SELECT c.code, c.name, COUNT(s.id) AS invoices, COALESCE(SUM(s.total_amount), 0) AS net_sales
            FROM customers c JOIN sales s ON s.customer_id = c.id
            WHERE s.holoo_code IS NOT NULL AND c.salesperson_id IS NULL
            GROUP BY c.id, c.code, c.name
            ORDER BY net_sales DESC LIMIT 100
        """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/status")
def holoo_status(_: dict = Depends(require_sync_access)):
    db = SessionLocal()
    try:
        x = db.query(SyncRun).filter_by(channel="holoo").order_by(SyncRun.id.desc()).first()
        if not x:
            return {"status": "no_sync"}
        return {"status": x.status, "started_at": x.started_at, "finished_at": x.finished_at,
                "records_read": x.records_read, "records_written": x.records_written}
    finally:
        db.close()


@router.get("/history")
def holoo_history(_: dict = Depends(require_sync_access)):
    db = SessionLocal()
    try:
        rows = db.query(SyncRun).filter_by(channel="holoo").order_by(SyncRun.id.desc()).limit(20).all()
        return [{"id": x.id, "status": x.status, "started_at": x.started_at, "finished_at": x.finished_at,
                 "records_read": x.records_read, "records_written": x.records_written} for x in rows]
    finally:
        db.close()


@router.get("/errors")
def holoo_errors(_: dict = Depends(require_sync_access)):
    db = SessionLocal()
    try:
        rows = db.query(SyncError).filter_by(channel="holoo").order_by(SyncError.id.desc()).limit(50).all()
        return [{"id": x.id, "entity": x.entity, "external_id": x.external_id,
                 "message": x.message, "created_at": x.created_at} for x in rows]
    finally:
        db.close()
