from datetime import datetime
import os
import requests

from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

from db import engine
from models import Customer, Product, SyncRun, SyncError

load_dotenv()

router = APIRouter(prefix="/holoo", tags=["Holoo"])

SessionLocal = sessionmaker(bind=engine)

HOLO_URL = (os.getenv("HOLO_API_URL") or "").rstrip("/")
USERNAME = os.getenv("HOLO_USERNAME", "web")
PASSWORD = os.getenv("HOLO_PASSWORD", "MQ==")


def login_holoo():

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


def get_holoo(path, token):

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

    data = get_holoo("/Customer", token)

    items = data.get("Customer", [])

    count = 0

    for x in items:

        code = x.get("Code") or x.get("ErpCode")

        if not code:
            continue

        obj = db.query(Customer).filter_by(code=code).first()

        if not obj:
            obj = Customer(code=code)
            db.add(obj)

        obj.name = x.get("Name")
        obj.phone = x.get("Mobile") or x.get("Tel")
        obj.city = x.get("CityName")

        count += 1

    return count


def sync_products(db, token):

    data = get_holoo("/Product", token)

    items = data.get("product", [])

    count = 0

    for x in items:

        code = str(x.get("Code") or x.get("ArticleId"))

        obj = db.query(Product).filter_by(code=code).first()

        if not obj:
            obj = Product(code=code)
            db.add(obj)

        obj.name = x.get("Name")
        obj.category = x.get("MainGroupName")
        obj.price = x.get("SellPrice", 0)
        obj.stock = x.get("Few", 0)

        count += 1

    return count


@router.post("/sync")
def sync_holoo():

    db = SessionLocal()

    run = SyncRun(
        channel="holoo",
        direction="import",
        status="running"
    )

    db.add(run)
    db.commit()
    db.refresh(run)

    try:

        token = login_holoo()

        customers = sync_customers(db, token)

        products = sync_products(db, token)

        run.status = "success"
        run.records_read = customers + products
        run.records_written = customers + products
        run.finished_at = datetime.utcnow()

        db.commit()

        return {
            "status": "success",
            "customers": customers,
            "products": products
        }

    except Exception as e:

        run.status = "failed"
        run.finished_at = datetime.utcnow()

        db.add(
            SyncError(
                sync_run_id=run.id,
                channel="holoo",
                entity="sync",
                message=str(e)
            )
        )

        db.commit()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    finally:
        db.close()

@router.get("/status")
def holoo_status():

    db = SessionLocal()

    try:

        last = (
            db.query(SyncRun)
            .filter_by(channel="holoo")
            .order_by(SyncRun.id.desc())
            .first()
        )

        if not last:
            return {
                "status": "no_sync"
            }

        return {
            "status": last.status,
            "started_at": last.started_at,
            "finished_at": last.finished_at,
            "records_read": last.records_read,
            "records_written": last.records_written
        }

    finally:
        db.close()



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

