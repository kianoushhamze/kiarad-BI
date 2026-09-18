from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import engine
from operations import current_user

router = APIRouter(prefix="/catalog", tags=["catalog"])
MANAGERS = {"ceo", "sales_manager", "finance"}

def manager(user=Depends(current_user)):
    if user["role"] not in MANAGERS:
        raise HTTPException(status_code=403, detail="دسترسی مدیریت کالا فقط برای نقش‌های مدیریتی مجاز است.")
    return user

class ChannelLink(BaseModel):
    channel: str = Field(min_length=2, max_length=30)
    external_id: str = Field(min_length=1, max_length=200)
    is_active: bool = True

class Reservation(BaseModel):
    channel: str = Field(min_length=2, max_length=30)
    external_order_id: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0)

class ProductUpdate(BaseModel):
    price: Optional[float] = Field(default=None, ge=0)
    stock: Optional[float] = Field(default=None, ge=0)
    min_stock: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None

@router.get("/products")
def products(user=Depends(manager)):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, code, name, category, price, stock, min_stock, is_active, updated_at FROM products ORDER BY id")).mappings().all()
    return {"items": [dict(r) for r in rows]}

@router.patch("/products/{product_id}")
def update_product(product_id: int, data: ProductUpdate, user=Depends(manager)):
    values = data.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(status_code=400, detail="حداقل یک فیلد برای ویرایش ارسال کنید.")
    values["is_active"] = int(values["is_active"]) if "is_active" in values else None
    sets = [f"{key}=:{key}" for key in values if values[key] is not None]
    sets.append("updated_at=CURRENT_TIMESTAMP")
    params = {k:v for k,v in values.items() if v is not None}; params["id"] = product_id
    with engine.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM products WHERE id=:id"), {"id": product_id}).first():
            raise HTTPException(status_code=404, detail="کالا پیدا نشد.")
        conn.execute(text(f"UPDATE products SET {', '.join(sets)} WHERE id=:id"), params)
    return {"status": "updated", "product_id": product_id}

@router.get("/products/{product_id}/channels")
def product_channels(product_id: int, user=Depends(manager)):
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
        try:
            row = conn.execute(text("""INSERT INTO inventory_reservations(product_id,channel,external_order_id,quantity,status) VALUES (:p,:c,:o,:q,'reserved') RETURNING id"""), {"p":product_id,"c":data.channel,"o":data.external_order_id,"q":data.quantity}).first()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"رزرو تکراری یا نامعتبر است: {exc}")
    return {"id": row[0], "status": "reserved"}
