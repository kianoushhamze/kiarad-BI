import os
import math
import re
import unicodedata
from datetime import datetime, date, timedelta
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from db import engine
from stock_reservations import lock_products, reservation_totals, reserved_quantity
from iran_time import iran_today
from operations import MANAGER_ROLES, current_user, require_manager
from daily_proforma_export import EXPORT_DIR, build_export
from holoo_mappings import ensure_holoo_entity_mappings
from product_pricing import ensure_product_prices, selected_price

router = APIRouter(tags=["proformas_kpi_and_ledger"])


def _ensure_proforma_storage(conn):
    ensure_product_prices(conn)
    ensure_holoo_entity_mappings(conn)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS proforma_invoices (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            salesperson_id INTEGER REFERENCES salespersons(id),
            total_amount NUMERIC(18, 2) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            credit_grade VARCHAR(20),
            notes TEXT,
            items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            channel VARCHAR(30) NOT NULL,
            external_order_id VARCHAR(200) NOT NULL,
            quantity DOUBLE PRECISION NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'reserved',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_inventory_reservation UNIQUE (channel, external_order_id, product_id)
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS proforma_holoo_queue (
            id SERIAL PRIMARY KEY,
            proforma_id INTEGER NOT NULL UNIQUE REFERENCES proforma_invoices(id) ON DELETE CASCADE,
            operation_key VARCHAR(120) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            external_invoice_id VARCHAR(120),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_proforma_holoo_queue_status ON proforma_holoo_queue(status, created_at)"
    ))


@router.on_event("startup")
def initialize_proforma_queue_storage():
    with engine.begin() as conn:
        _ensure_proforma_storage(conn)

class LocationRecord(BaseModel):
    salesperson_id: int
    latitude: float
    longitude: float
    battery_level: Optional[int] = 100
    activity: Optional[str] = "visiting"

class ProformaCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    customer_id: int
    salesperson_id: Optional[int] = None
    total_amount: Optional[float] = Field(default=None, gt=0, lt=10**16)
    notes: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


def _holoo_queue_readiness(customer_code: Any, items: Any, product_codes: Dict[int, Any],
                           duplicate_product_ids=None, customer_mapping_duplicate=False) -> Dict[str, Any]:
    blockers = []
    normalized_customer_code = str(customer_code or "").strip()
    if customer_mapping_duplicate:
        blockers.append("کد هلو برای مشتری تکراری است و نگاشت باید اصلاح شود")
    elif not normalized_customer_code:
        blockers.append("کد هلو برای مشتری ثبت نشده است")
    if isinstance(items, str):
        try:
            items = json.loads(items)
        except (TypeError, ValueError):
            items = []
    if not isinstance(items, list) or not items:
        blockers.append("پیش‌فاکتور قلم معتبر ندارد")
        items = []
    missing_product_ids = []
    duplicate_product_ids = set(duplicate_product_ids or [])
    duplicate_item_ids = []
    for item in items:
        if not isinstance(item, dict):
            blockers.append("ساختار یکی از اقلام نامعتبر است")
            continue
        try:
            product_id = int(item.get("product_id"))
            quantity = float(item.get("quantity"))
        except (TypeError, ValueError):
            blockers.append("شناسه یا تعداد یکی از اقلام نامعتبر است")
            continue
        if not math.isfinite(quantity) or quantity <= 0:
            blockers.append(f"تعداد کالای {product_id} معتبر نیست")
        if not str(product_codes.get(product_id) or "").strip():
            (duplicate_item_ids if product_id in duplicate_product_ids else missing_product_ids).append(product_id)
    if missing_product_ids:
        joined = "، ".join(str(item) for item in sorted(set(missing_product_ids)))
        blockers.append("کد هلو برای کالاهای شناسهٔ " + joined + " ثبت نشده است")
    if duplicate_item_ids:
        joined = "، ".join(str(item) for item in sorted(set(duplicate_item_ids)))
        blockers.append("کد هلو برای کالاهای شناسهٔ " + joined + " تکراری است")
    return {"mapping_ready": not blockers, "blockers": blockers}

