"""Site CMS admin (داشبورد مدیریت سایت): manage per-product site metadata
(site category, image, visibility) and the base price that feeds the public
site catalog (site/data.json rebuilt via scripts/build_site_catalog.py).

Gate: CEO only — site pricing/visibility decisions are top-level.
"""
import base64
import binascii
import logging
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from operations import current_user

logger = logging.getLogger("kiarad_site_cms")
router = APIRouter(prefix="/site-cms", tags=["site_cms"])

ROOT = Path(__file__).resolve().parent
REBUILD_SCRIPT = ROOT / "scripts" / "build_site_catalog.py"


def _ceo(user):
    if not user or user.get("role") != "ceo" or not user.get("id"):
        raise HTTPException(403, "مدیریت سایت فقط با حساب مدیرعامل امکان‌پذیر است.")


class ProductMetaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_category: str | None = None
    image_url: str | None = None
    hidden: bool | None = None
    discount_price_irr: int | None = None


class PriceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    price_irr: int


@router.get("/products")
def list_products(q: str = "", hidden: str = "", user: dict = Depends(current_user)):
    _ceo(user)
    with engine.connect() as conn:
        sql = """
            SELECT p.code, p.name, p.price, p.stock, p.category,
                   COALESCE(NULLIF(m.site_category, ''), p.category) AS site_category,
                   m.image_url, COALESCE(m.hidden, FALSE) AS hidden,
                   m.discount_price_irr
            FROM products p
            LEFT JOIN cms_product_meta m ON m.code = p.code
            WHERE COALESCE(p.is_active, 1) = 1
        """
        params: dict = {}
        if q:
            sql += " AND (p.code ILIKE :q OR p.name ILIKE :q) "
            params["q"] = f"%{q}%"
        if hidden == "true":
            sql += " AND COALESCE(m.hidden, FALSE) = TRUE "
        elif hidden == "false":
            sql += " AND COALESCE(m.hidden, FALSE) = FALSE "
        sql += " ORDER BY p.name LIMIT 2000"
        rows = conn.execute(text(sql), params).mappings().all()
    products = []
    for r in rows:
        discount = r["discount_price_irr"]
        effective = discount if (discount is not None and r["price"] is not None
                                 and 0 < discount < r["price"]) else r["price"]
        products.append({
            "code": r["code"], "name": r["name"], "price_irr": r["price"],
            "price_toman": (round(r["price"] / 10) if r["price"] is not None else None),
            "discount_price_irr": discount,
            "discount_price_toman": (round(discount / 10) if discount is not None else None),
            "effective_price_irr": effective,
            "effective_price_toman": (round(effective / 10) if effective is not None else None),
            "stock": r["stock"], "site_category": r["site_category"],
            "image_url": r["image_url"], "hidden": bool(r["hidden"]),
        })
    return {
        "count": len(products),
        "hidden_count": sum(1 for p in products if p["hidden"]),
        "products": products,
    }


@router.patch("/products/{code}")
def patch_product_meta(code: str, data: ProductMetaPatch, user: dict = Depends(current_user)):
    _ceo(user)
    if data.discount_price_irr is not None and data.discount_price_irr < 0:
        raise HTTPException(400, "قیمت تخفیفی نمی‌تواند منفی باشد.")
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM products WHERE code=:c"), {"c": code}).first()
        if not exists:
            raise HTTPException(404, "کالایی با این کد در هلو پیدا نشد.")
        conn.execute(text("""
            INSERT INTO cms_product_meta(code, site_category, image_url, hidden, discount_price_irr, updated_at)
            VALUES (:c, :cat, :img, COALESCE(:hid, FALSE), :disc, NOW())
            ON CONFLICT (code) DO UPDATE SET
                site_category = COALESCE(:cat, cms_product_meta.site_category),
                image_url = COALESCE(:img, cms_product_meta.image_url),
                hidden = COALESCE(:hid, cms_product_meta.hidden),
                discount_price_irr = CASE WHEN :set_disc THEN :disc ELSE cms_product_meta.discount_price_irr END,
                updated_at = NOW()
        """), {"c": code, "cat": data.site_category, "img": data.image_url,
               "hid": data.hidden, "disc": data.discount_price_irr,
               "set_disc": "discount_price_irr" in data.model_fields_set})
    return {"ok": True, "code": code}


