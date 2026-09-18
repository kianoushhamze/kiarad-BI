from fastapi import APIRouter, Depends, HTTPException
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
