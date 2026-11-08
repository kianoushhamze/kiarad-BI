import os
import requests
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from db import engine
from operations import current_user, require_manager
from iran_time import iran_today

router = APIRouter(prefix="/kerman", tags=["kerman_crm_and_planning"])
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

def call_llm(prompt: str, system: str = "") -> str:
    try:
        res = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.4}
        }, timeout=45)
        if res.status_code == 200:
            return res.json().get("response", "").strip()
        return "مدل هوش مصنوعی در دسترس نیست."
    except Exception as e:
        return f"خطا در مدل محلی: {str(e)}"

class CustomerBatchImport(BaseModel):
    name: str
    customer_type: str = Field(description="pharmacy, doctor, cosmetics_shop")
    city: str = "کرمان"
    phone: Optional[str] = None
    address: Optional[str] = None
    medical_system_code: Optional[str] = None
    guild_license_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ContentIdeaRequest(BaseModel):
    product_name: str
    focus_benefit: Optional[str] = "ترمیم‌کننده، ضد لک، آبرسان"
    target_audience: Optional[str] = "عموم بانوان یا مراجعین کلینیک‌ها"

@router.post("/customers/add")
def add_kerman_customer(data: CustomerBatchImport, _: dict = Depends(require_manager)):
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO customers (name, customer_type, city, phone, credit_limit, medical_system_code, guild_license_code, latitude, longitude, created_at)
            VALUES (:name, :ctype, :city, :phone, 0, :mcode, :gcode, :lat, :lon, NOW())
            RETURNING id, name, customer_type, city
        """), {
            "name": data.name,
            "ctype": data.customer_type,
            "city": data.city,
            "phone": data.phone,
            "mcode": data.medical_system_code,
            "gcode": data.guild_license_code,
            "lat": data.latitude,
            "lon": data.longitude
        }).mappings().first()
        return {"status": "success", "customer": dict(row)}

@router.get("/customers/by-type")
def get_customers_by_type(customer_type: str = Query(..., description="pharmacy, doctor, cosmetics_shop"), city: Optional[str] = None, _: dict = Depends(current_user)):
    clause = "WHERE customer_type = :ctype"
    params = {"ctype": customer_type}
    if city:
        clause += " AND city = :city"
        params["city"] = city
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, name, city, phone, customer_type, latitude, longitude FROM customers {clause} ORDER BY name LIMIT 150"), params).mappings().all()
        return [dict(r) for r in rows]

@router.get("/action-plan/monthly")
def get_monthly_action_plan(salesperson_id: Optional[int] = None, user: dict = Depends(current_user)):
    if user.get("role") not in {"ceo", "sales_manager"}:
        salesperson_id = user.get("salesperson_id")
        if not salesperson_id:
            raise HTTPException(status_code=403, detail="برای این حساب، ویزیتور متصل نشده است.")
    with engine.connect() as conn:
        cities = conn.execute(text("SELECT DISTINCT city FROM customers WHERE city IS NOT NULL")).scalars().all()
        if user.get("role") in {"ceo", "sales_manager"}:
            sp = conn.execute(text("SELECT id, name FROM salespersons ORDER BY name")).mappings().all()
        else:
            sp = conn.execute(text("SELECT id, name FROM salespersons WHERE id=:id"), {"id": salesperson_id}).mappings().all()
        
        prompt = f"شهرهای تحت پوشش شرکت کیاراد در استان کرمان: {list(cities)}.\nتیم ویزیتورها: {[dict(s) for s in sp]}.\nیک اکشن‌پلان ۴ هفته‌ای برای پوشش داروخانه‌ها، پزشکان زیبایی و فروشگاه‌های آرایشی استان بنویس."
        system = "تو مدیر ارشد برنامه‌ریزی و سرپرست فروش شرکت پخش کیاراد در استان کرمان هستی. برنامه‌ای دقیق و واقع‌بینانه به تفکیک هفته و مناطق استان ارائه کن."
        plan = call_llm(prompt, system)
        return {"action_plan": plan}

@router.get("/weekly-meeting-summary")
def generate_weekly_meeting_summary(_: dict = Depends(require_manager)):
    week_ago = iran_today() - timedelta(days=7)
    with engine.connect() as conn:
        reports = conn.execute(text("""
            SELECT s.name as salesperson_name, dr.report_date, dr.visits_count, dr.orders_count, 
                   dr.reported_sales_amount, dr.loss_reasons, dr.issues, dr.notes
            FROM daily_reports dr
            JOIN salespersons s ON s.id = dr.salesperson_id
            WHERE dr.report_date >= :start_date
            ORDER BY dr.report_date DESC
        """), {"start_date": week_ago}).mappings().all()
        
        if not reports:
            return {"summary": "در ۷ روز گذشته گزارشی ثبت نشده است.", "coaching_points": []}
            
        reports_text = "\n".join([f"- ویزیتور {r['salesperson_name']} (تاریخ {r['report_date']}): ویزیت={r['visits_count']}، سفارش={r['orders_count']}، موانع و دلایل رد={r['loss_reasons']}، مشکلات={r['issues']}" for r in reports])
        
        prompt = f"گزارش‌های شبانه ویزیتورهای کیاراد در هفته اخیر:\n{reports_text}\n\nلطفاً نقاط ضعف، علل رد سفارش توسط داروخانه‌ها/پزشکان و نکات کلیدی آموزشی را برای جلسه هفتگی مدیرعامل آماده کن."
        system = "تو مربی ارشد فروش دارویی و آرایشی هستی. نکات کاربردی، روان و انگیزشی برای اصلاح تکنیک‌های فروش ویزیتورها استخراج کن."
        analysis = call_llm(prompt, system)
        return {"meeting_agenda": analysis, "raw_reports_count": len(reports)}

@router.post("/instagram-ideas")
def generate_instagram_content(data: ContentIdeaRequest, _: dict = Depends(current_user)):
    prompt = f"محصول: {data.product_name}\nمزیت اصلی: {data.focus_benefit}\nمخاطب: {data.target_audience}\nیک سناریوی ریلز جذاب اینستاگرام شامل قلاب اول ۳ ثانیه، بدنه آموزش/معرفی و دعوت به اقدام (CTA) برای پیج بنویس."
    system = "تو سناریونویس ارشد محتوای شبکه‌های اجتماعی حوزه مراقبت پوست، مو و درماتولوژی هستی."
    script = call_llm(prompt, system)
    return {"product": data.product_name, "script": script}
