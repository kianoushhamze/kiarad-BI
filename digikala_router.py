from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime
import db
from digikala_api import DigikalaClient

router = APIRouter(prefix="/digikala", tags=["Digikala"])
# Lazy client: missing tokens must not break app import/startup — only the
# request that actually needs Digikala reports a clear error.
_client = None


def get_client() -> DigikalaClient:
    global _client
    if _client is None:
        _client = DigikalaClient()
    return _client


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
        client = get_client()
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
def list_variants(limit: int = 300):
    """لیست کالاهای همگام‌شدهٔ دیجی‌کالا (جدول واقعی با کلید dkp_id)."""
    with db.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT dkp_id, title, holoo_code, price_selling, stock, status, updated_at
            FROM digikala_variants ORDER BY (holoo_code IS NULL), dkp_id LIMIT :l
        """), {"l": max(1, min(limit, 500))}).mappings().all()
    return [{
        "variant_id": r["dkp_id"],
        "product_id": r["dkp_id"],
        "title": r["title"],
        "holoo_code": r["holoo_code"],
        "selling_price": r["price_selling"],
        "seller_stock": r["stock"],
        "is_active": r["status"] == "active",
        "last_sync_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    } for r in rows]

@router.patch("/variants/{variant_id}/stock")
def update_variant_stock(variant_id: int, count: int, db_session: Session = Depends(get_db)):
    """به‌روزرسانی موجودی هم‌زمان در دیجی‌کالا و دیتابیس"""
    from setup_digikala_complete import DigikalaVariant
    resp = get_client().update_stock(variant_id, count)
    if resp.status_code in [200, 204]:
        item = db_session.query(DigikalaVariant).filter_by(variant_id=variant_id).first()
        if item:
            item.seller_stock = count
            item.last_sync_at = datetime.utcnow()
            db_session.commit()
        return {"success": True, "variant_id": variant_id, "new_stock": count}
    raise HTTPException(status_code=resp.status_code, detail=resp.text)
