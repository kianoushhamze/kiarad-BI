import os
import tempfile
import base64
from typing import Any
from fastapi import Request, HTTPException
import base64
import os
import re
import tempfile
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from db import engine

router = APIRouter(prefix="/operations", tags=["voice_reports"])
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# لود مدل faster-whisper در بک‌اند
whisper_model = None
_whisper_tried = False

def get_whisper():
    """Lazy-load whisper: only on first real audio request."""
    global whisper_model, _whisper_tried
    if whisper_model is None and not _whisper_tried:
        _whisper_tried = True
        try:
            from faster_whisper import WhisperModel
            whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            print("OK: faster-whisper loaded lazily on first audio request.")
        except Exception as err:
            print(f"whisper load failed: {err}")
    return whisper_model


class AudioInput(BaseModel):
    audio_base64: str

class AdvancedReportInput(BaseModel):
    salesperson_id: Optional[int] = 1
    customer_name: Optional[str] = "نامشخص"
    visits_count: int = 1
    orders_count: int = 0
    reported_sales_amount: float = 0
    reported_collections_amount: float = 0
    followup_task: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None

def parse_report_nlp(text_input: str) -> dict:
    t = text_input.translate(PERSIAN_DIGITS)

    # شناسایی نام مشتری
    cust_match = re.search(r'(?:داروخانه|کلینیک|دکتر|گالری)\s+([^\s,،]+(?:\s+[^\s,،]+)?)', t)
    cust_name = cust_match.group(0) if cust_match else "مشتری حضوری"

    # شناسایی تسک پیگیری و تعهدات
    followup_task = None
    if "کاتالوگ" in t:
        followup_task = f"ارسال کاتالوگ محصولات به {cust_name} و پیگیری ویزیت مجدد"
    elif "سفارش" in t and "فروش" not in t:
        followup_task = f"پیگیری ارسال سفارش اعلام‌شده توسط {cust_name}"
    elif "چک" in t:
        followup_task = f"پیگیری تسویه و وضعیت چک {cust_name}"

    # استخراج مبالغ فروش و وصولی
    sales = 0.0
    s_match = re.search(r'(?:فروش|سفارش|مجموع|جمعا)\s*(?:حدود)?\s*(\d+(?:\.\d+)?)\s*میلیون', t)
    if s_match:
        sales = float(s_match.group(1)) * 10_000_000

    collections = 0.0
    c_match = re.search(r'(?:وصول|دریافت|تسویه|نقد)\s*(?:حدود)?\s*(\d+(?:\.\d+)?)\s*میلیون', t)
    if c_match:
        collections = float(c_match.group(1)) * 10_000_000

    orders = 1 if sales > 0 else 0
    has_check = "چک" in t
    action_type = "تحویل/دریافت چک" if has_check else ("ثبت سفارش" if sales > 0 else "ویزیت و پرزنت محصولات")

    summary = f"ویزیت {cust_name} انجام شد ({action_type})."
    if followup_task:
        summary += f" اقدام بعدی: {followup_task}."

    return {
        "raw_text": text_input,
        "customer_name": cust_name,
        "visits_count": 1,
        "orders_count": orders,
        "reported_sales_amount": sales,
        "reported_collections_amount": collections,
        "followup_task": followup_task,
        "summary": summary,
        "notes": text_input
    }

@router.post("/transcribe-audio")
@router.post("/operations/transcribe-audio")
async def transcribe_audio_endpoint(request: Request):
    try:
        content_type = request.headers.get("content-type", "")
        audio_bytes = b""
        if "application/json" in content_type:
            body = await request.json()
            b64 = body.get("audio_base64") or body.get("audio") or body.get("file") or ""
            if isinstance(b64, list):
                b64 = b64 if len(b64) > 1 else b64[0]
            if isinstance(b64, str) and "," in b64:
                b64 = b64.split(",", 1)
            audio_bytes = base64.b64decode(b64)
        else:
            form = await request.form()
            for key, val in form.items():
                if hasattr(val, "read"):
                    audio_bytes = await val.read()
                    break
                elif isinstance(val, str) and len(val) > 50:
                    try:
                        s = val.split(",", 1) if "," in val else val
                        audio_bytes = base64.b64decode(s)
                        break
                    except Exception:
                        pass
            if not audio_bytes:
                audio_bytes = await request.body()

        if not audio_bytes:
            raise HTTPException(status_code=400, detail="فایل صوتی یافت نشد")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            segments, info = get_whisper().transcribe(
                tmp_path,
                language="fa",
                vad_filter=False,
                beam_size=5
            )
            text = " ".join([seg.text.strip() for seg in segments]).strip()
            print(f"✓ متن استخراج‌شده از ویس: {text}")
            return {
                "transcribed_text": text,
                "text": text,
                "action_summary": text,
                "summary": text,
                "customer_name": "شناسایی از ویس",
                "customer": "شناسایی از ویس"
            }
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except HTTPException:
        raise
    except Exception as e:
        print(f"خطا در پردازش: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/submit-daily-report")
def submit_report(data: AdvancedReportInput):
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO daily_reports 
            (salesperson_id, report_date, visits_count, orders_count, 
             reported_sales_amount, reported_collections_amount, notes, tomorrow_plan, created_at)
            VALUES 
            (:sp_id, CURRENT_DATE, :visits, :orders, :sales, :collect, :notes, :plan, NOW())
            RETURNING id
        """), {
            "sp_id": data.salesperson_id or 1,
            "visits": data.visits_count,
            "orders": data.orders_count,
            "sales": data.reported_sales_amount,
            "collect": data.reported_collections_amount,
            "notes": data.summary or data.notes,
            "plan": data.followup_task or "پیگیری طبق برنامه"
        })
        rep_id = res.scalar()

        if data.followup_task:
            conn.execute(text("""
                INSERT INTO tasks (title, description, priority, status, progress, assigned_to, created_by, created_at, updated_at)
                VALUES (:title, :desc, 'high', 'new', 0, 1, 1, NOW(), NOW())
            """), {
                "title": data.followup_task,
                "desc": f"تسک ثبت‌شده خودکار از ویس گزارش شبانه: {data.notes}"
            })

        return {"status": "ok", "report_id": rep_id, "task_created": bool(data.followup_task)}
