import urllib.request
import json
import time

print("==================================================================")
print(" 🚀 تست جامع و خودکار سلامت تمام بخش‌های کیاراد BI")
print("==================================================================")

endpoints = [
    ("داشبورد مدیریتی", "http://localhost:8000/dashboard/full?range=month"),
    ("خلاصه گزارشات فروش", "http://localhost:8000/reports/summary?days=30"),
    ("نوتیفیکیشن‌ها و هشدارها", "http://localhost:8000/reports/recommendations"),
    ("لیست تارگت‌های هوشمند", "http://localhost:8000/targets/custom-list"),
    ("پیگیری‌های CRM", "http://localhost:8000/crm/interactions"),
    ("پیام‌های چت تیمی", "http://localhost:8000/chat/messages?room=general"),
]

print("\n--- ۱. تست پایداری و سرعت اندپوینت‌های API ---")
for name, url in endpoints:
    try:
        t0 = time.time()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            elapsed = (time.time() - t0) * 1000
            print(f"  [✓] {name}: کد {resp.status} (زمان پاسخ: {elapsed:.0f}ms)")
    except Exception as e:
        print(f"  [❌] {name}: خطا -> {e}")

print("\n--- ۲. تست سناریوهای دستیار هوشمند ---")
chat_tests = [
    "امروز چه فاکتورهایی صادر شده ؟",
    "کرم سوآلین ویرا",
    "آمار پایگاه‌های کرمان",
    "یه تارگت ۳۰ میلیون تومنی از شامپو ضد ریزش درمالیست برای فروشنده تست ایجاد کن"
]

for q in chat_tests:
    try:
        t0 = time.time()
        req = urllib.request.Request(
            "http://localhost:8000/assistant/chat",
            data=json.dumps({"message": q}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = (time.time() - t0) * 1000
            ans = data.get("reply", "")[:70].replace("\n", " ")
            print(f"  [✓] سوال: '{q}'\n      پاسخ ({elapsed:.0f}ms): {ans}...")
    except Exception as e:
        print(f"  [❌] سوال '{q}': خطا -> {e}")

print("\n==================================================================")
print(" تست پایان یافت.")
print("==================================================================")