# ۱. لیست مشتریان بدون قفل ۴۰۱ و سازگار با هر دو فرمت آرایه و آبجکت
@router.get("/operations/customers-list")
@router.get("/customers-list")
def get_customers_dropdown():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, city, phone, NULL::text AS customer_type
            FROM customers ORDER BY name LIMIT 500
        """)).mappings().all()
        res = [dict(r) for r in rows]
        return res


def _customer_search_terms(value: Optional[str]):
    normalized = unicodedata.normalize('NFKC', value or '').translate(str.maketrans(
        'يكآأإى۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', 'یکااای01234567890123456789'))
    normalized = re.sub('[ـ\u064b-\u065f\u0670]', '', normalized).lower()
    return ''.join(char if char.isalnum() else ' ' for char in normalized).split()


@router.get("/directory/customers")
def get_customer_directory(q: Optional[str] = Query(default=None, max_length=100), user: dict = Depends(current_user)):
    """Contact directory for authenticated field staff; financial fields are kept separate."""
    query = """
        SELECT id, code, name, city, phone,
               NULL::text AS customer_type, NULL::text AS province_area
        FROM customers
    """
    params = {}
    terms = _customer_search_terms(q)
    if terms:
        # Search normalization only; original names/contact fields remain untouched.
        field = "lower(regexp_replace(translate(regexp_replace(concat_ws(' ',name,city,phone,code), '[ـ\u064b-\u065f\u0670]', '', 'g'), 'يكآأإى۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', 'یکااای01234567890123456789'), '[^[:alnum:]]+', ' ', 'g'))"
        clauses = []
        for index, term in enumerate(terms):
            key = f'q{index}'
            clauses.append(f"({field} LIKE :{key} OR replace({field},' ','') LIKE :{key})")
            params[key] = '%' + term + '%'
        query += ' WHERE ' + ' AND '.join(clauses)
    query += " ORDER BY name LIMIT 500"
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]

# ۲. لیست کالاها بدون قفل ۴۰۱ و با قیمت و موجودی
@router.get("/operations/products-list")
@router.get("/products-list")
def get_products_dropdown():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.code, p.name, p.price, p.price2, p.stock, p.category
            FROM products p
            ORDER BY p.category, p.name LIMIT 5000
        """)).mappings().all()
        res = [dict(r) for r in rows]
        totals = reservation_totals(conn, [r['id'] for r in res])
        for product in res:
            product['reserved_quantity'] = totals.get(product['id'], 0)
            product['available_stock'] = max(0, float(product['stock'] or 0) - product['reserved_quantity'])
        return res

# ۳. استخراج معین حساب مشتری از اسناد و فاکتورهای هلو
@router.get("/operations/customers/{customer_id}/ledger")
def get_customer_ledger(customer_id: int):
    with engine.connect() as conn:
        cust = conn.execute(text("SELECT id, name, city, credit_limit FROM customers WHERE id=:id"), {"id": customer_id}).mappings().first()
        if not cust:
            raise HTTPException(status_code=404, detail="مشتری یافت نشد")
            
        sales = conn.execute(text("SELECT id, total_amount, date FROM sales WHERE customer_id=:id ORDER BY date DESC"), {"id": customer_id}).mappings().all()
        payments = conn.execute(text("SELECT id, amount, payment_date FROM payments WHERE customer_id=:id ORDER BY payment_date DESC"), {"id": customer_id}).mappings().all()
        
        total_sales = sum(float(s["total_amount"] or 0) for s in sales)
        total_paid = sum(float(p["amount"] or 0) for p in payments)
        balance = total_sales - total_paid
        
        return {
            "customer": dict(cust),
            "total_sales": total_sales,
            "total_paid": total_paid,
            "current_balance": balance,
            "invoices": [dict(s) for s in sales],
            "payments": [dict(p) for p in payments]
        }

