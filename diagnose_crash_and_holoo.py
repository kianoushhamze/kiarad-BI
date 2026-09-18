import os
import glob
import traceback

print("==================================================================")
print(" ۱. بررسی نحوه اتصال به هلو در فایل db.py و تنظیمات محیطی")
print("==================================================================")
if os.path.exists("db.py"):
    with open("db.py", "r", encoding="utf-8") as f:
        print("محتوای db.py:")
        print(f.read()[:500])

print("\n==================================================================")
print(" ۲. یافتن فایل‌های ارتباطی با نرم‌افزار هلو (Holoo)")
print("==================================================================")
holoo_files = glob.glob("**/*holoo*", recursive=True) + glob.glob("**/*sync*", recursive=True) + glob.glob("*.py")
for f in set(holoo_files):
    if not f.endswith((".pyc", ".log")) and ("holoo" in f.lower() or "sync" in f.lower() or "import" in f.lower()):
        print("  -->", f)

print("\n==================================================================")
print(" ۳. شبیه‌سازی زنده سوال کاربر در پایتون برای دیدن خطای کرش")
print("==================================================================")
try:
    from assistant_engine import chat, ChatRequest
    test_q = "امروز چه فاکتورهایی صادر شده ؟"
    print(f"در حال تست سوال: '{test_q}' ...")
    res = chat(ChatRequest(message=test_q))
    print("✓ نتیجه موفق:", res)
except Exception as e:
    print("❌ علت دقیق کرش پایتون:")
    traceback.print_exc()

print("\nدر حال تست استعلام کالا...")
try:
    from assistant_engine import chat, ChatRequest
    test_q2 = "کرم سوآلین ویرا"
    res2 = chat(ChatRequest(message=test_q2))
    print("✓ نتیجه موفق استعلام کالا:", res2)
except Exception as e:
    print("❌ علت کرش در استعلام کالا:")
    traceback.print_exc()
