"""Kiarad CRUD API - generic add/edit/delete + file upload + excel import."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Header, Request, Response
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional, List
import shutil, os, uuid, json, re
from datetime import datetime
from db import engine
from sqlalchemy import text
import openpyxl
from operations import current_user,MANAGER_ROLES

router = APIRouter()

def _require_base_manager(table,user):
    if table in {'pharmacies','cosmetics_shops','kerman_bases_manual'} and user.get('role') not in MANAGER_ROLES:
        raise HTTPException(403,'پرسنل باید پایگاه جدید را از مسیر پیشنهاد و تأیید مدیر ثبت کند')

UPLOAD_ROOT = Path(__file__).resolve().parent / "kiarad-dashboard" / "public" / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
CATALOG_MAX_FILE_BYTES = 10 * 1024 * 1024
CATALOG_ALLOWED_EXTENSIONS = {
    "image": {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"},
    "pdf": {".pdf": "application/pdf"},
}


def _ensure_product_media_table(conn):
    """Create the empty storage schema required by the catalog endpoints."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS product_media (
            id SERIAL PRIMARY KEY,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            media_type VARCHAR(20) NOT NULL,
            file_path TEXT NOT NULL,
            file_name TEXT,
            mime_type VARCHAR(120),
            size_bytes BIGINT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            caption TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_product_media_product_id ON product_media(product_id)"
    ))


