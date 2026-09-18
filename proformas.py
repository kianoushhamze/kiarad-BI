import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from db import engine
from operations import current_user

router = APIRouter(tags=["proformas_kpi_and_ledger"])

class LocationRecord(BaseModel):
    salesperson_id: int
    latitude: float
    longitude: float
    battery_level: Optional[int] = 100
    activity: Optional[str] = "visiting"

class ProformaCreate(BaseModel):
    customer_id: int
    total_amount: float = Field(gt=0)
    notes: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = []

# ۱. لیست مشتریان بدون قفل ۴۰۱ و سازگار با هر دو فرمت آرایه و آبجکت
@router.get("/operations/customers-list")
@router.get("/customers-list")
def get_customers_dropdown():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, city, phone, credit_limit, customer_type 
            FROM customers ORDER BY name LIMIT 500
        """)).mappings().all()
        res = [dict(r) for r in rows]
        return res

# ۲. لیست کالاها بدون قفل ۴۰۱ و با قیمت و موجودی
@router.get("/operations/products-list")
@router.get("/products-list")
def get_products_dropdown():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, code, name, price, stock, category 
            FROM products ORDER BY category, name LIMIT 200
        """)).mappings().all()
        res = [dict(r) for r in rows]
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

# ۴. داشبورد و شاخص‌های کلیدی عملکرد (KPI) ویزیتورها
@router.get("/operations/visitors/kpis")
def get_visitors_kpis():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT 
                sp.id, sp.name, sp.phone,
                COALESCE(t.target_amount, 50000000) as monthly_target,
                COALESCE(s.sales_amount, 0) as total_sales,
                COALESCE(s.orders_count, 0) as orders_count,
                COALESCE(dr.visits_sum, 0) as total_visits,
                COALESCE(dr.reports_count, 0) as reports_count
            FROM salespersons sp
            LEFT JOIN (
                SELECT salesperson_id, SUM(total_amount) as sales_amount, COUNT(*) as orders_count 
                FROM sales GROUP BY salesperson_id
            ) s ON s.salesperson_id = sp.id
            LEFT JOIN (
                SELECT salesperson_id, target_amount FROM targets WHERE status='active'
            ) t ON t.salesperson_id = sp.id
            LEFT JOIN (
                SELECT salesperson_id, SUM(visits_count) as visits_sum, COUNT(*) as reports_count 
                FROM daily_reports GROUP BY salesperson_id
            ) dr ON dr.salesperson_id = sp.id
            ORDER BY total_sales DESC
        """)).mappings().all()
        
        kpi_list = []
        for r in rows:
            target = float(r["monthly_target"] or 0)
            actual = float(r["total_sales"] or 0)
            visits = int(r["total_visits"] or 0)
            orders = int(r["orders_count"] or 0)
            kpi_list.append({
                "salesperson_id": r["id"],
                "name": r["name"],
                "phone": r["phone"],
                "target": target,
                "actual_sales": actual,
                "achievement_percent": round((actual / target * 100), 1) if target else 0,
                "total_visits": visits,
                "orders_count": orders,
                "conversion_rate": round((orders / visits * 100), 1) if visits else 0
            })
        return kpi_list

@router.get("/operations/locations/latest")
def get_latest_locations():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT DISTINCT ON (s.id)
                s.id as salesperson_id, s.name, s.phone,
                COALESCE(l.latitude, 30.2839) as latitude,
                COALESCE(l.longitude, 57.0834) as longitude,
                COALESCE(l.battery_level, 100) as battery_level,
                COALESCE(l.activity, 'فعال') as activity,
                COALESCE(l.recorded_at, NOW()) as recorded_at
            FROM salespersons s
            LEFT JOIN salesperson_locations l ON l.salesperson_id = s.id
            ORDER BY s.id, l.recorded_at DESC NULLS LAST
        """)).mappings().all()
        return [dict(r) for r in rows]

@router.get("/operations/proformas/my")
def get_my_proformas():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.customer_id, c.name as customer_name, p.total_amount, 
                   p.status, p.credit_grade, p.created_at, p.notes
            FROM proforma_invoices p
            JOIN customers c ON c.id = p.customer_id
            ORDER BY p.id DESC LIMIT 50
        """)).mappings().all()
        return [dict(r) for r in rows]

@router.post("/operations/proformas")
def create_proforma(data: ProformaCreate):
    with engine.begin() as conn:
        cust = conn.execute(text("SELECT id, name, credit_limit FROM customers WHERE id = :id"), {"id": data.customer_id}).mappings().first()
        limit = float(cust["credit_limit"] or 0) if cust else 0
        grade = "A (عالی)" if limit == 0 or data.total_amount <= limit else "D (نیاز به تایید)"
        
        row = conn.execute(text("""
            INSERT INTO proforma_invoices (customer_id, total_amount, status, credit_grade, notes, created_at)
            VALUES (:cust_id, :amount, 'registered', :grade, :notes, NOW())
            RETURNING id, customer_id, total_amount, status, credit_grade
        """), {
            "cust_id": data.customer_id,
            "amount": data.total_amount,
            "grade": grade,
            "notes": data.notes
        }).mappings().first()
        return {"proforma": dict(row)}
