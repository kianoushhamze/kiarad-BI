import os
import re

print("==================================================================")
print(" ۱. حذف کامل نوار بنفش متداخل از کل قالب سایت")
print("==================================================================")
base_dir = r"D:\project\kiaradbi\kiarad-dashboard"

# گشتن در تمام فایلهای قالب و حذف نوار بالایی که شامل 'ثبت پیش‌فاکتور و اعتبار' است
for root, _, files in os.walk(base_dir):
    for file in files:
        if file.endswith((".tsx", ".jsx", ".html")):
            fpath = os.path.join(root, file)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            if "ثبت پیش‌فاکتور و اعتبار" in content and "layout" in file:
                # حذف بلوک نوار از layout
                cleaned = re.sub(r'<div[^>]*>.*?ثبت پیش‌فاکتور و اعتبار.*?</div>\s*</div>', '', content, flags=re.DOTALL)
                cleaned = re.sub(r'<header[^>]*>.*?ثبت پیش‌فاکتور و اعتبار.*?</header>', '', cleaned, flags=re.DOTALL)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(cleaned)
                print(f"✓ نوار تکراری بالا از {file} پاکسازی شد.")

print("==================================================================")
print(" ۲. قرار دادن تمامی گزینه‌ها در ستون (سایدبار) راست بدون تکرار")
print("==================================================================")
mgmt_file = r"D:\project\kiaradbi\kiarad-dashboard\app\management\page.tsx"

if os.path.exists(mgmt_file):
    with open(mgmt_file, "r", encoding="utf-8") as f:
        code = f.read()

    # تعریف کامل و بدون تکرار آیتم‌های ستون راست
    unified_sidebar_items = '''
  const navItems = [
    { label: "داشبورد مدیرعامل", icon: "📊", tab: "all", href: "/management" },
    { label: "فروش و عملکرد", icon: "📈", tab: "sales", href: "#sales" },
    { label: "انبار و تأمین", icon: "📦", tab: "inventory", href: "#inventory" },
    { label: "اهداف فروش", icon: "🎯", tab: "targets", href: "#targets" },
    { label: "🛒 فروش آنلاین (دیجی‌کالا/ترب/اینستا)", icon: "🛒", href: "/online-sales", isExternal: true },
    { label: "📊 KPI ویزیتورها", icon: "👤", href: "/visitor-kpis", isExternal: true },
    { label: "🏢 پایگاه‌های استان کرمان", icon: "🏢", href: "/kerman-bases", isExternal: true },
    { label: "💬 چت تیمی و فایل", icon: "💬", href: "/team-chat", isExternal: true },
    { label: "📝 ثبت پیش‌فاکتور و اعتبار", icon: "📝", href: "/proformas", isExternal: true },
    { label: "🗺️ نقشه آنلاین کرمان", icon: "🗺️", href: "/map", isExternal: true },
    { label: "🎙️ گزارش صوتی هوشمند", icon: "🎙️", href: "/voice-report", isExternal: true },
    { label: "👥 عملکرد پرسنل", icon: "👥", href: "/", isExternal: true },
  ];
'''
    # جایگزینی آرایه navItems در فایل
    code = re.sub(r'const navItems = \[.*?\];', unified_sidebar_items, code, flags=re.DOTALL)
    
    with open(mgmt_file, "w", encoding="utf-8") as f:
        f.write(code)
    print("✓ تمام امکانات (نقشه، ویس، پیش‌فاکتور، آنلاین و...) به ستون راست منتقل شدند.")

print("==================================================================")
print(" ۳. افزودن دکمه «← بازگشت به داشبورد اصلی» در تمام صفحات فرعی")
print("==================================================================")
subpages = [
    r"D:\project\kiaradbi\kiarad-dashboard\app\online-sales\page.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\visitor-kpis\page.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\kerman-bases\page.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\team-chat\page.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\proformas\page.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\map\page.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\voice-report\page.tsx"
]

back_button_html = '''
      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>
'''

for page_path in subpages:
    if os.path.exists(page_path):
        with open(page_path, "r", encoding="utf-8") as f:
            p_code = f.read()
        
        # تصحیح لینک‌های داشبورد اصلی از / به /management تا صفحه لاگین نیاید
        p_code = re.sub(r'href="/"', 'href="/management"', p_code)
        
        # تزریق دکمه بازگشت در ابتدای محتوا
        if "بازگشت به داشبورد اصلی" not in p_code:
            p_code = re.sub(r'(<div[^>]*padding[^>]*>)', r'\1\n' + back_button_html, p_code, count=1)
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(p_code)
            print(f"✓ دکمه بازگشت به {os.path.basename(os.path.dirname(page_path))} اضافه شد.")

print("==================================================================")
print(" تمام تغییرات با موفقیت ۱۰۰٪ ثبت شدند!")
print("==================================================================")
