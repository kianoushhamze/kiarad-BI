import sys
import os
from sqlalchemy import text
from db import engine
from operations import hash_password

ROLES_MAP = {
    "1": ("salesperson", "ویزیتور / نماینده علمی"),
    "2": ("sales_manager", "مدیر فروش"),
    "3": ("finance", "مدیر مالی و حسابداری"),
    "4": ("ceo", "مدیرعامل / دسترسی کامل")
}

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def list_users():
    print("\n--- فهرست کاربران سیستم ---")
    with engine.connect() as conn:
        users = conn.execute(text("""
            SELECT u.id, u.username, u.full_name, u.role, u.is_active, sp.name as sp_name
            FROM users u
            LEFT JOIN salespersons sp ON sp.id = u.salesperson_id
            ORDER BY u.id
        """)).mappings().all()
        
        if not users:
            print("هیچ کاربری یافت نشد.")
            return []
            
        print(f"{'شناسه':<6} | {'نام کاربری':<15} | {'نام کامل':<20} | {'نقش':<15} | {'وضعیت':<10}")
        print("-" * 75)
        for u in users:
            status = "فعال ✅" if u['is_active'] == 1 else "مسدود ⛔"
            role_desc = next((desc for _, (r, desc) in ROLES_MAP.items() if r == u['role']), u['role'])
            print(f"{u['id']:<6} | {u['username']:<15} | {u['full_name']:<20} | {role_desc:<15} | {status:<10}")
        return users

def add_user():
    print("\n--- ایجاد کاربر جدید ---")
    username = input("نام کاربری انگلیسی: ").strip().lower()
    full_name = input("نام و نام خانوادگی: ").strip()
    password = input("رمز عبور (حداقل ۱۰ کاراکتر): ").strip()
    
    print("\nانتخاب نقش کاربر:")
    for k, (_, desc) in ROLES_MAP.items():
        print(f"[{k}] {desc}")
    r_choice = input("شماره نقش: ").strip()
    role = ROLES_MAP.get(r_choice, ("salesperson", ""))[0]
    
    salesperson_id = None
    if role == "salesperson":
        phone = input("شماره تماس ویزیتور: ").strip()
        with engine.begin() as conn:
            sp = conn.execute(text("INSERT INTO salespersons (name, phone) VALUES (:n, :p) RETURNING id"), {"n": full_name, "p": phone}).first()
            salesperson_id = sp[0]
            
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (username, password_hash, full_name, role, salesperson_id, is_active, created_at)
            VALUES (:u, :p, :f, :r, :s, 1, NOW())
        """), {
            "u": username,
            "p": hash_password(password),
            "f": full_name,
            "r": role,
            "s": salesperson_id
        })
    print(f"\n✅ کاربر '{full_name}' با نقش '{role}' با موفقیت ساخته شد.")

def change_role():
    users = list_users()
    if not users: return
    user_id = input("\nشناسه (ID) کاربری که می‌خواهید نقشش را تغییر دهید: ").strip()
    
    print("\nنقش جدید را انتخاب کنید:")
    for k, (_, desc) in ROLES_MAP.items():
        print(f"[{k}] {desc}")
    r_choice = input("شماره نقش جدید: ").strip()
    new_role = ROLES_MAP.get(r_choice, (None, None))[0]
    if not new_role:
        print("شماره نقش نامعتبر است.")
        return
        
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET role = :r WHERE id = :id"), {"r": new_role, "id": user_id})
    print(f"\n✅ نقش کاربر شناسه {user_id} به '{new_role}' تغییر یافت.")

def toggle_status():
    users = list_users()
    if not users: return
    user_id = input("\nشناسه (ID) کاربر مورد نظر: ").strip()
    
    with engine.begin() as conn:
        row = conn.execute(text("SELECT is_active FROM users WHERE id = :id"), {"id": user_id}).first()
        if not row:
            print("کاربر یافت نشد.")
            return
        new_status = 0 if row[0] == 1 else 1
        conn.execute(text("UPDATE users SET is_active = :s WHERE id = :id"), {"s": new_status, "id": user_id})
    
    state_txt = "مسدود و غیرفعال" if new_status == 0 else "فعال"
    print(f"\n✅ دسترسی کاربر شناسه {user_id} اکنون {state_txt} شد.")

def reset_password():
    users = list_users()
    if not users: return
    user_id = input("\nشناسه (ID) کاربر برای تغییر پسورد: ").strip()
    new_pass = input("رمز عبور جدید: ").strip()
    
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET password_hash = :p WHERE id = :id"), {
            "p": hash_password(new_pass),
            "id": user_id
        })
    print(f"\n✅ رمز عبور کاربر شناسه {user_id} تغییر یافت.")

def delete_user():
    users = list_users()
    if not users: return
    user_id = input("\nشناسه (ID) کاربری که می‌خواهید کلاً حذف شود: ").strip()
    confirm = input(f"آیا از حذف دائم کاربر {user_id} اطمینان دارید؟ (yes/no): ").strip().lower()
    if confirm == "yes":
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        print(f"\n🗑️ کاربر شناسه {user_id} حذف گردید.")

def main():
    while True:
        print("\n" + "="*40)
        print("    مرکز مدیریت کاربران کیاراد بی‌آی")
        print("="*40)
        print(" مشاهده لیست کاربران و وضعیت دسترسی")
        print("[2] ساخت کاربر جدید (ویزیتور / مدیر)")
        print("[3] تغییر سطح دسترسی و نقش کاربر")
        print("[4] مسدود کردن / فعال‌سازی دسترسی کاربر")
        print("[5] تغییر رمز عبور کاربر")
        print("[6] حذف دائم یک کاربر")
        print("[0] خروج")
        
        c = input("\nگزینه مورد نظر را وارد کنید: ").strip()
        if c == "1": list_users()
        elif c == "2": add_user()
        elif c == "3": change_role()
        elif c == "4": toggle_status()
        elif c == "5": reset_password()
        elif c == "6": delete_user()
        elif c == "0": break
        else: print("گزینه نامعتبر است.")

if __name__ == "__main__":
    main()
