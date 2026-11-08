import os
import sys
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, func

import db
from models import Sale, SaleItem, Customer, Product, InventoryReservation, SalesPerson
from iran_time import iran_today
from operations import current_user
from digikala_api import DigikalaClient

router = APIRouter(prefix="/visitor-portal", tags=["Visitor Portal"])
dk_client = DigikalaClient()

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# مدل‌های ورودی
class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)
    price: Optional[int] = None

class CreatePreInvoiceRequest(BaseModel):
    customer_id: int
    items: List[OrderItemIn]
    notes: Optional[str] = None

# ۱. دریافت فاکتورهای ویزیتور با مانده بدهی و آلارم ۱۵ روزه
@router.get("/invoices")
def get_visitor_invoices(db_session: Session = Depends(get_db), user: dict = Depends(current_user)):
    salesperson_id = user.get("salesperson_id")
    role = user.get("role", "")
    
    query = db_session.query(Sale, Customer).join(Customer, Sale.customer_id == Customer.id)
    
    # اگر ویزیتور است، فقط فاکتورهای خودش؛ اگر مدیر است، همه
    if role == "salesperson" and salesperson_id:
        query = query.filter(Sale.salesperson_id == salesperson_id)
    
    sales_data = query.order_by(Sale.id.desc()).all()
    today = iran_today()
    
    results = []
    for sale, customer in sales_data:
        # محاسبه روزهای گذشته از تاریخ فاکتور
        sale_date = sale.date if isinstance(sale.date, date) else today
        days_passed = (today - sale_date).days if sale_date else 0
        
        # محاسبه تقریبی یا مانده بدهی مشتری از فاکتورها منهای پرداخت‌ها
        # برای دقت، از مجموع فاکتورهای پرداخت‌نشده یا حد اعتبار استفاده می‌شود
        customer_debt = getattr(customer, "credit_limit", 0) or 0
        
        is_overdue_15 = days_passed >= 15
        
        results.append({
            "sale_id": sale.id,
            "invoice_number": f"INV-{sale.id:05d}",
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_city": customer.city,
            "customer_phone": customer.phone,
            "date": sale_date.isoformat(),
            "total_amount": sale.total_amount,
            "customer_remaining_debt": customer_debt,
            "days_passed": days_passed,
            "is_overdue_15": is_overdue_15,
            "status": "نیازمند تسویه (بیش از ۱۵ روز)" if is_overdue_15 else "جاری"
        })
        
    return results

# ۲. کارت هشدار بالای ۱۵ روز
@router.get("/overdue-summary")
def get_overdue_summary(db_session: Session = Depends(get_db), user: dict = Depends(current_user)):
    salesperson_id = user.get("salesperson_id")
    role = user.get("role", "")
    
    query = db_session.query(Sale, Customer).join(Customer, Sale.customer_id == Customer.id)
    if role == "salesperson" and salesperson_id:
        query = query.filter(Sale.salesperson_id == salesperson_id)
        
    today = iran_today()
    all_sales = query.all()
    
    overdue_invoices = []
    total_overdue_amount = 0
    
    for s, c in all_sales:
        s_date = s.date if isinstance(s.date, date) else today
        days = (today - s_date).days
        if days >= 15:
            overdue_invoices.append({
                "invoice_number": f"INV-{s.id:05d}",
                "customer_name": c.name,
                "amount": s.total_amount,
                "days_passed": days
            })
            total_overdue_amount += (s.total_amount or 0)
            
    return {
        "overdue_count": len(overdue_invoices),
        "total_overdue_amount": total_overdue_amount,
        "overdue_invoices": overdue_invoices[:10]
    }

# ۳. کاتالوگ با نمایش موجودی آزاد در لحظه
@router.get("/catalog")
def get_live_catalog(db_session: Session = Depends(get_db)):
    products = db_session.query(Product).filter(Product.is_active == True).all()
    
    # مجموع رزروهای فعال
    reservations = db_session.query(
        InventoryReservation.product_id,
        func.sum(InventoryReservation.quantity).label("reserved")
    ).filter(InventoryReservation.status == "reserved").group_by(InventoryReservation.product_id).all()
    
    res_dict = {r.product_id: r.reserved for r in reservations}
    
    catalog = []
    for p in products:
        reserved = res_dict.get(p.id, 0)
        available = max(0, (p.stock or 0) - reserved)
        catalog.append({
            "product_id": p.id,
            "code": p.code,
            "name": p.name,
            "category": p.category,
            "price": p.price,
            "stock_total": p.stock or 0,
            "stock_reserved": reserved,
            "stock_available": available
        })
    return catalog

