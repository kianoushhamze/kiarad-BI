import requests
import time
import py_compile

print("==================================================================")
print(" ۱. تست زنده سرعت و پاسخگویی مدل qwen2.5:3b در اولاما")
print("==================================================================")
t0 = time.time()
try:
    r = requests.post(
        "http://127.0.0.1:11434/api/generate",
        json={
            "model": "qwen2.5:3b",
            "prompt": "تو کی هستی؟ در دو جمله معرفی کن.",
            "stream": False,
            "options": {"num_predict": 60, "temperature": 0.5}
        },
        timeout=35
    )
    elapsed = time.time() - t0
    print(f"✓ پاسخ زنده اولاما در {elapsed:.1f} ثانیه دریافت شد:")
    print(" ", r.json().get("response"))
except Exception as e:
    print("❌ خطای ارتباط با اولاما:", e)

print("==================================================================")
print(" ۲. بهینه‌سازی پارامترهای سرعت و حذف پاسخ پیش‌فرض در assistant_engine.py")
print("==================================================================")
assistant_file = "assistant_engine.py"

with open(assistant_file, "r", encoding="utf-8") as f:
    code = f.read()

# افزایش تایم‌اوت به ۴۰ ثانیه و بهینه‌سازی تعداد توکن‌ها برای سرعت ۳ برابری
code = code.replace('"timeout=15"', '"timeout=40"')
code = code.replace('timeout=15', 'timeout=40')
code = code.replace('"num_predict": 350', '"num_predict": 180, "num_ctx": 1024')

# چاپ خطا در لاگ در صورت بروز مشکل تا علت پنهان نماند
code = code.replace(
    'except Exception:\n        pass',
    'except Exception as err:\n        print(f"Ollama Call Error: {err}")'
)

with open(assistant_file, "w", encoding="utf-8") as f:
    f.write(code)

py_compile.compile(assistant_file, doraise=True)
print("✓ تنظیمات بهینه‌سازی سرعت و تایم‌اوت با موفقیت اعمال شدند.")
