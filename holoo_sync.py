from datetime import datetime
import os
import requests
from holoo_transport import holoo_request as _holoo_request

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from db import engine
from models import Customer, Product
from holoo_mappings import ensure_holoo_entity_mappings, save_holoo_entity_mapping

load_dotenv()

HOLO_URL = os.getenv("HOLO_API_URL", "").rstrip("/")
USERNAME = os.getenv("HOLO_USERNAME", "web")
PASSWORD = os.getenv("HOLO_PASSWORD", "MQ==")
DBNAME = os.getenv("HOLO_DBNAME", "Holoo2")


SessionLocal = sessionmaker(
    bind=engine
)


def holoo_login():
    if not HOLO_URL:
        raise ValueError("HOLO_API_URL is not configured")

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


def holoo_get(path, token):

    r = _holoo_request('GET',
        HOLO_URL + path,
        headers={
            "Authorization": token
        },
        timeout=120
    )

    r.raise_for_status()

    return r.json()


def sync_customers(db, token):

    ensure_holoo_entity_mappings(db)

    data = holoo_get(
        "/Customer",
        token
    )

    items = (data.get("customer") if "customer" in data else data.get("Customer")) if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("Holoo customer response has an unexpected shape")

    total = 0

    for x in items:

        erp_code = str(x.get("ErpCode") or "").strip()
        code = x.get("Code") or erp_code

        if not code:
            continue

        obj = db.query(Customer).filter_by(
            code=code
        ).first()
        if not obj and erp_code and code != erp_code:
            obj = db.query(Customer).filter_by(code=erp_code).first()

        if not obj:
            obj = Customer(
                code=code
            )
            db.add(obj)

        obj.name = x.get("Name")
        obj.phone = x.get("Mobile") or x.get("Tel")
        obj.city = x.get("CityName")
        if erp_code:
            db.flush()
            save_holoo_entity_mapping(db, "customer", obj.id, erp_code)

        total += 1

    db.commit()

    return total


def sync_products(db, token):

    ensure_holoo_entity_mappings(db)

    data = holoo_get(
        "/Product",
        token
    )

    items = data.get("product") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("Holoo product response has an unexpected shape")

    total = 0

    for x in items:

        erp_code = str(x.get("ErpCode") or "").strip()
        raw_code = x.get("Code") or x.get("ArticleId") or erp_code
        if not raw_code:
            continue
        code = str(raw_code)

        obj = db.query(Product).filter_by(
            code=code
        ).first()
        if not obj and erp_code and code != erp_code:
            obj = db.query(Product).filter_by(code=erp_code).first()

        if not obj:
            obj = Product(
                code=code
            )
            db.add(obj)

        obj.name = x.get("Name")
        obj.category = x.get("MainGroupName")
        obj.price = x.get("SellPrice", 0)
        obj.stock = x.get("Few", 0)
        obj.is_active = 1 if x.get("IsActive") else 0
        obj.updated_at = datetime.utcnow()
        if erp_code:
            db.flush()
            save_holoo_entity_mapping(db, "product", obj.id, erp_code)

        total += 1

    db.commit()

    return total


def main():

    db = SessionLocal()

    try:

        print("Connecting Holoo...")

        token = holoo_login()

        print("Holoo Login OK")

        c = sync_customers(
            db,
            token
        )

        print(
            "Customers synced:",
            c
        )


        p = sync_products(
            db,
            token
        )

        print(
            "Products synced:",
            p
        )


        print("SYNC COMPLETED")


    except Exception as e:

        print("SYNC ERROR:")
        print(e)
        raise SystemExit(1)

    finally:

        db.close()


if __name__ == "__main__":
    main()
