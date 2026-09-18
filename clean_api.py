import shutil

# تهیه نسخه پشتیبان
shutil.copyfile("api.py", "api.py.bak")

# حذف خطوط دیجی‌کالا از چرخه بوت سرور
with open("api.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

clean_lines = [line for line in lines if "digikala" not in line.lower()]

with open("api.py", "w", encoding="utf-8") as f:
    f.writelines(clean_lines)

print("api.py cleaned successfully! Digikala dependency detached from core server.")
