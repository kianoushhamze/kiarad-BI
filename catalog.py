from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import text

from db import engine
from operations import current_user
from data_sources import ensure_source_storage, save_manual_fields, restore_holoo_fields

router = APIRouter(prefix="/catalog", tags=["catalog"])
MANAGERS = {"ceo", "sales_manager", "finance"}

@router.on_event('startup')
def initialize_data_sources():
    with engine.begin() as conn:ensure_source_storage(conn)

def manager(user=Depends(current_user)):
    if user["role"] not in MANAGERS:
        raise HTTPException(status_code=403, detail="دسترسی مدیریت کالا فقط برای نقش‌های مدیریتی مجاز است.")
    return user


def reader(user=Depends(current_user)):
    return user

class ChannelLink(BaseModel):
    channel: str = Field(min_length=2, max_length=30)
    external_id: str = Field(min_length=1, max_length=200)
    is_active: bool = True

class Reservation(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    channel: str = Field(min_length=2, max_length=30)
    external_order_id: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0, le=1000000000)

class ProductUpdate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    price: Optional[float] = Field(default=None, ge=0)
    price2: Optional[float] = Field(default=None, ge=0)
    stock: Optional[float] = Field(default=None, ge=0)
    min_stock: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None

class InventoryBatchInput(BaseModel):
    batch_code: str = Field(min_length=1, max_length=100)
    expiry_date: date
    quantity: float = Field(gt=0, le=1000000000)
    note: str = Field(default="", max_length=1000)