@router.post("/products/{code}/price")
def update_price(code: str, data: PriceUpdate, user: dict = Depends(current_user)):
    _ceo(user)
    if data.price_irr < 0:
        raise HTTPException(400, "قیمت نمی‌تواند منفی باشد.")
    with engine.begin() as conn:
        row = conn.execute(text("SELECT name, price FROM products WHERE code=:c"), {"c": code}).mappings().first()
        if not row:
            raise HTTPException(404, "کالایی با این کد در هلو پیدا نشد.")
        conn.execute(text("UPDATE products SET price=:p WHERE code=:c"), {"p": data.price_irr, "c": code})
    # This updates the local catalog only; no Holoo write is performed.
    logger.info("site-cms price change: user=%s code=%s name=%s old=%s new=%s",
                user.get("id"), code, row["name"], row["price"], data.price_irr)
    return {
        "ok": True, "code": code, "old_price_irr": row["price"],
        "new_price_irr": data.price_irr,
        "new_price_toman": round(data.price_irr / 10),
        "note": "قیمت در سامانهٔ کیاراد تغییر کرد؛ این عملیات قیمت را در هلو تغییر نمی‌دهد.",
    }


@router.post("/rebuild")
def rebuild_catalog(user: dict = Depends(current_user)):
    _ceo(user)
    if not REBUILD_SCRIPT.exists():
        raise HTTPException(500, f"اسکریپت بازسازی پیدا نشد: {REBUILD_SCRIPT}")
    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(REBUILD_SCRIPT)],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT),
            encoding="utf-8", errors="replace",
        )
    except Exception as exc:  # never crash the admin page on rebuild failure
        raise HTTPException(500, f"اجرای بازسازی کاتالوگ سایت شکست خورد: {exc}")
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise HTTPException(500, f"بازسازی کاتالوگ با خطا متوقف شد:\n{output.strip()}")
    return {"ok": True, "output": output.strip()}

# ---------------------------------------------------------------------------
# CMS banners (بنرهای صفحهٔ اصلی سایت) — image stored base64 (max 600KB),
# served via a cacheable endpoint. Public read = /site-banners (open, no
# personal data); admin CRUD = /site-cms/banners (CEO, like the rest of CMS).
# ---------------------------------------------------------------------------
BANNER_MAX_BYTES = 600 * 1024

banner_router = APIRouter(prefix="/site-banners", tags=["site_cms"])  # public, read-only