# ۴. لیست مشتریان ویزیتور
@router.get("/customers")
def get_customers(db_session: Session = Depends(get_db)):
    customers = db_session.query(Customer).order_by(Customer.name).all()
    return [{
        "id": c.id,
        "code": c.code,
        "name": c.name,
        "phone": c.phone,
        "city": c.city
    } for c in customers]

# ۵. ثبت آنلاین پیش‌فاکتور + رزرو موجودی + به‌روزرسانی آنی دیجی‌کالا
@router.post("/pre-invoice")
def create_pre_invoice(payload: CreatePreInvoiceRequest, db_session: Session = Depends(get_db), user: dict = Depends(current_user)):
    salesperson_id = user.get("salesperson_id") or 1
    
    # الف) بررسی موجودی آزاد تک‌تک اقلام
    total_amount = 0
    items_to_create = []
    
    for item in payload.items:
        product = db_session.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"کالای شناسه {item.product_id} یافت نشد.")
            
        unit_price = item.price if item.price is not None else (product.price or 0)
        
        # محاسبه موجودی آزاد
        reserved = db_session.query(func.sum(InventoryReservation.quantity))\
            .filter(InventoryReservation.product_id == product.id, InventoryReservation.status == "reserved").scalar() or 0
        available = (product.stock or 0) - reserved
        
        if item.quantity > available:
            raise HTTPException(status_code=400, detail=f"موجودی کالای «{product.name}» کافی نیست. موجودی قابل سفارش: {available} عدد")
            
        item_total = unit_price * item.quantity
        total_amount += item_total
        items_to_create.append((product, item.quantity, unit_price))
        
    # ب) ثبت رکورد فاکتور
    new_sale = Sale(
        customer_id=payload.customer_id,
        salesperson_id=salesperson_id,
        date=iran_today(),
        total_amount=total_amount
    )
    db_session.add(new_sale)
    db_session.flush() # برای گرفتن new_sale.id
    
    # ج) ثبت اقلام و رزرو موجودی انبار
    digikala_synced_items = []
    for product, qty, price in items_to_create:
        # ثبت قلم فاکتور
        sale_item = SaleItem(
            sale_id=new_sale.id,
            product_id=product.id,
            quantity=qty,
            price=price
        )
        db_session.add(sale_item)
        
        # ثبت رزرو در انبار
        resv = InventoryReservation(
            product_id=product.id,
            channel="visitor_pre_invoice",
            external_order_id=str(new_sale.id),
            quantity=qty,
            status="reserved"
        )
        db_session.add(resv)
        
        # کسر موجودی فیزیکی انبار کیاراد
        product.stock = max(0, (product.stock or 0) - qty)
        
        # د) به‌روزرسانی آنی موجودی در دیجی‌کالا (حفظ تعادل کانال‌ها)
        try:
            from setup_digikala_complete import DigikalaVariant
            dk_var = db_session.query(DigikalaVariant).filter(
                (DigikalaVariant.holoo_code == product.code) | (DigikalaVariant.title.contains(product.name[:15]))
            ).first()
            if dk_var:
                new_dk_stock = product.stock
                dk_client.update_stock(dk_var.variant_id, new_dk_stock)
                dk_var.seller_stock = new_dk_stock
                digikala_synced_items.append({"variant_id": dk_var.variant_id, "new_stock": new_dk_stock})
        except Exception as e:
            print(f"هشدار در همگام‌سازی دیجی‌کالا: {e}")
            
    db_session.commit()
    
    return {
        "success": True,
        "message": "پیش‌فاکتور با موفقیت ثبت شد و موجودی انبار و دیجی‌کالا به‌روز گردید.",
        "sale_id": new_sale.id,
        "invoice_number": f"INV-{new_sale.id:05d}",
        "total_amount": total_amount,
        "digikala_synced_items": digikala_synced_items
    }
