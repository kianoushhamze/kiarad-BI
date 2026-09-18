import os
import sys
import time
import subprocess
from datetime import datetime

# زمان‌بندی: ۳۶۰۰ ثانیه = ۱ ساعت کامل
INTERVAL = 3600

PYTHON = sys.executable
BASE_DIR = r"D:\project\kiaradbi"
HOLOO_SCRIPT = os.path.join(BASE_DIR, "holoo_sync.py")
DIGIKALA_SCRIPT = os.path.join(BASE_DIR, "setup_digikala_complete.py")

print("==================================================")
print("  سرویس همگام‌سازی خودکار کیاراد (هلو + دیجی‌کالا)")
print(f"  زمان‌بندی: هر ۶۰ دقیقه یک‌بار (INTERVAL = {INTERVAL}s)")
print("==================================================")

while True:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_str}] شروع همگام‌سازی خودکار دوره‌ای...")

    # ۱. همگام‌سازی هلو
    try:
        print("-> در حال دریافت داده‌های جدید از حسابداری هلو...")
        res_h = subprocess.run([PYTHON, HOLOO_SCRIPT], capture_output=True, text=True, timeout=180)
        if res_h.returncode == 0:
            print(" [هلو] همگام‌سازی فاکتورها و مطالبات با موفقیت انجام شد.")
        else:
            print(" [هلو] هشدار در همگام‌سازی:")
            print((res_h.stderr or res_h.stdout)[:200])
    except Exception as e:
        print(f"خطا در اجرای همگام‌سازی هلو: {e}")

    # ۲. همگام‌سازی دیجی‌کالا
    try:
        print("-> در حال بررسی و همگام‌سازی سفارش‌ها و کالاهای دیجی‌کالا...")
        res_dk = subprocess.run([PYTHON, DIGIKALA_SCRIPT], capture_output=True, text=True, timeout=90)
        if res_dk.returncode == 0:
            print(" [دیجی‌کالا] وضعیت سفارش‌ها و موجودی کالاها با موفقیت به‌روز شد.")
        else:
            print(" [دیجی‌کالا] هشدار در همگام‌سازی دیجی‌کالا.")
    except Exception as e:
        print(f"خطا در اجرای همگام‌سازی دیجی‌کالا: {e}")

    next_time = datetime.fromtimestamp(time.time() + INTERVAL).strftime("%H:%M:%S")
    print(f"\n دوره همگام‌سازی تکمیل شد. همگام‌سازی بعدی رأس ساعت {next_time} (۱ ساعت دیگر)...")
    time.sleep(INTERVAL)
