from datetime import datetime
import os
import requests

from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from db import engine
from models import Customer, Product

load_dotenv()

HOLO_URL = os.getenv("HOLO_API_URL").rstrip("/")
USERNAME = os.getenv("HOLO_USERNAME", "web")
PASSWORD = os.getenv("HOLO_PASSWORD", "MQ==")


SessionLocal = sessionmaker(
    bind=engine
)


def holoo_login():

    r = requests.post(
        HOLO_URL + "/Login",
        json={
            "userinfo": {
                "username": USERNAME,
                "userpass": PASSWORD,
                "dbname": "Holoo2"
            }
        },
        timeout=30
    )

    r.raise_for_status()

    return r.json()["Login"]["Token"]


def holoo_get(path, token):

    r = requests.get(
        HOLO_URL + path,
        headers={
            "Authorization": token
        },
        timeout=120
    )

    r.raise_for_status()

    return r.json()


def sync_customers(db, token):

    data = holoo_get(
        "/Customer",
        token
    )

    items = data.get("Customer", [])

    total = 0

    for x in items:

        code = x.get("Code") or x.get("ErpCode")

        if not code:
            continue

        obj = db.query(Customer).filter_by(
            code=code
        ).first()

        if not obj:
            obj = Customer(
                code=code
            )
            db.add(obj)

        obj.name = x.get("Name")
        obj.phone = x.get("Mobile") or x.get("Tel")
        obj.city = x.get("CityName")

        total += 1

    db.commit()

    return total


def sync_products(db, token):

    data = holoo_get(
        "/Product",
        token
    )

    items = data.get("product", [])

    total = 0

    for x in items:

        code = str(
            x.get("Code") or x.get("ArticleId")
        )

        obj = db.query(Product).filter_by(
            code=code
        ).first()

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

    finally:

        db.close()


if __name__ == "__main__":
    main()
