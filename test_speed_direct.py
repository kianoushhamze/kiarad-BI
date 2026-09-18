import urllib.request
import json
import time

print("==================================================================")
print(" 🚀 تست پرسرعت با آی‌پی مستقیم 127.0.0.1 (بدون تاخیر ویندوز)")
print("==================================================================")

endpoints = [
    ("داشبورد مدیریتی", "http://127.0.0.1:8000/dashboard/full?range=month"),
    ("خلاصه گزارشات فروش", "http://127.0.0.1:8000/reports/summary?days=30"),
    ("نوتیفیکیشن‌ها و هشدارها", "http://127.0.0.1:8000/reports/recommendations"),
    ("لیست تارگت‌های هوشمند", "http://127.0.0.1:8000/targets/custom-list"),
    ("پیگیری‌های CRM", "http://127.0.0.1:8000/crm/interactions"),
    ("پیام‌های چت تیمی", "http://127.0.0.1:8000/chat/messages?room=general"),
]

for name, url in endpoints:
    try:
        t0 = time.time()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            elapsed = (time.time() - t0) * 1000
            print(f"  [✓] {name}: کد {resp.status} (زمان: {elapsed:.0f}ms)")
    except Exception as e:
        print(f"  [❌] {name}: خطا -> {e}")

print("\n--- تست استعلام دستیار با 127.0.0.1 ---")
try:
    t0 = time.time()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/assistant/chat",
        data=json.dumps({"message": "آمار پایگاه‌های کرمان"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        elapsed = (time.time() - t0) * 1000
        print(f"  [✓] پاسخ دستیار ({elapsed:.0f}ms):\n      {data.get('reply')}")
except Exception as e:
    print(f"  [❌] خطا: {e}")

print("==================================================================")