def _image_media_bytes(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    raise HTTPException(415, "فقط تصویر معتبر PNG، JPEG، GIF یا WebP پذیرفته می‌شود.")


def _clean_image(image_base64: str) -> str:
    """Accept raw base64 or a supported image data URL; return canonical base64."""
    value = "".join((image_base64 or "").split())
    declared_media = None
    if value.lower().startswith("data:"):
        header, separator, payload = value.partition(",")
        if not separator or header.lower() not in {
            "data:image/png;base64", "data:image/jpeg;base64",
            "data:image/gif;base64", "data:image/webp;base64",
        }:
            raise HTTPException(400, "نوع تصویر ارسالی پشتیبانی نمی‌شود.")
        declared_media = header[5:].split(";", 1)[0].lower()
        value = payload
    max_encoded = 4 * ((BANNER_MAX_BYTES + 2) // 3)
    if len(value) > max_encoded:
        raise HTTPException(413, "حجم تصویر باید کمتر از ۶۰۰ کیلوبایت باشد.")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "تصویر باید base64 معتبر باشد.")
    if len(raw) < 64:
        raise HTTPException(400, "تصویر خیلی کوچک یا نامعتبر است.")
    if len(raw) > BANNER_MAX_BYTES:
        raise HTTPException(413, "حجم تصویر باید کمتر از ۶۰۰ کیلوبایت باشد.")
    actual_media = _image_media_bytes(raw)
    if declared_media and declared_media != actual_media:
        raise HTTPException(400, "نوع اعلام‌شده با محتوای واقعی تصویر مطابقت ندارد.")
    return base64.b64encode(raw).decode("ascii")


def _image_media(b64: str) -> str:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(415, "تصویر ذخیره‌شده معتبر نیست.")
    return _image_media_bytes(raw)


def _clean_link_url(value: str | None) -> str | None:
    """Allow same-site absolute paths or HTTPS links; reject scriptable schemes."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise HTTPException(400, "پیوند بنر معتبر نیست.")
    if value.startswith("/") and not value.startswith("//"):
        return value
    parsed = urlsplit(value)
    if (parsed.scheme.lower() != "https" or not parsed.netloc or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise HTTPException(400, "پیوند بنر باید مسیر داخلی یا نشانی HTTPS معتبر باشد.")
    return value


def _safe_public_link(value: str | None) -> str | None:
    try:
        return _clean_link_url(value)
    except HTTPException:
        # Old records are not trusted just because they predate validation.
        return None


class BannerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=200)
    image_base64: str = Field(min_length=64, max_length=820000)
    link_url: str | None = Field(default=None, max_length=1000)
    sort: int = 0
    active: bool = True


class BannerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    image_base64: str | None = Field(default=None, max_length=820000)
    link_url: str | None = Field(default=None, max_length=1000)
    sort: int | None = None
    active: bool | None = None


@banner_router.get("")
def public_banners():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, title, link_url, sort FROM site_banners "
            "WHERE active = TRUE ORDER BY sort, id"
        )).mappings().all()
    return {"count": len(rows),
            "banners": [dict(r) | {"link_url": _safe_public_link(r['link_url']), "image_url": f"/site-banners/{r['id']}/image"} for r in rows]}


@banner_router.get("/{banner_id}/image")
def banner_image(banner_id: int):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT image_base64 FROM site_banners WHERE id = :id AND active = TRUE"
        ), {"id": banner_id}).first()
    if not row:
        raise HTTPException(404, "بنر پیدا نشد.")
    media_type = _image_media(row[0])
    raw = base64.b64decode(row[0], validate=True)
    return Response(content=raw, media_type=media_type,
                    headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})


def _banner_row(r) -> dict:
    return {"id": r["id"], "title": r["title"], "link_url": _safe_public_link(r["link_url"]),
            "sort": r["sort"], "active": bool(r["active"]),
            "image_url": f"/site-banners/{r['id']}/image"}


@router.get("/banners")
def list_banners(user: dict = Depends(current_user)):
    _ceo(user)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, title, link_url, sort, active FROM site_banners ORDER BY sort, id"
        )).mappings().all()
    return {"count": len(rows), "banners": [_banner_row(r) for r in rows]}


@router.post("/banners")
def create_banner(data: BannerIn, user: dict = Depends(current_user)):
    _ceo(user)
    b64 = _clean_image(data.image_base64)
    link_url = _clean_link_url(data.link_url)
    with engine.begin() as conn:
        row = conn.execute(text(
            "INSERT INTO site_banners(title, image_base64, link_url, sort, active) "
            "VALUES (:t, :img, :url, :s, :a) RETURNING id"
        ), {"t": data.title.strip(), "img": b64, "url": link_url,
            "s": data.sort, "a": data.active}).mappings().first()
    return {"ok": True, "id": int(row["id"])}


@router.patch("/banners/{banner_id}")
def patch_banner(banner_id: int, data: BannerPatch, user: dict = Depends(current_user)):
    _ceo(user)
    b64 = _clean_image(data.image_base64) if data.image_base64 else None
    link_url = _clean_link_url(data.link_url)
    with engine.begin() as conn:
        row = conn.execute(text(
            "UPDATE site_banners SET "
            "title = COALESCE(:t, title), image_base64 = COALESCE(:img, image_base64), "
            "link_url = COALESCE(:url, link_url), sort = COALESCE(:s, sort), "
            "active = COALESCE(:a, active) WHERE id = :id RETURNING id"
        ), {"t": data.title, "img": b64, "url": link_url,
            "s": data.sort, "a": data.active, "id": banner_id}).mappings().first()
    if not row:
        raise HTTPException(404, "بنری با این شناسه پیدا نشد.")
    return {"ok": True, "id": banner_id}


@router.delete("/banners/{banner_id}")
def delete_banner(banner_id: int, user: dict = Depends(current_user)):
    _ceo(user)
    with engine.begin() as conn:
        deleted = conn.execute(text(
            "DELETE FROM site_banners WHERE id = :id RETURNING id"), {"id": banner_id}).first()
    if not deleted:
        raise HTTPException(404, "بنری با این شناسه پیدا نشد.")
    return {"ok": True, "id": banner_id}

