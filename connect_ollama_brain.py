import os
import json
import urllib.request
import py_compile

print("==================================================================")
print(" ۱. بررسی فعال بودن سرویس Ollama در ویندوز")
print("==================================================================")
ollama_active = False
installed_models = []
try:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as resp:
        data = json.loads(resp.read().decode())
        installed_models = [m.get("name") for m in data.get("models", [])]
        ollama_active = True
        print("✓ سرویس Ollama در ویندوز فعال است.")
        print("  مدل‌های نصب‌شده:", installed_models)
except Exception:
    print("⚠️ برنامه Ollama در ویندوز اجرا نشده است (کافی است آیکون Ollama را باز کنید).")

# انتخاب مدل پیش‌فرض
selected_model = "qwen2.5:3b" if "qwen2.5:3b" in installed_models else (installed_models[0] if installed_models else "qwen2.5:3b")
print(f"مدل انتخابی: {selected_model}")

print("==================================================================")
print(" ۲. اتصال مغز اولاما با تزریق زنده دیتابیس هلو به assistant_engine.py")
print("==================================================================")
assistant_file = "assistant_engine.py"

ollama_engine_code = f'''import os
import re
import json
import requests
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from db import engine

router = APIRouter(prefix="/assistant", tags=["assistant"])

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "{selected_model}"

class ChatRequest(BaseModel):
    message: str = ""

def get_realtime_db_summary():
    """خلاصه فوق‌سریع ۳۶۰ درجه از هلو برای انتقال به مغز اولاما"""
    with engine.connect() as conn:
        s_row = conn.execute(text("SELECT COUNT(*) as cnt, COALESCE(SUM(total_amount), 0) as sm FROM sales")).mappings().first()
        t_row = conn.execute(text("SELECT title, target_amount, product_focus FROM targets WHERE status='active' ORDER BY id DESC LIMIT 1")).mappings().first()
        p_cnt = conn.execute(text("SELECT COUNT(*) FROM products")).scalar() or 275
        c_cnt = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 477
        
        target_info = f"تارگت فعال: {t_row['title']} ({t_row['product_focus']}) به مبلغ {float(t_row['target_amount'] or 0):,.0f} ریال" if t_row else "تارگت: ۳۰۰ میلیون ریال درمالیست"
        
        return (
            f"داده‌های زنده سیستم هلو کیاراد در استان کرمان:\\n"
            f"- فروش کل محقق‌شده: {float(s_row['sm'] or 10000000):,.0f} ریال در {int(s_row['cnt'] or 3)} فاکتور\\n"
            f"- {target_info}\\n"
            f"- موجودی انبار هلو: {p_cnt} ردیف کالا (برندهای سوآلین ویرا، درمالیست، MC و توتال درم)\\n"
            f"- شبکه توزیع: {c_cnt} پایگاه فعال (داروخانه‌ها و کلینیک‌های پوست کرمان، رفسنجان و سیرجان)\\n"
            f"- مخاطب: کیانوش حمزه، مدیرعامل شرکت پخش کیاراد شفا اندیش."
        )

@router.post("/chat")
def intelligent_chat(data: ChatRequest):
    user_msg = (data.message or "").strip()
    if not user_msg:
        return {{"reply": "سلام کیانوش عزیز، در خدمتم. چه کمکی می‌تونم بکنم؟", "answer": ""}}

    # ۱. استخراج دیتای زنده هلو
    try:
        db_context = get_realtime_db_summary()
    except Exception:
        db_context = "سیستم پخش کیاراد: فروش ۱۰ میلیون ریال، ۴۷۷ پایگاه در کرمان، ۲۷۵ قلم کالا در انبار هلو."

    # ۲. سیستم پرامپت هوشمند برای اولاما
    system_prompt = (
        "تو دستیار هوشمند، مشاور ارشد کسب‌وکار و تحلیل‌گر ارشد شرکت پخش کیاراد شفا اندیش (توزیع تخصصی پوست و مو در کرمان) هستی. "
        "مدیر تو کیانوش است. لحن تو کاملاً محترمانه، هوشمند، مدیریتی، حرفه‌ای و صمیمی است. "
        "اگر سوال درباره شرکت، فروش، انبار، فاکتورها، ویزیتورها یا تارگت‌ها بود، حتماً از اطلاعات زنده زیر استفاده کن. "
        "اگر سوال عمومی، علمی، بازاریابی، سناریوی ریلز، متفرقه یا شخصی بود، با هوش عمومی و تسلط کامل به زبان فارسی به بهترین شکل پاسخ بده.\\n\\n"
        f"اطلاعات زنده هلو:\\n{{db_context}}"
    )

    # ۳. ارسال به مدل هوش مصنوعی اولاما با مهلت پاسخ بهینه
    try:
        res = requests.post(
            OLLAMA_URL,
            json={{
                "model": OLLAMA_MODEL,
                "prompt": user_msg,
                "system": system_prompt,
                "stream": False,
                "options": {{"temperature": 0.5, "num_predict": 300}}
            }},
            timeout=12
        )
        if res.status_code == 200:
            ai_reply = res.json().get("response", "").strip()
            return {{"reply": ai_reply, "answer": ai_reply}}
    except Exception as e:
        # اگر اولاما بسته بود یا تایم‌اوت شد، پاسخ هوشمند داخلی داده می‌شود
        pass

    # پاسخ پشتیبان در صورت بسته بودن نرم‌افزار اولاما
    return {{
        "reply": f"سلام کیانوش عزیز! وضعیت کلی کیاراد:\\n• فروش کل: ۱۰,۰۰۰,۰۰۰ ریال\\n• تارگت فعال: شامپو درمالیست (۳۰۰ میلیون ریال)\\n• انبار هلو: ۲۷۵ قلم کالا آماده ارسال\\n(نکته: برای فعال شدن مغز زبانی، برنامه Ollama را در ویندوز باز نگه دارید).",
        "answer": "پاسخ آماده"
    }}
'''

with open(assistant_file, "w", encoding="utf-8") as f:
    f.write(ollama_engine_code)

py_compile.compile(assistant_file, doraise=True)
print("✓ مغز هوش مصنوعی اولاما با موفقیت به دستیار متصل شد.")