@router.get("/operations/customers/{customer_id}/credit")
def get_customer_credit(customer_id: int, proforma_amount: float = 0):
    # اعتبارسنجی سقف بدهی باید مبلغ همین پیش‌فاکتور را هم در نظر بگیرد؛
    # وگرنه مشتریِ نزدیک به سقف سبز نشان داده می‌شود و بعد از ثبت پیش‌فاکتور قرمز می‌شود.
    proforma_amount = max(0.0, float(proforma_amount or 0))
    with engine.connect() as conn:
        customer = conn.execute(
            text("SELECT id, name, credit_limit FROM customers WHERE id=:id"),
            {"id": customer_id},
        ).mappings().first()
        if not customer:
            raise HTTPException(status_code=404, detail="مشتری یافت نشد")

        totals = conn.execute(text("""
            SELECT
                COALESCE((SELECT SUM(total_amount) FROM sales WHERE customer_id=:id), 0) AS sales_total,
                COALESCE((SELECT SUM(amount) FROM payments WHERE customer_id=:id), 0) AS payments_total
        """), {"id": customer_id}).mappings().first()

    current_balance = float(totals["sales_total"] or 0) - float(totals["payments_total"] or 0)
    credit_limit = float(customer["credit_limit"] or 0)
    projected_balance = current_balance + proforma_amount
    if credit_limit <= 0:
        grade = "unrated"
        message = "برای این مشتری سقف اعتباری ثبت نشده است."
    elif projected_balance > credit_limit:
        grade = "red"
        if proforma_amount > 0:
            message = (
                f"با احتساب مبلغ {proforma_amount:,.0f} ریالی این پیش‌فاکتور، "
                "ماندهٔ بدهی مشتری از سقف اعتبار عبور می‌کند."
            )
        else:
            message = "ماندهٔ بدهی مشتری از سقف اعتبار عبور کرده است."
    elif projected_balance == credit_limit:
        grade = "yellow"
        message = "با این پیش‌فاکتور ماندهٔ بدهی دقیقاً به سقف اعتبار می‌رسد."
    else:
        grade = "green"
        message = "ماندهٔ بدهی مشتری + مبلغ این پیش‌فاکتور از سقف اعتبار بیشتر نیست."

    return {
        "customer_id": customer_id,
        "current_balance": current_balance,
        "proforma_amount": proforma_amount,
        "projected_balance": projected_balance,
        "credit_limit": credit_limit,
        "grade": grade,
        "message": message,
    }

# ۴. داشبورد و شاخص‌های کلیدی عملکرد (KPI) ویزیتورها
@router.get("/operations/visitors/kpis")
def get_visitors_kpis(user: dict = Depends(current_user)):
    salesperson_id = None
    if user.get("role") not in MANAGER_ROLES:
        salesperson_id = user.get("salesperson_id")
        if not salesperson_id:
            return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT 
                sp.id, sp.name, sp.phone,
                t.target_amount as period_target,
                t.start_date as target_start_date,
                t.end_date as target_end_date,
                COALESCE(s.sales_amount, 0) as total_sales,
                COALESCE(s.orders_count, 0) as orders_count,
                COALESCE(dr.visits_sum, 0) as total_visits,
                COALESCE(dr.reports_count, 0) as reports_count
            FROM salespersons sp
            LEFT JOIN LATERAL (
                SELECT target_amount, start_date, end_date
                FROM targets
                WHERE salesperson_id = sp.id AND status = 'active'
                  AND COALESCE(target_type, '') <> 'تسویه'
                  AND target_amount > 0
                  AND start_date IS NOT NULL AND end_date IS NOT NULL
                  AND CURRENT_DATE BETWEEN start_date AND end_date
                ORDER BY start_date DESC, id DESC
                LIMIT 1
            ) t ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(total_amount), 0) as sales_amount,
                       COUNT(*) as orders_count
                FROM sales
                WHERE salesperson_id = sp.id
                  AND (t.start_date IS NULL OR CAST(date AS DATE) BETWEEN t.start_date AND t.end_date)
            ) s ON TRUE
            LEFT JOIN LATERAL (
                SELECT COALESCE(SUM(visits_count), 0) as visits_sum,
                       COUNT(*) as reports_count
                FROM daily_reports
                WHERE salesperson_id = sp.id
                  AND (t.start_date IS NULL OR report_date BETWEEN t.start_date AND t.end_date)
            ) dr ON TRUE
            WHERE (:spid IS NULL OR sp.id = :spid)
            ORDER BY total_sales DESC
        """), {"spid": salesperson_id}).mappings().all()
        
        kpi_list = []
        for r in rows:
            target = float(r["period_target"]) if r["period_target"] is not None else None
            actual = float(r["total_sales"] or 0)
            visits = int(r["total_visits"] or 0)
            orders = int(r["orders_count"] or 0)
            kpi_list.append({
                "salesperson_id": r["id"],
                "name": r["name"],
                "phone": r["phone"],
                "target": target,
                "target_start_date": r["target_start_date"],
                "target_end_date": r["target_end_date"],
                "sales_period": "target" if target is not None else "all_time",
                "actual_sales": actual,
                "achievement_percent": round((actual / target * 100), 1) if target else None,
                "total_visits": visits,
                "orders_count": orders,
                "conversion_rate": round((orders / visits * 100), 1) if visits else None
            })
        return kpi_list

@router.get("/operations/locations/latest")
def get_latest_locations(salesperson_id: int = None, user: dict = Depends(current_user)):
    if user.get("role") not in {"ceo", "sales_manager"}:
        own_salesperson_id = user.get("salesperson_id")
        if not own_salesperson_id:
            raise HTTPException(status_code=403, detail="برای این حساب ویزیتوری متصل نیست")
        salesperson_id = int(own_salesperson_id)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ON (s.id)
                s.id as salesperson_id, s.name, s.phone,
                l.latitude as latitude,
                l.longitude as longitude,
                l.battery_level as battery_level,
                l.activity as activity,
                l.recorded_at AT TIME ZONE current_setting('TIMEZONE') as recorded_at
            FROM salespersons s
            LEFT JOIN salesperson_locations l ON l.salesperson_id = s.id
            WHERE (:spid IS NULL OR s.id = :spid) ORDER BY s.id, l.recorded_at DESC NULLS LAST
        """), {"spid": salesperson_id}).mappings().all()
        return [dict(r) for r in rows]

