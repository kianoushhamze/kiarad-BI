import os
import requests
from sqlalchemy import text
from db import engine

HOLO_URL = "http://192.168.1.105:8080/TncHoloo/api".rstrip("/")
HOLO_USER = os.getenv("HOLO_USERNAME", "web")
HOLO_PASS = os.getenv("HOLO_PASSWORD", "MQ==")

def sync_from_holoo():
    print("Connecting to Holoo...")
    login_res = requests.post(
        f"{HOLO_URL}/Login",
        json={"username": HOLO_USER, "password": HOLO_PASS},
        timeout=60
    )
    login_res.raise_for_status()
    token = login_res.json()["Login"]["Token"]

    print("Fetching customers...")
    cust_res = requests.get(
        f"{HOLO_URL}/Customer",
        headers={"Authorization": token},
        timeout=60
    )
    cust_res.raise_for_status()
    customers = cust_res.json().get("Customer", [])
    print(f"Retrieved {len(customers)} customers from Holoo.")

    upsert_sql = text("""
        INSERT INTO customers (code, name, phone, mobile, city, address, mandeh, cheque_debt, is_active, updated_at)
        VALUES (:code, :name, :phone, :mobile, :city, :address, :mandeh, :cheque_debt, :is_active, CURRENT_TIMESTAMP)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            phone = EXCLUDED.phone,
            mobile = EXCLUDED.mobile,
            city = EXCLUDED.city,
            address = EXCLUDED.address,
            mandeh = EXCLUDED.mandeh,
            cheque_debt = EXCLUDED.cheque_debt,
            is_active = EXCLUDED.is_active,
            updated_at = CURRENT_TIMESTAMP;
    """)

    count = 0
    with engine.begin() as conn:
        for item in customers:
            code = str(item.get("Code", "")).strip()
            if not code:
                continue
            conn.execute(upsert_sql, {
                "code": code,
                "name": item.get("Name", ""),
                "phone": item.get("Tel", ""),
                "mobile": item.get("Mobile", ""),
                "city": item.get("CityName", ""),
                "address": item.get("Address", ""),
                "mandeh": float(item.get("Mandeh", 0.0) or 0.0),
                "cheque_debt": float(item.get("debtInCheques", 0.0) or 0.0),
                "is_active": bool(item.get("IsActive", True))
            })
            count += 1

    print(f"Successfully synced {count} customers into database.")

if __name__ == "__main__":
    try:
        sync_from_holoo()
    except Exception as e:
        print(f"Error: {e}")
