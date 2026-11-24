from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime
import math
from operations import current_user
from stock_reservations import reserved_quantity
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



def _variants_key_column(conn) -> str:
    """کلید شناسهٔ دیجی‌کالا در نصب فعلی: dkp_id (اسکیمای جدید) یا variant_id (قدیمی)."""
    return conn.execute(text("""SELECT CASE
          WHEN COUNT(*) FILTER (WHERE column_name = 'dkp_id') > 0 THEN 'dkp_id'
          WHEN COUNT(*) FILTER (WHERE column_name = 'variant_id') > 0 THEN 'variant_id'
          ELSE '' END
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'digikala_variants'""")).scalar() or ""


class MappingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    holoo_code: str = Field(min_length=1)


@router.patch("/variants/{variant_id}/mapping")
def set_variant_mapping(variant_id: int, body: MappingUpdate, user: dict = Depends(current_user), db_session: Session = Depends(get_db)):
    """ثبت نگاشت واریانت دیجی‌کالا ← کد هلو (جایگزین جریان دستی variant_map.csv).

    کلید مسیر شناسهٔ دیجی‌کالاست: در اسکیمای فعلی dkp_id و در نصب‌های قدیمی variant_id —
    هر دو همان شناسهٔ دیجی‌کالا هستند و کد تأمین‌کننده در خروجی اکسل هم همین است.
    """
    if user.get("role") != "ceo":
        raise HTTPException(403, "دسترسی مدیرعامل لازم است.")
    code = body.holoo_code.strip()
    if code and not db_session.execute(text("SELECT 1 FROM products WHERE code = :code"), {"code": code}).scalar():
        raise HTTPException(422, "کالای هلو یافت نشد.")
    if not code:
        raise HTTPException(422, "کد هلو نمی‌تواند خالی باشد.")
    with db.engine.connect() as conn:
        key_col = _variants_key_column(conn)
    if not key_col:
        raise HTTPException(503, "جدول digikala_variants یافت نشد؛ ابتدا همگام‌سازی دیجی‌کالا را اجرا کنید.")
    ts_col = db_session.execute(text("""SELECT CASE
          WHEN COUNT(*) FILTER (WHERE column_name = 'updated_at') > 0 THEN 'updated_at'
          WHEN COUNT(*) FILTER (WHERE column_name = 'last_sync_at') > 0 THEN 'last_sync_at'
          ELSE '' END
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'digikala_variants'""")).scalar() or ""
    sets = ["holoo_code = :code"]
    if ts_col:
        sets.append(f"{ts_col} = NOW()")
    result = db_session.execute(text(f"""
        UPDATE digikala_variants SET {', '.join(sets)} WHERE {key_col} = :vid
    """), {"code": code, "vid": variant_id})
    if result.rowcount == 0:
        db_session.rollback()
        raise HTTPException(404, f"واریانت {variant_id} در digikala_variants یافت نشد.")
    db_session.commit()
    return {"success": True, "variant_id": variant_id, "holoo_code": code, "applied_to_column": key_col}


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


@router.post("/variants/{variant_key}/sync-stock")
def sync_variant_stock(variant_key: int, user: dict = Depends(current_user)):
    """Publish dashboard availability to one mapped seller variant."""
    if user.get("role") != "ceo":
        raise HTTPException(403, "دسترسی مدیرعامل لازم است.")
    with db.engine.begin() as conn:
        variant = conn.execute(text("""
            SELECT raw->>'id' AS seller_id, holoo_code, status
            FROM digikala_variants WHERE dkp_id = :key FOR UPDATE
        """), {"key": variant_key}).mappings().first()
        if not variant:
            raise HTTPException(404, "کالای دیجی‌کالا یافت نشد.")
        seller_id = variant["seller_id"] or ""
        if not seller_id.isascii() or not seller_id.isdecimal() or int(seller_id) <= 0:
            raise HTTPException(409, "شناسهٔ فروشندهٔ این کالا در دیجی‌کالا موجود نیست.")
        if not variant["holoo_code"] or variant["status"] != "active":
            raise HTTPException(409, "برای ارسال موجودی، کالا باید فعال و به هلو متصل باشد.")
        product = conn.execute(text("""
            SELECT id, is_active, stock FROM products WHERE code = :code FOR UPDATE
        """), {"code": variant["holoo_code"]}).mappings().first()
        if not product or product["stock"] is None or not math.isfinite(float(product["stock"])):
            raise HTTPException(409, "موجودی کالای متصل در داشبورد مشخص نیست.")
        count = 0
        if product["is_active"]:
            count = max(0, math.floor(float(product["stock"]) - reserved_quantity(conn, product["id"])))
        try:
            response = get_client().update_stock(int(seller_id), count)
        except Exception as exc:
            raise HTTPException(502, "ارسال موجودی به دیجی‌کالا انجام نشد.") from exc
        if response.status_code not in (200, 201, 204):
            raise HTTPException(502, f"دیجی‌کالا موجودی را نپذیرفت ({response.status_code}).")
        conn.execute(text("""
            UPDATE digikala_variants SET stock = :count, updated_at = NOW() WHERE dkp_id = :key
        """), {"count": count, "key": variant_key})
    return {"new_stock": count}