@router.get("/operations/proformas/my")
def get_my_proformas(user: dict = Depends(current_user)):
    salesperson_id = None
    if user.get("role") not in MANAGER_ROLES:
        salesperson_id = user.get("salesperson_id")
        if not salesperson_id:
            return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.customer_id, p.salesperson_id, c.name as customer_name, p.total_amount,
                   p.status, p.credit_grade, p.created_at, p.notes, p.items_json,
                   q.operation_key, q.status AS queue_status, q.attempt_count
            FROM proforma_invoices p
            JOIN customers c ON c.id = p.customer_id
            LEFT JOIN proforma_holoo_queue q ON q.proforma_id = p.id
            WHERE (:spid IS NULL OR p.salesperson_id = :spid)
            ORDER BY p.id DESC LIMIT 50
        """), {"spid": salesperson_id}).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("items_json"), str):
                try:
                    item["items_json"] = json.loads(item["items_json"])
                except (TypeError, ValueError):
                    item["items_json"] = []
            result.append(item)
        return result


@router.get("/operations/proformas/exports")
def list_proforma_exports(_: dict = Depends(require_manager)):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(EXPORT_DIR.glob("proformas_????-??-??.csv"), reverse=True)[:90]:
        stat = path.stat()
        items.append({"file_name": path.name, "size_bytes": stat.st_size,
                      "generated_at": datetime.fromtimestamp(stat.st_mtime).isoformat()})
    return {"items": items}


@router.post("/operations/proformas/exports/generate")
def generate_proforma_export(data: dict, _: dict = Depends(require_manager)):
    raw_date = str(data.get("date") or (iran_today() - timedelta(days=1)).isoformat())
    try: export_date = date.fromisoformat(raw_date)
    except ValueError: raise HTTPException(status_code=422, detail="تاریخ نامعتبر است")
    if export_date>iran_today():raise HTTPException(422,'برای تاریخ آینده خروجی ساخته نمی‌شود.')
    path, count = build_export(export_date)
    return {"status": "generated", "file_name": path.name, "records": count}


@router.get("/operations/proformas/exports/{file_name}")
def download_proforma_export(file_name: str, _: dict = Depends(require_manager)):
    if not file_name.startswith("proformas_") or not file_name.endswith(".csv") or Path(file_name).name != file_name:
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")
    path = EXPORT_DIR / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")
    return FileResponse(path, media_type="text/csv; charset=utf-8", filename=file_name)

@router.post("/operations/proformas")
def create_proforma(data: ProformaCreate, user: dict = Depends(current_user)):
    salesperson_id = data.salesperson_id if user.get("role") in MANAGER_ROLES else user.get("salesperson_id")
    if not salesperson_id:
        raise HTTPException(status_code=403, detail="برای ثبت پیش‌فاکتور، حساب ویزیتوری متصل لازم است")
    with engine.begin() as conn:
        cust = conn.execute(text("SELECT id, name, credit_limit FROM customers WHERE id = :id"), {"id": data.customer_id}).mappings().first()
        if not cust:
            raise HTTPException(status_code=404, detail="مشتری یافت نشد")

        total_amount = 0.0
        normalized_items = []
        seen_product_ids = set()
        if data.items:
            parsed_items = []
            for item in data.items:
                try:
                    raw_id = item.get('product_id')
                    if isinstance(raw_id, bool) or (isinstance(raw_id, float) and not raw_id.is_integer()):
                        raise ValueError()
                    product_id = int(raw_id)
                    if product_id <= 0 or isinstance(item.get('quantity'), bool):
                        raise ValueError()
                    quantity = float(item.get("quantity"))
                except (TypeError, ValueError, OverflowError):
                    raise HTTPException(status_code=422, detail="قلم پیش‌فاکتور نامعتبر است")
                if not math.isfinite(quantity) or quantity <= 0:
                    raise HTTPException(status_code=422, detail="تعداد هر کالا باید بیشتر از صفر باشد")
                if product_id in seen_product_ids:
                    raise HTTPException(status_code=422, detail="هر کالا را فقط در یک سطر وارد کنید")
                seen_product_ids.add(product_id)
                parsed_items.append((product_id, quantity, item))
            lock_products(conn, product_ids=seen_product_ids)
            for product_id, quantity, item in parsed_items:
                product = conn.execute(text("""
                    SELECT p.name, p.price, p.price2, p.stock
                    FROM products p WHERE p.id=:id FOR UPDATE
                """), {"id": product_id}).mappings().first()
                if not product:
                    raise HTTPException(status_code=404, detail="کالا یافت نشد")
                available_stock = float(product["stock"] or 0) - reserved_quantity(conn, product_id)
                if not math.isfinite(available_stock) or quantity > available_stock:
                    raise HTTPException(
                        status_code=409,
                        detail=f"موجودی قابل فروش «{product['name']}» کافی نیست؛ موجودی آزاد {available_stock:g} است",
                    )
                price_level=item.get('price_level',1)
                unit_price = selected_price(product,price_level)
                line_total = unit_price * quantity
                total_amount += line_total
                normalized_items.append({
                    "product_id": product_id,
                    "product_name": product["name"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "price_level": price_level,
                    "line_total": line_total,
                })
        elif data.total_amount is not None:
            total_amount = float(data.total_amount)

        if not math.isfinite(total_amount) or not 0 < total_amount < 10**16:
            raise HTTPException(status_code=422, detail="مبلغ پیش‌فاکتور باید مثبت و در محدودهٔ قابل ثبت باشد")

        balance = conn.execute(text("""
            SELECT
                COALESCE((SELECT SUM(total_amount) FROM sales WHERE customer_id=:id), 0) -
                COALESCE((SELECT SUM(amount) FROM payments WHERE customer_id=:id), 0)
        """), {"id": data.customer_id}).scalar() or 0
        limit = float(cust["credit_limit"] or 0)
        projected_balance = float(balance) + total_amount
        if limit <= 0 or projected_balance <= limit:
            grade, status_value = "green", "approved"
        elif float(balance) < limit:
            grade, status_value = "yellow", "pending"
        else:
            grade, status_value = "red", "pending"
        
        row = conn.execute(text("""
            INSERT INTO proforma_invoices
                (customer_id, salesperson_id, total_amount, status, credit_grade, notes, items_json, created_at)
            VALUES (:cust_id, :spid, :amount, :status, :grade, :notes, CAST(:items_json AS JSONB), NOW())
            RETURNING id, customer_id, total_amount, status, credit_grade
        """), {
            "cust_id": data.customer_id,
            "spid": salesperson_id,
            "amount": total_amount,
            "status": status_value,
            "grade": grade,
            "notes": data.notes,
            "items_json": json.dumps(normalized_items, ensure_ascii=False),
        }).mappings().first()
        proforma = dict(row)
        for item in normalized_items:
            conn.execute(text("""
                INSERT INTO inventory_reservations
                    (product_id, channel, external_order_id, quantity, status, created_at)
                VALUES (:product_id, 'proforma', :external_order_id, :quantity, 'reserved', NOW())
            """), {
                "product_id": item["product_id"],
                "external_order_id": "proforma:" + str(proforma["id"]),
                "quantity": item["quantity"],
            })
        return {
            "proforma_id": proforma["id"],
            "status": proforma["status"],
            "credit_grade": proforma["credit_grade"],
            "total_amount": proforma["total_amount"],
            "inventory_reserved": bool(normalized_items),
            "proforma": proforma,
        }


@router.post("/operations/proformas/{proforma_id}/queue")
def queue_proforma(proforma_id: int, _: dict = Depends(require_manager)):
    """Durable local handoff queue. No external invoice is created here."""
    with engine.begin() as conn:
        row = conn.execute(text("SELECT status, items_json FROM proforma_invoices WHERE id=:id FOR UPDATE"),
                           {"id": proforma_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="پیش‌فاکتور پیدا نشد")
        if row["status"] not in {"approved", "queued"}:
            raise HTTPException(status_code=409, detail="فقط پیش‌فاکتور تأییدشده قابل ورود به صف است")
        items = row["items_json"]
        if isinstance(items, str):
            items = json.loads(items)
        if not items:
            raise HTTPException(status_code=409, detail="پیش‌فاکتور بدون اقلام قابل ارسال نیست")
        operation_key = "holoo:proforma:" + str(proforma_id)
        queued = conn.execute(text("""
            INSERT INTO proforma_holoo_queue (proforma_id, operation_key, status)
            VALUES (:proforma_id, :operation_key, 'pending')
            ON CONFLICT (proforma_id) DO UPDATE
            SET updated_at = proforma_holoo_queue.updated_at
            RETURNING id, operation_key, status, attempt_count
        """), {"proforma_id": proforma_id, "operation_key": operation_key}).mappings().first()
        if row["status"] != "queued":
            conn.execute(text("UPDATE proforma_invoices SET status='queued' WHERE id=:id"), {"id": proforma_id})
        return {
            "proforma_id": proforma_id,
            "status": "queued",
            "queue_id": queued["id"],
            "operation_key": queued["operation_key"],
            "queue_status": queued["status"],
            "attempt_count": queued["attempt_count"],
            "external_submission": False,
        }


@router.get("/operations/proformas/holoo-queue")
def list_holoo_queue(_: dict = Depends(require_manager)):
    """Read-only preflight. This endpoint never sends an invoice to Holoo."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT q.id AS queue_id, q.proforma_id, q.operation_key, q.status AS queue_status,
                   q.attempt_count, q.last_error, q.external_invoice_id, q.created_at, q.updated_at,
                   p.status AS proforma_status, p.customer_id, p.items_json,
                   c.name AS customer_name, cm.holoo_erp_code AS customer_erp_code,
                   cm.local_id AS customer_mapping_id,
                   cm.duplicate_count AS customer_mapping_duplicate_count
            FROM proforma_holoo_queue q
            JOIN proforma_invoices p ON p.id=q.proforma_id
            JOIN customers c ON c.id=p.customer_id
            LEFT JOIN (
                SELECT local_id, holoo_erp_code,
                       COUNT(*) OVER (PARTITION BY holoo_erp_code) AS duplicate_count
                FROM holoo_entity_mappings WHERE entity_type='customer'
            ) cm ON cm.local_id=c.id
            ORDER BY q.id
            LIMIT 200
        """)).mappings().all()
        product_ids = set()
        parsed_items = {}
        for row in rows:
            items = row["items_json"]
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except (TypeError, ValueError):
                    items = []
            parsed_items[row["queue_id"]] = items
            if isinstance(items, list):
                for item in items:
                    try:
                        product_ids.add(int(item.get("product_id")))
                    except (AttributeError, TypeError, ValueError):
                        continue
        product_codes = {}
        if product_ids:
            code_rows = conn.execute(text(
                """SELECT local_id, holoo_erp_code, duplicate_count
                   FROM (
                       SELECT local_id, holoo_erp_code,
                              COUNT(*) OVER (PARTITION BY holoo_erp_code) AS duplicate_count
                       FROM holoo_entity_mappings WHERE entity_type='product'
                   ) mapped
                   WHERE local_id = ANY(:ids)"""
            ), {"ids": list(product_ids)}).mappings().all()
            product_codes = {int(row["local_id"]): row["holoo_erp_code"] for row in code_rows if row["duplicate_count"] == 1}
            duplicate_product_ids = {int(row["local_id"]) for row in code_rows if row["duplicate_count"] > 1}
        else:
            duplicate_product_ids = set()

    result = []
    for row in rows:
        item = dict(row)
        item["items_json"] = parsed_items[row["queue_id"]]
        item.update(_holoo_queue_readiness(
            item["customer_erp_code"], item["items_json"], product_codes, duplicate_product_ids,
            bool(item["customer_mapping_duplicate_count"] and item["customer_mapping_duplicate_count"] > 1),
        ))
        item["external_submission"] = False
        result.append(item)
    return {"items": result, "external_submission": False}


@router.post("/operations/proformas/{proforma_id}/approve")
def approve_proforma(proforma_id: int, _: dict = Depends(require_manager)):
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT status FROM proforma_invoices WHERE id=:id FOR UPDATE"
        ), {"id": proforma_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="پیش‌فاکتور پیدا نشد")
        if row["status"] == "approved":
            return {"proforma_id": proforma_id, "status": "approved"}
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="فقط پیش‌فاکتور در انتظار بررسی قابل تأیید است")
        conn.execute(text(
            "UPDATE proforma_invoices SET status='approved' WHERE id=:id"
        ), {"id": proforma_id})
    return {"proforma_id": proforma_id, "status": "approved"}


@router.post("/operations/proformas/{proforma_id}/reject")
def reject_proforma(proforma_id: int, _: dict = Depends(require_manager)):
    """Reject a pending proforma and atomically release its reservations."""
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT status FROM proforma_invoices WHERE id=:id FOR UPDATE"
        ), {"id": proforma_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="پیش‌فاکتور پیدا نشد")
        if row["status"] == "rejected":
            return {"proforma_id": proforma_id, "status": "rejected", "reservations_released": 0}
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="فقط پیش‌فاکتور در انتظار بررسی قابل رد است")
        conn.execute(text(
            "UPDATE proforma_invoices SET status='rejected' WHERE id=:id"
        ), {"id": proforma_id})
        released = conn.execute(text("""
            UPDATE inventory_reservations
            SET status='released'
            WHERE channel='proforma'
              AND external_order_id=:external_order_id
              AND status='reserved'
        """), {"external_order_id": "proforma:" + str(proforma_id)})
    return {
        "proforma_id": proforma_id,
        "status": "rejected",
        "reservations_released": max(0, int(released.rowcount or 0)),
    }


@router.post("/operations/proformas/{proforma_id}/cancel")
def cancel_proforma(proforma_id: int, user: dict = Depends(current_user)):
    """Cancel a local proforma and release its active inventory reservations atomically."""
    is_manager = user.get("role") in MANAGER_ROLES
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, salesperson_id, status
            FROM proforma_invoices
            WHERE id = :id
            FOR UPDATE
        """), {"id": proforma_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="پیش‌فاکتور پیدا نشد")

        if not is_manager and (
            user.get("role") not in {"salesperson", "visitor"}
            or not user.get("salesperson_id")
            or int(user["salesperson_id"]) != int(row["salesperson_id"] or 0)
        ):
            raise HTTPException(status_code=403, detail="اجازهٔ لغو این پیش‌فاکتور را ندارید")

        if row["status"] == "cancelled":
            return {"proforma_id": proforma_id, "status": "cancelled", "reservations_released": 0}
        if row["status"] not in {"pending", "approved", "queued"}:
            raise HTTPException(status_code=409, detail="وضعیت این پیش‌فاکتور اجازهٔ لغو نمی‌دهد")

        conn.execute(text("""
            UPDATE proforma_invoices
            SET status = 'cancelled'
            WHERE id = :id
        """), {"id": proforma_id})
        released = conn.execute(text("""
            UPDATE inventory_reservations
            SET status = 'released'
            WHERE channel = 'proforma'
              AND external_order_id = :external_order_id
              AND status = 'reserved'
        """), {"external_order_id": "proforma:" + str(proforma_id)})

        return {
            "proforma_id": proforma_id,
            "status": "cancelled",
            "reservations_released": max(0, int(released.rowcount or 0)),
        }
