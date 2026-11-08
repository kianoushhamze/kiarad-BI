from datetime import datetime
import os
import requests
from holoo_transport import holoo_request as _holoo_request

from fastapi import APIRouter, Depends, HTTPException
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from db import engine
from models import Customer, Product, SyncRun, SyncError
from holoo_mappings import ensure_holoo_entity_mappings, save_holoo_entity_mapping
from operations import require_manager

load_dotenv()

router = APIRouter(prefix="/holoo", tags=["Holoo"])

SessionLocal = sessionmaker(bind=engine)

HOLO_URL = (os.getenv("HOLO_API_URL") or "").rstrip("/")
USERNAME = os.getenv("HOLO_USERNAME", "web")
PASSWORD = os.getenv("HOLO_PASSWORD", "MQ==")
DBNAME = os.getenv("HOLO_DBNAME", "Holoo2")


def login_holoo():

    r = _holoo_request('POST',
        HOLO_URL + "/Login",
        json={
            "userinfo": {
                "username": USERNAME,
                "userpass": PASSWORD,
                "dbname": DBNAME
            }
        },
        timeout=30
    )

    r.raise_for_status()

    login = r.json().get("Login")
    state = login.get("State") if isinstance(login, dict) else None
    if str(state).strip().lower() not in {"true", "1"} or not login.get("Token"):
        raise ValueError("Holoo login did not return an active session")
    return login["Token"]


def get_holoo(path, token, timeout=300):

    r = _holoo_request('GET',
        HOLO_URL + path,
        headers={
            "Authorization": token
        },
        timeout=timeout
    )

    r.raise_for_status()

    return r.json()


def _as_records(payload, keys=()):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
    return []


def _as_bool(value):
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


@router.get("/payment-options")
def holoo_payment_options(_: dict = Depends(require_manager)):
    """Read safe payment account labels for a later invoice preview; never writes to Holoo."""
    try:
        token = login_holoo()
        cash_response = get_holoo("/Report/GetCash", token, timeout=25)
        bank_response = get_holoo("/Payment/Account", token, timeout=25)
        cash_rows = _as_records(cash_response, ("report", "Report"))
        bank_rows = _as_records(bank_response, ("account", "Account", "accounts", "Accounts"))
        cash = []
        for row in cash_rows:
            if not isinstance(row, dict) or not row.get("Code"):
                continue
            cash.append({"code": str(row["Code"]), "name": str(row.get("Name") or "صندوق"),
                         "balance": row.get("Price")})
        banks = []
        for row in bank_rows:
            if not isinstance(row, dict) or not row.get("sarfaslCode"):
                continue
            banks.append({"code": str(row["sarfaslCode"]),
                          "name": str(row.get("bankName") or row.get("accOwnerName") or "حساب بانکی"),
                          "has_pos": _as_bool(row.get("hasPOS", row.get("hasPos", False)))})
        return {"cash": cash, "banks": banks, "source": "holoo_read_only", "invoice_write_enabled": False}
    except Exception:
        raise HTTPException(status_code=502, detail="خواندن سرفصل‌های پرداخت از هلو انجام نشد؛ اتصال و پاسخ وب‌سرویس را بررسی کنید.")


def sync_customers(db, token):

    data = get_holoo("/Customer", token)

    items = (data.get("customer") if "customer" in data else data.get("Customer")) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("Holoo customer response has an unexpected shape")

    count = 0

    for x in items:

        erp_code = str(x.get("ErpCode") or "").strip()
        code = x.get("Code") or erp_code

        if not code:
            continue

        obj = db.query(Customer).filter_by(code=code).first()
        if not obj and erp_code and code != erp_code:
            # Older imports may have used ErpCode as the local code fallback.
            obj = db.query(Customer).filter_by(code=erp_code).first()

        if not obj:
            obj = Customer(code=code)
            db.add(obj)

        obj.name = x.get("Name")
        obj.phone = x.get("Mobile") or x.get("Tel")
        obj.city = x.get("CityName")
        if erp_code:
            db.flush()
            save_holoo_entity_mapping(db, "customer", obj.id, erp_code)

        count += 1

    return count


def sync_products(db, token):

    data = get_holoo("/Product", token)

    items = data.get("product") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("Holoo product response has an unexpected shape")

    count = 0

    for x in items:

        erp_code = str(x.get("ErpCode") or "").strip()
        raw_code = x.get("Code") or x.get("ArticleId") or erp_code
        if not raw_code:
            continue
        code = str(raw_code)

        obj = db.query(Product).filter_by(code=code).first()
        if not obj and erp_code and code != erp_code:
            # Keep prior rows that were keyed by ErpCode instead of product Code.
            obj = db.query(Product).filter_by(code=erp_code).first()

        if not obj:
            obj = Product(code=code)
            db.add(obj)

        obj.name = x.get("Name")
        obj.category = x.get("MainGroupName")
        obj.price = x.get("SellPrice", 0)
        obj.stock = x.get("Few", 0)
        obj.updated_at = datetime.utcnow()
        if erp_code:
            db.flush()
            save_holoo_entity_mapping(db, "product", obj.id, erp_code)

        count += 1

    return count


@router.post("/sync",status_code=202)
def sync_holoo():
    from holoo_finance_jobs import start_financial_refresh
    return start_financial_refresh()


@router.get("/status")
def holoo_status():
    from holoo_finance_jobs import financial_refresh_status
    from holoo_operational_sync import operational_status
    with engine.connect() as conn:
        return {**financial_refresh_status(),"last_operational_success":operational_status(conn,manager=True)}


@router.get("/history")
def holoo_history():

    db = SessionLocal()

    try:

        rows = (
            db.query(SyncRun)
            .filter_by(channel="holoo")
            .order_by(SyncRun.id.desc())
            .limit(20)
            .all()
        )

        return [
            {
                "id": x.id,
                "status": x.status,
                "started_at": x.started_at,
                "finished_at": x.finished_at,
                "records_read": x.records_read,
                "records_written": x.records_written
            }
            for x in rows
        ]

    finally:
        db.close()



@router.get("/errors")
def holoo_errors():

    db = SessionLocal()

    try:

        rows = (
            db.query(SyncError)
            .filter_by(channel="holoo")
            .order_by(SyncError.id.desc())
            .limit(20)
            .all()
        )

        return [
            {
                "id": x.id,
                "entity": x.entity,
                "message": x.message,
                "created_at": x.created_at
            }
            for x in rows
        ]

    finally:
        db.close()