def _ensure_base_source_columns(conn):
    """Preserve existing bases; unknown provenance remains NULL."""
    for table in ("pharmacies", "cosmetics_shops"):
        conn.execute(text(f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS source TEXT"))


@router.on_event("startup")
def initialize_catalog_storage():
    with engine.begin() as conn:
        _ensure_product_media_table(conn)
        _ensure_base_source_columns(conn)

ALLOWED_TABLES = {
    "products": ["code", "name", "category", "price", "stock", "min_stock", "is_active"],
    "pharmacies": ["name", "city", "address", "phone", "type", "source"],
    "cosmetics_shops": ["name", "city", "address", "phone", "source"],
    "kerman_bases_manual": ["name", "city", "address", "phone", "type"],
    "cash_accounts": ["name", "account_type", "current_balance", "minimum_reserve", "is_active"],
    "fixed_expenses": ["title", "amount", "due_day", "is_active", "notes"],
    "product_media": ["product_id", "media_type", "file_path", "file_name", "mime_type", "size_bytes", "sort_order", "caption"],
}


def _check_table(t: str):
    if t not in ALLOWED_TABLES:
        raise HTTPException(400, "table not allowed: " + t)


def _validate_catalog_content(media_type: str, filename: str, content: bytes) -> tuple[str, str, str]:
    if media_type not in CATALOG_ALLOWED_EXTENSIONS:
        raise HTTPException(400, "نوع رسانه باید عکس یا پی‌دی‌اف باشد")
    safe_name = Path((filename or "").replace("\\", "/")).name.strip()[:180]
    extension = Path(safe_name).suffix.lower()
    mime_type = CATALOG_ALLOWED_EXTENSIONS[media_type].get(extension)
    if not safe_name or not mime_type:
        raise HTTPException(415, "پسوند فایل با نوع رسانه سازگار نیست")
    if not content or len(content) > CATALOG_MAX_FILE_BYTES:
        raise HTTPException(400, "فایل خالی است یا بیش از ۱۰ مگابایت حجم دارد")
    valid = (
        extension in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff")
        or extension == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n")
        or extension == ".webp" and len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
        or extension == ".pdf" and content.startswith(b"%PDF-")
    )
    if not valid:
        raise HTTPException(400, "محتوای فایل با پسوند اعلام‌شده سازگار نیست")
    return extension, mime_type, safe_name


def _catalog_file_path(public_path: str) -> Path:
    prefix = "/api/files/"
    if not isinstance(public_path, str) or not public_path.startswith(prefix):
        raise ValueError("invalid catalog file path")
    target = (UPLOAD_ROOT / public_path[len(prefix):]).resolve()
    target.relative_to(UPLOAD_ROOT.resolve())
    return target


@router.get("/crud/{table}")
def list_rows(table: str, limit: int = 500, offset: int = 0, q: Optional[str] = None):
    _check_table(table)
    cols = ALLOWED_TABLES[table]
    sql = "SELECT id, " + ", ".join(cols) + " FROM " + table
    params = {"lim": max(1,min(limit,5000)), "off": max(0,offset)}
    if q:
        searchable=[col for col in cols if col in {'name','title','code','caption'}]
        if searchable:
            sql += ' WHERE '+' OR '.join(f'{column} ILIKE :q' for column in searchable)
            params["q"] = "%" + q[:200] + "%"
    sql += " ORDER BY id DESC LIMIT :lim OFFSET :off"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/crud/{table}")
def create_row(table: str, payload: dict, user:dict=Depends(current_user)):
    _check_table(table)
    _require_base_manager(table,user)
    if table=='products':
        from data_entry import normalize_rows,allowed
        allowed('products',user)
        from data_sources import save_manual_fields
        values=normalize_rows('products',[payload],'IRR')[0]
        values={'min_stock':0,'is_active':1,**values}
        with engine.begin() as conn:
            ident=conn.execute(text('INSERT INTO products ('+', '.join(values)+',updated_at) VALUES ('+', '.join(':'+key for key in values)+',NOW()) RETURNING id'),values).scalar_one()
            save_manual_fields(conn,'products',ident,{key:value for key,value in values.items() if key!='code'},int(user['id']))
        return {'ok':True,'id':ident,'source':'manual'}
    cols = [c for c in ALLOWED_TABLES[table] if c in payload]
    if not cols:
        raise HTTPException(400, "no valid columns")
    placeholders = ", ".join(":" + c for c in cols)
    sql = "INSERT INTO " + table + " (" + ", ".join(cols) + ") VALUES (" + placeholders + ") RETURNING id"
    with engine.begin() as conn:
        r = conn.execute(text(sql), {c: payload[c] for c in cols}).fetchone()
    return {"ok": True, "id": r[0]}


@router.put("/crud/{table}/{row_id}")
def update_row(table: str, row_id: int, payload: dict, user:dict=Depends(current_user)):
    _check_table(table)
    _require_base_manager(table,user)
    if table=='products':
        from data_entry import allowed
        allowed('products',user)
        from data_sources import FIELDS,save_manual_fields
        with engine.begin() as conn:
            old=conn.execute(text('SELECT code FROM products WHERE id=:id FOR UPDATE'),{'id':row_id}).mappings().first()
            if not old:raise HTTPException(404,'کالا پیدا نشد.')
            if 'code' in payload and str(payload['code'])!=str(old['code']):raise HTTPException(409,'کد کالای موجود از این مسیر تغییر نمی‌کند؛ نگاشت هلو باید مستقل بررسی شود.')
            values={key:value for key,value in payload.items() if key in FIELDS['products']}
            save_manual_fields(conn,'products',row_id,values,int(user['id']))
        return {'ok':True,'source':'manual'}
    cols = [c for c in ALLOWED_TABLES[table] if c in payload]
    if not cols:
        raise HTTPException(400, "no valid columns")
    sets = ", ".join(c + " = :" + c for c in cols)
    sql = "UPDATE " + table + " SET " + sets + " WHERE id = :id"
    params = {c: payload[c] for c in cols}
    params["id"] = row_id
    with engine.begin() as conn:
        conn.execute(text(sql), params)
    return {"ok": True}


@router.delete("/crud/{table}/{row_id}")
def delete_row(table: str, row_id: int, user:dict=Depends(current_user)):
    _check_table(table)
    _require_base_manager(table,user)
    sql = "DELETE FROM " + table + " WHERE id = :id"
    with engine.begin() as conn:
        conn.execute(text(sql), {"id": row_id})
    return {"ok": True}


@router.post("/upload/product-media")
async def upload_product_media(
    product_id: int = Form(...),
    media_type: str = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    content = await file.read(CATALOG_MAX_FILE_BYTES + 1)
    ext, mime_type, safe_name = _validate_catalog_content(media_type, file.filename or "", content)
    sub = "images" if media_type == "image" else "pdfs"
    with engine.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM products WHERE id=:id"), {"id": product_id}).first():
            raise HTTPException(404, "کالا پیدا نشد")
    folder = UPLOAD_ROOT / "products" / sub
    folder.mkdir(parents=True, exist_ok=True)
    fname = str(uuid.uuid4()) + ext
    dest = folder / fname
    dest.write_bytes(content)
    size = len(content)
    rel = "/api/files/products/" + sub + "/" + fname
    try:
        with engine.begin() as conn:
            r = conn.execute(text("""
                INSERT INTO product_media (product_id, media_type, file_path, file_name, mime_type, size_bytes, caption)
                VALUES (:pid, :mt, :fp, :fn, :mime, :sz, :cap) RETURNING id
            """), {"pid": product_id, "mt": media_type, "fp": rel, "fn": safe_name,
                   "mime": mime_type, "sz": size, "cap": caption[:500]}).fetchone()
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return {"ok": True, "id": r[0], "url": rel, "size": size}


@router.post("/upload/catalog")
async def upload_catalog(file: UploadFile = File(...), caption: str = Form("")):
    content = await file.read(CATALOG_MAX_FILE_BYTES + 1)
    guessed_type = "pdf" if Path(file.filename or "").suffix.lower() == ".pdf" else "image"
    ext, _, _ = _validate_catalog_content(guessed_type, file.filename or "", content)
    folder = UPLOAD_ROOT / "catalog"
    folder.mkdir(parents=True, exist_ok=True)
    fname = str(uuid.uuid4()) + ext
    dest = folder / fname
    dest.write_bytes(content)
    rel = "/api/files/catalog/" + fname
    return {"ok": True, "url": rel, "size": len(content)}


@router.get("/product-media/{product_id}")
def list_product_media(product_id: int):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, product_id, media_type, file_path, file_name, size_bytes, sort_order, caption FROM product_media WHERE product_id = :pid ORDER BY sort_order, id"
        ), {"pid": product_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.delete("/product-media/{media_id}")
def delete_product_media(media_id: int):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT file_path FROM product_media WHERE id = :id"), {"id": media_id}).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        rel = row[0]
        try:
            fp = _catalog_file_path(rel)
        except ValueError:
            fp = None
        conn.execute(text("DELETE FROM product_media WHERE id = :id"), {"id": media_id})
    try:
        if fp and fp.exists():
            fp.unlink()
    except Exception:
        pass
    return {"ok": True}


@router.post("/import/excel/{table}")
async def import_excel(table: str, file: UploadFile = File(...), user:dict=Depends(current_user)):
    _check_table(table)
    _require_base_manager(table,user)
    if table=='products':
        from data_entry import excel_preview
        return await excel_preview('products',file,'IRR','',user)
    cols = ALLOWED_TABLES[table]
    try:
        wb = openpyxl.load_workbook(file.file, data_only=True)
    except Exception as e:
        raise HTTPException(400, "cannot read excel: " + str(e))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"ok": True, "inserted": 0, "skipped": 0, "errors": []}
    header = [str(c).strip().lower() if c else "" for c in rows[0]]
    mapping = {}
    for col in cols:
        if col in header:
            mapping[col] = header.index(col)
    if not mapping:
        return {"ok": False, "error": "no matching columns. expected: " + ", ".join(cols)}
    inserted = 0
    skipped = 0
    errors = []
    with engine.begin() as conn:
        for i, r in enumerate(rows[1:], start=2):
            try:
                payload = {}
                empty = True
                for col, idx in mapping.items():
                    v = r[idx] if idx < len(r) else None
                    if v is not None and str(v).strip() != "":
                        empty = False
                    payload[col] = v
                if empty:
                    skipped += 1
                    continue
                placeholders = ", ".join(":" + c for c in payload)
                sql = "INSERT INTO " + table + " (" + ", ".join(payload) + ") VALUES (" + placeholders + ")"
                conn.execute(text(sql), payload)
                inserted += 1
            except Exception as e:
                errors.append("row " + str(i) + ": " + str(e))
    return {"ok": True, "inserted": inserted, "skipped": skipped, "errors": errors[:10]}


@router.get("/import/template/{table}")
def template_excel(table: str):
    _check_table(table)
    cols = ALLOWED_TABLES[table]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(cols)
    for c in cols:
        ws.column_dimensions[ws.cell(row=1, column=cols.index(c) + 1).column_letter].width = 22
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=" + table + "_template.xlsx"},
    )

from fastapi.responses import FileResponse as _FR
from fastapi import HTTPException as _HE

@router.get("/files/{path:path}")
def serve_file(path: str, request: Request, user: dict = Depends(current_user)):
    if not re.fullmatch(r"(?:catalog|products/(?:images|pdfs))/[A-Za-z0-9][A-Za-z0-9._-]*", path):
        raise _HE(403, "دسترسی به این مسیر فایل مجاز نیست")
    target = (UPLOAD_ROOT / path).resolve()
    root = UPLOAD_ROOT.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise _HE(403, "forbidden")
    if not target.exists() or not target.is_file():
        raise _HE(404, "not found")
    import mimetypes
    mt, _ = mimetypes.guess_type(str(target))
    headers = {"Cache-Control": "private, no-cache", "Vary": "Authorization, Cookie",
               "X-Content-Type-Options": "nosniff"}
    response = _FR(str(target), media_type=mt or "application/octet-stream",
                   stat_result=target.stat(), headers=headers)
    etag = response.headers["etag"]
    validators = request.headers.get("if-none-match", "").split(",")
    if any(value.strip().removeprefix("W/") in (etag, "*") for value in validators):
        return Response(status_code=304, headers={**headers, "ETag": etag})
    return response

@router.post("/upload/catalog-file")
async def upload_catalog_file(
    media_type: str = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    content = await file.read(CATALOG_MAX_FILE_BYTES + 1)
    ext, mime_type, safe_name = _validate_catalog_content(media_type, file.filename or "", content)
    folder = UPLOAD_ROOT / "catalog"
    folder.mkdir(parents=True, exist_ok=True)
    fname = str(uuid.uuid4()) + ext
    dest = folder / fname
    dest.write_bytes(content)
    size = len(content)
    rel = "/api/files/catalog/" + fname
    try:
        with engine.begin() as conn:
            r = conn.execute(text("""
                INSERT INTO product_media (product_id, media_type, file_path, file_name, mime_type, size_bytes, caption)
                VALUES (NULL, :mt, :fp, :fn, :mime, :sz, :cap) RETURNING id
            """), {"mt": media_type, "fp": rel, "fn": safe_name,
                   "mime": mime_type, "sz": size, "cap": caption[:500]}).fetchone()
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return {"ok": True, "id": r[0], "url": rel, "size": size}


@router.get("/catalog-files")
def list_catalog_files():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, media_type, file_path, file_name, size_bytes, caption, created_at FROM product_media WHERE product_id IS NULL ORDER BY id DESC"
        )).fetchall()
    return [dict(r._mapping) for r in rows]


@router.delete("/catalog-files/{fid}")
def delete_catalog_file(fid: int):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT file_path FROM product_media WHERE id = :id AND product_id IS NULL"), {"id": fid}).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        rel = row[0]
        try:
            fp = _catalog_file_path(rel)
        except ValueError:
            fp = None
        conn.execute(text("DELETE FROM product_media WHERE id = :id"), {"id": fid})
    try:
        if fp and fp.exists():
            fp.unlink()
    except Exception:
        pass
    return {"ok": True}
