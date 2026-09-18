import os
import sys
import json
from datetime import datetime
import requests

# ۱. ایمپورت موتور دیتابیس پروژه
try:
    import db
    engine = getattr(db, 'engine', None)
    SessionLocal = getattr(db, 'SessionLocal', None)
except Exception as e:
    print(f"خطا در بارگذاری db.py: {e}")
    sys.exit(1)

from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker

Base = getattr(db, 'Base', None) or declarative_base()
if not SessionLocal and engine:
    SessionLocal = sessionmaker(bind=engine)

# ۲. تعریف جداول دیتابیس دیجی‌کالا
class DigikalaVariant(Base):
    __tablename__ = "digikala_variants"
    id = Column(Integer, primary_key=True, autoincrement=True)
    variant_id = Column(BigInteger, unique=True, index=True, nullable=False)
    product_id = Column(BigInteger, nullable=True)
    title = Column(Text, nullable=False)
    holoo_code = Column(String(100), nullable=True, index=True)
    selling_price = Column(BigInteger, default=0)
    seller_stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

class DigikalaOrder(Base):
    __tablename__ = "digikala_orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(BigInteger, unique=True, index=True, nullable=False)
    order_number = Column(String(100), nullable=True)
    status = Column(String(50), default="new")
    total_price = Column(BigInteger, default=0)
    shipping_type = Column(String(50), default="digikala")
    order_date = Column(DateTime, nullable=True)
    items_count = Column(Integer, default=1)
    is_invoiced = Column(Boolean, default=False)
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# ۳. ایجاد جداول در PostgreSQL
print("۱. در حال ایجاد جداول دیجی‌کالا در دیتابیس PostgreSQL...")
Base.metadata.create_all(bind=engine)
print(" جداول digikala_variants و digikala_orders با موفقیت ساخته شدند.")

# ۴. همگام‌سازی و ذخیره کالاها از API دیجی‌کالا به دیتابیس
print("۲. در حال واکشی کالاها از پنل دیجی‌کالا و ذخیره در دیتابیس...")
from digikala_api import DigikalaClient
client = DigikalaClient()
resp = client.get_variants(page=1, size=50)

session = SessionLocal()
synced_count = 0

if resp.status_code == 200:
    data = resp.json().get("data", {})
    variants = data.get("items", []) or data.get("variants", [])
    for v in variants:
        vid = v.get("id") or v.get("variant_id")
        pid = v.get("product_id") or (v.get("product", {}) if isinstance(v.get("product"), dict) else {}).get("id")
        title = v.get("title") or v.get("product_title") or (v.get("product", {}) if isinstance(v.get("product"), dict) else {}).get("title", "بدون عنوان")
        
        price = v.get("price")
        price_val = 0
        if isinstance(price, dict):
            price_val = price.get("selling_price") or price.get("current_price") or 0
        elif price:
            price_val = price
            
        stock = v.get("seller_stock") if v.get("seller_stock") is not None else (v.get("stock") or 0)
        
        existing = session.query(DigikalaVariant).filter_by(variant_id=vid).first()
        if not existing:
            new_var = DigikalaVariant(
                variant_id=vid,
                product_id=pid,
                title=title,
                selling_price=int(price_val or 0),
                seller_stock=int(stock or 0),
                last_sync_at=datetime.utcnow()
            )
            session.add(new_var)
        else:
            existing.title = title
            existing.selling_price = int(price_val or 0)
            existing.seller_stock = int(stock or 0)
            existing.last_sync_at = datetime.utcnow()
        synced_count += 1
    session.commit()
    print(f" {synced_count} کالا با موفقیت در جدول digikala_variants ذخیره و همگام شد.")
else:
    print(f"خطا در دریافت کالاها: {resp.text}")

session.close()

# ۵. ساخت فایل روتر FastAPI برای اتصال به داشبورد فرانت‌اند
print("۳. در حال ایجاد digikala_router.py...")
router_code = '''from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import db
from digikala_api import DigikalaClient

router = APIRouter(prefix="/digikala", tags=["Digikala"])
client = DigikalaClient()

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.get("/status")
def get_status():
    """وضعیت اتصال و توکن دیجی‌کالا"""
    try:
        prof = client.get_profile()
        stats = client.get_orders_statistics()
        return {
            "connected": prof.status_code == 200,
            "seller_id": client.tokens.get("seller_id"),
            "profile_status": prof.status_code,
            "orders_statistics": stats.json().get("data", {}) if stats.status_code == 200 else {}
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@router.get("/variants")
def list_variants(db_session: Session = Depends(get_db)):
    """لیست کالاهای همگام‌شده با نگاشت هلو"""
    from setup_digikala_complete import DigikalaVariant
    items = db_session.query(DigikalaVariant).all()
    return [{
        "variant_id": i.variant_id,
        "product_id": i.product_id,
        "title": i.title,
        "holoo_code": i.holoo_code,
        "selling_price": i.selling_price,
        "seller_stock": i.seller_stock,
        "is_active": i.is_active,
        "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None
    } for i in items]

@router.patch("/variants/{variant_id}/stock")
def update_variant_stock(variant_id: int, count: int, db_session: Session = Depends(get_db)):
    """به‌روزرسانی موجودی هم‌زمان در دیجی‌کالا و دیتابیس"""
    from setup_digikala_complete import DigikalaVariant
    resp = client.update_stock(variant_id, count)
    if resp.status_code in [200, 204]:
        item = db_session.query(DigikalaVariant).filter_by(variant_id=variant_id).first()
        if item:
            item.seller_stock = count
            item.last_sync_at = datetime.utcnow()
            db_session.commit()
        return {"success": True, "variant_id": variant_id, "new_stock": count}
    raise HTTPException(status_code=resp.status_code, detail=resp.text)
'''

with open("digikala_router.py", "w", encoding="utf-8") as rf:
    rf.write(router_code)
print(" فایل digikala_router.py ساخته شد.")

# ۶. متصل کردن روتر به api.py
print("۴. بررسی و اتصال روتر به api.py...")
with open("api.py", "r", encoding="utf-8") as af:
    api_content = af.read()

if "digikala_router" not in api_content:
    backup_file = "api.py.backup_before_digikala"
    with open(backup_file, "w", encoding="utf-8") as bf:
        bf.write(api_content)
    
    # اضافه کردن ایمپورت و include_router
    new_api_content = "from digikala_router import router as digikala_router\n" + api_content
    # اضافه کردن بعد از تعریف app
    if "app = FastAPI" in new_api_content:
        parts = new_api_content.split("app = FastAPI", 1)
        # پیدا کردن اولین خط بعد از ساخت app
        subparts = parts[1].split("\n", 1)
        new_api_content = parts[0] + "app = FastAPI" + subparts[0] + "\napp.include_router(digikala_router)\n" + subparts[1]
    else:
        new_api_content += "\napp.include_router(digikala_router)\n"
        
    with open("api.py", "w", encoding="utf-8") as af:
        af.write(new_api_content)
    print(" روتر دیجی‌کالا با موفقیت به api.py اضافه شد.")
else:
    print(" روتر دیجی‌کالا قبلاً در api.py وجود داشت.")

print("\n اتوماسیون کامل دیجی‌کالا با موفقیت بر روی پروژه شما پیاده‌سازی شد!")
