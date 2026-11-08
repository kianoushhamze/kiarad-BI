import base64
import os
import re
import tempfile
import hashlib
import json
import threading
from pathlib import Path
from importlib.util import find_spec
from uuid import UUID, uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from db import engine
from operations import MANAGER_ROLES, current_user, role_has_module_permission

router = APIRouter(prefix="/operations", tags=["voice_reports"])
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# لود مدل faster-whisper در بک‌اند
whisper_model = None
_whisper_tried = False
_whisper_lock = threading.Lock()
_speech_conversion_verified = False
_loaded_speech_model_source = None
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _speech_model_verification(folder):
    try:
        result = json.loads((Path(folder) / "verification.json").read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _speech_model_rejected(folder):
    return _speech_model_verification(folder).get("exclude_from_auto_selection") is True


def speech_model_source():
    """An offline model directory may be supplied without changing application code."""
    configured = os.getenv("KIARAD_SPEECH_MODEL_PATH", "").strip()
    if configured:
        return configured
    root = Path(__file__).resolve().parent / "data" / "speech-models"
    try:
        active = json.loads((root / "active-model.json").read_text(encoding="utf-8"))
        relative = active.get("directory")
        if isinstance(relative, str) and relative and not Path(relative).is_absolute():
            folder = (root / relative).resolve()
            folder.relative_to(root.resolve())
            if folder != root.resolve() and all((folder / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
                return str(folder)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    for size in ("small", "base", "tiny"):
        folder = (root / ("faster-whisper-" + size)).resolve()
        try:
            folder.relative_to(root.resolve())
        except ValueError:
            continue
        if not _speech_model_rejected(folder) and all((folder / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
            return str(folder)
    return "small"


def speech_readiness():
    installed = find_spec("faster_whisper") is not None
    source = _loaded_speech_model_source if whisper_model is not None and _loaded_speech_model_source else speech_model_source()
    if os.getenv("KIARAD_SPEECH_MODEL_PATH", "").strip() or Path(source).is_dir():
        folder = Path(source)
        files_present = folder.is_dir() and all((folder / name).is_file() for name in
                                                ("model.bin", "config.json", "tokenizer.json"))
        state = "local_files_present" if installed and files_present else "local_files_missing"
    else:
        state = "cache_not_verified"
    if not installed:
        state = "dependency_missing"
    if whisper_model is not None:
        state = "loaded"
    elif _whisper_tried:
        state = "load_failed"
    rejected = _speech_model_rejected(source)
    quality_warning = _speech_model_verification(source).get("public_sample_check_passed") is False
    if rejected and whisper_model is None:
        state = "quality_rejected"
    return {"state": state, "library_installed": installed, "manual_entry_available": True,
            "automatic_download": False, "restart_required_after_model_change": True,
            "conversion_verified": bool(_speech_conversion_verified and whisper_model is not None),
            "public_sample_quality_warning": quality_warning}


@router.get("/speech-readiness")
def speech_status(_: dict = Depends(current_user)):
    return speech_readiness()


def get_whisper():
    """Lazy-load whisper: only on first real audio request."""
    global whisper_model, _whisper_tried, _loaded_speech_model_source
    if whisper_model is None and not _whisper_tried:
        _whisper_tried = True
        try:
            from faster_whisper import WhisperModel
            source = speech_model_source()
            whisper_model = WhisperModel(source, device="cpu", compute_type="int8",
                                         cpu_threads=2, num_workers=1, local_files_only=True)
            _loaded_speech_model_source = source
            print("OK: faster-whisper loaded lazily on first audio request.")
        except Exception:
            print("Local speech model unavailable.")
    return whisper_model


class AudioInput(BaseModel):
    audio_base64: str

class AdvancedReportInput(BaseModel):
    submission_key: UUID = Field(default_factory=uuid4)
    salesperson_id: Optional[int] = Field(default=None, gt=0)
    assigned_user_id: Optional[int] = Field(default=None, gt=0)
    customer_id: Optional[int] = Field(default=None, gt=0)
    customer_name: Optional[str] = Field(default="نامشخص", max_length=300)
    visits_count: int = Field(default=0, ge=0, le=10000)
    orders_count: int = Field(default=0, ge=0, le=10000)
    reported_sales_amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    reported_collections_amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    followup_task: Optional[str] = Field(default=None, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=5000)
    notes: Optional[str] = Field(default=None, max_length=20000)
    raw_text: Optional[str] = Field(default=None, max_length=20000)


@router.on_event("startup")
def ensure_voice_report_schema():
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE daily_reports ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id)"))
        _ensure_voice_entries(conn)


def _ensure_voice_entries(conn, *, temporary=False):
    conn.execute(text(f"""CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS voice_report_entries (
        id SERIAL PRIMARY KEY, created_by INTEGER NOT NULL REFERENCES users(id),
        salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
        report_id INTEGER NOT NULL REFERENCES daily_reports(id),
        task_id INTEGER REFERENCES tasks(id),customer_id INTEGER REFERENCES customers(id),
        customer_name TEXT NOT NULL,raw_text TEXT NOT NULL,summary TEXT NOT NULL,
        visits_count INTEGER NOT NULL,orders_count INTEGER NOT NULL,
        reported_sales_amount NUMERIC NOT NULL,reported_collections_amount NUMERIC NOT NULL,
        submission_key UUID NOT NULL,payload_hash VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
        UNIQUE(created_by,submission_key)
    )"""))


@router.get("/voice-customers")
def voice_customers(_: dict = Depends(current_user)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, name, city FROM customers
            WHERE COALESCE(name, '') <> ''
            ORDER BY name LIMIT 1000
        """)).mappings().all()
    return {"items": [dict(row) for row in rows]}

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

    summary = text_input[:5000]

    return {
        "raw_text": text_input,
        "customer_name": cust_name,
        "visits_count": 0,
        "orders_count": 0,
        "reported_sales_amount": 0,
        "reported_collections_amount": 0,
        "followup_task": followup_task,
        "summary": summary,
        "notes": text_input
    }

async def _audio_body(request: Request) -> bytes:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 14 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="حجم درخواست صوتی بیش از حد مجاز است")
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = json.loads(raw)
            value = body.get("audio_base64") or body.get("audio") or ""
            if not isinstance(value, str):
                raise ValueError()
            if value.startswith("data:"):
                value = value.split(",", 1)[1]
            audio = base64.b64decode(re.sub(r"\s+", "", value), validate=True)
        except (ValueError, TypeError, AttributeError, IndexError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="دادهٔ صوتی معتبر نیست")
    elif "multipart/form-data" in content_type:
        async def receive():
            return {"type": "http.request", "body": bytes(raw), "more_body": False}
        parsed_request = Request(request.scope, receive)
        async with parsed_request.form(max_files=1, max_fields=2) as form:
            upload = form.get("file")
            if upload is None or not hasattr(upload, "read"):
                raise HTTPException(status_code=400, detail="فایل صوتی یافت نشد")
            audio = await upload.read(MAX_AUDIO_BYTES + 1)
    else:
        audio = bytes(raw)
    if not audio:
        raise HTTPException(status_code=400, detail="فایل صوتی یافت نشد")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="حداکثر حجم صوت ۱۰ مگابایت است")
    return audio


def _transcribe_bytes(audio: bytes) -> dict:
    global _speech_conversion_verified
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as tmp:
            tmp.write(audio)
            path = tmp.name
        with _whisper_lock:
            model = get_whisper()
            if model is None:
                raise HTTPException(status_code=503, detail="مدل محلی تبدیل گفتار آماده نیست؛ فعلاً گزارش را متنی وارد کنید")
            try:
                segments, _ = model.transcribe(path, language="fa", vad_filter=True, beam_size=5)
                transcript = " ".join(segment.text.strip() for segment in segments).strip()
            except Exception:
                raise HTTPException(status_code=400, detail="صوت قابل پردازش نیست؛ دوباره ضبط کنید یا متن را دستی وارد کنید")
        if not transcript:
            raise HTTPException(status_code=422, detail="گفتار قابل تشخیصی پیدا نشد؛ دوباره ضبط کنید")
        _speech_conversion_verified = True
        parsed = parse_report_nlp(transcript)
        return {**parsed, "transcribed_text": transcript, "text": transcript,
                "action_summary": parsed["summary"], "customer": parsed["customer_name"]}
    finally:
        if path and os.path.exists(path):
            os.remove(path)


@router.post("/transcribe-audio")
@router.post("/operations/transcribe-audio")
async def transcribe_audio_endpoint(request: Request, _: dict = Depends(current_user)):
    audio = await _audio_body(request)
    return await run_in_threadpool(_transcribe_bytes, audio)


@router.get("/voice-reports")
def voice_report_history(user: dict = Depends(current_user)):
    manager = user.get("role") in MANAGER_ROLES
    if not manager and not user.get("salesperson_id"):
        return {"items": []}
    where = "" if manager else " WHERE e.salesperson_id=:sp_id"
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT e.*,sp.name AS salesperson_name,u.full_name AS author_name
            FROM voice_report_entries e JOIN salespersons sp ON sp.id=e.salesperson_id
            JOIN users u ON u.id=e.created_by
        """ + where + " ORDER BY e.created_at DESC,e.id DESC LIMIT 100"),
            {} if manager else {"sp_id": user["salesperson_id"]}).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/submit-daily-report")
def submit_report(data: AdvancedReportInput, user: dict = Depends(current_user)):
    manager = user.get("role") in MANAGER_ROLES
    salesperson_id = data.salesperson_id if manager else user.get("salesperson_id")
    if not salesperson_id:
        raise HTTPException(status_code=403, detail="حساب پرسنل را انتخاب یا به پروفایل ویزیتور متصل کنید")
    raw_text = (data.raw_text or data.notes or "").strip()
    summary = (data.summary or "").strip()
    followup = (data.followup_task or "").strip()
    if not raw_text or not summary:
        raise HTTPException(status_code=422, detail="متن گزارش و خلاصه نباید خالی باشند")
    if followup and not role_has_module_permission(user["role"], "tasks", "can_write"):
        raise HTTPException(status_code=403, detail="مجوز ساخت کار پیگیری ندارید؛ متن پیگیری را حذف کنید یا با مدیر هماهنگ کنید")
    normalized = {**data.model_dump(exclude={"submission_key", "notes"}), "salesperson_id": salesperson_id,
                  "raw_text": raw_text, "summary": summary, "followup_task": followup,
                  "assigned_user_id":data.assigned_user_id if manager else user["id"]}
    digest = hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    with engine.begin() as conn:
        key = {"created_by": user["id"], "key": str(data.submission_key)}
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key,0))"),
                     {"lock_key": f"voice:{user['id']}:{data.submission_key}"})
        previous = conn.execute(text("""SELECT id,report_id,task_id,payload_hash FROM voice_report_entries
            WHERE created_by=:created_by AND submission_key=CAST(:key AS uuid)"""),key).mappings().first()
        if previous:
            if previous["payload_hash"] != digest:
                raise HTTPException(status_code=409, detail="این شناسه قبلاً برای گزارش متفاوت ثبت شده؛ گزارش تازه‌ای شروع کنید")
            return {"status":"ok","entry_id":previous["id"],"report_id":previous["report_id"],
                    "task_id":previous["task_id"],"task_created":previous["task_id"] is not None,"replayed":True}
        if not conn.execute(text("SELECT id FROM salespersons WHERE id=:id FOR UPDATE"),{"id":salesperson_id}).first():
            raise HTTPException(status_code=404, detail="پروفایل پرسنل پیدا نشد")
        customer_name = (data.customer_name or "").strip() or "نامشخص"
        if data.customer_id is not None:
            customer = conn.execute(text("SELECT id,name FROM customers WHERE id=:id"),{"id":data.customer_id}).mappings().first()
            if not customer:
                raise HTTPException(status_code=404, detail="مشتری انتخاب‌شده پیدا نشد")
            customer_name = customer["name"]
        today = conn.execute(text("SELECT (NOW() AT TIME ZONE 'Asia/Tehran')::date")).scalar()
        report = conn.execute(text("""SELECT id,customer_id FROM daily_reports
            WHERE salesperson_id=:sp_id AND report_date=:day ORDER BY id LIMIT 1 FOR UPDATE"""),
            {"sp_id":salesperson_id,"day":today}).mappings().first()
        notes = f"{customer_name}: {summary}"
        values = {"sp_id":salesperson_id,"customer_id":data.customer_id,"day":today,
                  "visits":data.visits_count,"orders":data.orders_count,"sales":data.reported_sales_amount,
                  "collect":data.reported_collections_amount,"notes":notes,"plan":followup or None}
        if report:
            report_id = report["id"]
            conn.execute(text("""UPDATE daily_reports SET
                visits_count=COALESCE(visits_count,0)+:visits,orders_count=COALESCE(orders_count,0)+:orders,
                reported_sales_amount=COALESCE(reported_sales_amount,0)+:sales,
                reported_collections_amount=COALESCE(reported_collections_amount,0)+:collect,
                notes=CONCAT_WS(E'\\n\\n',NULLIF(notes,''),:notes),
                tomorrow_plan=CONCAT_WS(E'\\n',NULLIF(tomorrow_plan,''),:plan),
                customer_id=CASE WHEN customer_id=:customer_id THEN customer_id ELSE NULL END
                WHERE id=:id"""),{**values,"id":report_id})
        else:
            report_id = conn.execute(text("""INSERT INTO daily_reports
                (salesperson_id,customer_id,report_date,visits_count,new_customers_count,orders_count,lost_orders_count,
                 reported_sales_amount,reported_collections_amount,notes,tomorrow_plan,created_at)
                VALUES (:sp_id,:customer_id,:day,:visits,0,:orders,0,:sales,:collect,:notes,:plan,
                        NOW() AT TIME ZONE 'Asia/Tehran') RETURNING id"""),values).scalar()
        task_id = None
        if followup:
            assigned_to = user["id"]
            if manager:
                assigned_to = conn.execute(text("""SELECT id FROM users WHERE id=:target_id AND salesperson_id=:sp_id
                    AND is_active::text IN ('1','true','t') AND role IN ('salesperson','visitor')
                    ORDER BY id LIMIT 1"""),{"sp_id":salesperson_id,"target_id":data.assigned_user_id}).scalar()
                if not assigned_to:
                    raise HTTPException(status_code=409, detail="حساب فعال پرسنل برای تخصیص پیگیری پیدا نشد")
            task_id = conn.execute(text("""INSERT INTO tasks
                (title,description,priority,status,progress,assigned_to,created_by,customer_id,created_at,updated_at)
                VALUES (:title,:description,'high','new',0,:assigned_to,:created_by,:customer_id,NOW(),NOW())
                RETURNING id"""),{"title":followup,"description":f"پیگیری گزارش روزانهٔ {report_id}: {raw_text[:1000]}",
                                "assigned_to":assigned_to,"created_by":user["id"],"customer_id":data.customer_id}).scalar()
            conn.execute(text("""INSERT INTO task_updates (task_id,user_id,progress,status,note,created_at)
                VALUES (:task_id,:user_id,0,'new','ایجاد از گزارش کار',NOW())"""),{"task_id":task_id,"user_id":user["id"]})
        entry_id = conn.execute(text("""INSERT INTO voice_report_entries
            (created_by,salesperson_id,report_id,task_id,customer_id,customer_name,raw_text,summary,
             visits_count,orders_count,reported_sales_amount,reported_collections_amount,submission_key,payload_hash)
            VALUES (:created_by,:sp_id,:report_id,:task_id,:customer_id,:customer_name,:raw_text,:summary,
                    :visits,:orders,:sales,:collect,CAST(:key AS uuid),:digest) RETURNING id"""),
            {**values,**key,"report_id":report_id,"task_id":task_id,"customer_name":customer_name,
             "raw_text":raw_text,"summary":summary,"digest":digest}).scalar()
    return {"status":"ok","entry_id":entry_id,"report_id":report_id,"task_id":task_id,
            "task_created":task_id is not None,"replayed":False}