def ensure_inventory_batches():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory_batches (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                batch_code VARCHAR(100) NOT NULL,
                expiry_date DATE NOT NULL,
                quantity NUMERIC(14,3) NOT NULL CHECK (quantity > 0),
                note TEXT NOT NULL DEFAULT '',
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (product_id, batch_code)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_inventory_batches_expiry ON inventory_batches(expiry_date, product_id)"))

@router.get("/products/{product_id}/batches")
def list_inventory_batches(product_id: int, user=Depends(reader)):
    ensure_inventory_batches()
    with engine.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM products WHERE id=:id"), {"id": product_id}).first():
            raise HTTPException(status_code=404, detail="کالا پیدا نشد.")
        rows = conn.execute(text("""
            SELECT id, product_id, batch_code, expiry_date, quantity, note, created_at
            FROM inventory_batches WHERE product_id=:id ORDER BY expiry_date, batch_code
        """), {"id": product_id}).mappings().all()
    return {"items": [dict(row) for row in rows], "source": "manual", "updates_product_stock": False}

@router.post("/products/{product_id}/batches")
def create_inventory_batch(product_id: int, data: InventoryBatchInput, user=Depends(manager)):
    ensure_inventory_batches()
    if not data.batch_code.strip():
        raise HTTPException(status_code=422, detail="شمارهٔ بچ نمی‌تواند خالی باشد.")
    if data.expiry_date < datetime.now(ZoneInfo("Asia/Tehran")).date():
        raise HTTPException(status_code=422, detail="تاریخ انقضا در گذشته است؛ کالای منقضی را به‌عنوان بچ جدید ثبت نکنید.")
    with engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM products WHERE id=:id"), {"id": product_id}).first():
            raise HTTPException(status_code=404, detail="کالا پیدا نشد.")
        try:
            row = conn.execute(text("""
                INSERT INTO inventory_batches(product_id, batch_code, expiry_date, quantity, note, created_by)
                VALUES (:product_id, :batch_code, :expiry_date, :quantity, :note, :created_by)
                RETURNING id, product_id, batch_code, expiry_date, quantity, note, created_at
            """), {"product_id": product_id, "batch_code": data.batch_code.strip(),
                   "expiry_date": data.expiry_date, "quantity": data.quantity,
                   "note": data.note.strip(), "created_by": int(user["id"])}).mappings().one()
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise HTTPException(status_code=409, detail="این شمارهٔ بچ برای همین کالا قبلاً ثبت شده است.")
            raise
    return {"item": dict(row), "source": "manual", "updates_product_stock": False}

@router.get("/products")
def products(user=Depends(reader)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.code, p.name, p.category, p.price, p.price2, p.stock, p.min_stock,
                   p.is_active, p.updated_at,
                   ARRAY(SELECT o.field FROM data_field_overrides o WHERE o.entity='products' AND o.local_id=p.id ORDER BY o.field) AS manual_fields,
                   COALESCE(r.reserved_quantity, 0) AS reserved_quantity,
                   GREATEST(0, COALESCE(p.stock, 0) - COALESCE(r.reserved_quantity, 0)) AS available_stock
            FROM products p
            LEFT JOIN (
                SELECT product_id, SUM(quantity) AS reserved_quantity
                FROM inventory_reservations WHERE status='reserved' GROUP BY product_id
            ) r ON r.product_id=p.id
            ORDER BY p.id
        """)).mappings().all()
    return {"items": [dict(r) for r in rows]}

@router.patch("/products/{product_id}")
def update_product(product_id: int, data: ProductUpdate, user=Depends(manager)):
    values = data.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(status_code=400, detail="حداقل یک فیلد برای ویرایش ارسال کنید.")
    if 'is_active' in values:values['is_active']=int(values['is_active'])
    with engine.begin() as conn:
        save_manual_fields(conn,'products',product_id,values,int(user['id']))
        conn.execute(text('UPDATE products SET updated_at=NOW() WHERE id=:id'),{'id':product_id})
    return {"status": "updated", "product_id": product_id,'source':'manual','holoo_overwrite':False}

@router.post('/products/{product_id}/restore-holoo')
def restore_product(product_id:int,user=Depends(manager)):
    with engine.begin() as conn:return restore_holoo_fields(conn,'products',product_id,int(user['id']))

@router.get("/products/{product_id}/channels")
def product_channels(product_id: int, user=Depends(reader)):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, channel, external_id, is_active, last_synced_at FROM product_channels WHERE product_id=:id ORDER BY channel"), {"id": product_id}).mappings().all()
    return {"product_id": product_id, "items": [dict(r) for r in rows]}

@router.post("/products/{product_id}/channels")
def add_channel(product_id: int, data: ChannelLink, user=Depends(manager)):
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM products WHERE id=:id"), {"id": product_id}).first()
        if not exists: raise HTTPException(status_code=404, detail="کالا پیدا نشد.")
        try:
            row = conn.execute(text("""INSERT INTO product_channels(product_id,channel,external_id,is_active) VALUES (:p,:c,:e,:a) RETURNING id"""), {"p":product_id,"c":data.channel,"e":data.external_id,"a":1 if data.is_active else 0}).first()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"نگاشت کانال تکراری یا نامعتبر است: {exc}")
    return {"id": row[0], "status": "created"}

@router.get("/sync-runs")
def sync_runs(user=Depends(manager), limit: int = 50):
    limit = max(1, min(limit, 200))
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, channel, direction, status, started_at, finished_at, records_read, records_written FROM sync_runs ORDER BY id DESC LIMIT :limit"), {"limit":limit}).mappings().all()
    return {"items": [dict(r) for r in rows]}

@router.post("/products/{product_id}/reservations")
def reserve(product_id: int, data: Reservation, user=Depends(manager)):
    with engine.begin() as conn:
        product=conn.execute(text('SELECT stock FROM products WHERE id=:id FOR UPDATE'),{'id':product_id}).mappings().first()
        if not product:raise HTTPException(404,'کالا پیدا نشد.')
        reserved=conn.execute(text("SELECT COALESCE(SUM(quantity),0) FROM inventory_reservations WHERE product_id=:id AND status='reserved'"),{'id':product_id}).scalar()
        if data.quantity>float(product['stock'] or 0)-float(reserved or 0):
            raise HTTPException(409,'موجودی آزاد برای این رزرو کافی نیست.')
        try:
            row = conn.execute(text("""INSERT INTO inventory_reservations(product_id,channel,external_order_id,quantity,status,created_at) VALUES (:p,:c,:o,:q,'reserved',NOW()) RETURNING id"""), {"p":product_id,"c":data.channel,"o":data.external_order_id,"q":data.quantity}).first()
        except Exception as exc:
            raise HTTPException(status_code=409, detail="رزرو تکراری یا نامعتبر است.") from None
    return {"id": row[0], "status": "reserved"}
