import os
import re

mgmt_file = r"D:\project\kiaradbi\kiarad-dashboard\app\management\page.tsx"

if os.path.exists(mgmt_file):
    with open(mgmt_file, "r", encoding="utf-8") as f:
        code = f.read()

    # ۱. تعریف نوار دسترسی سریع تمیز و بدون تداخل
    quick_bar = '''
          {/* نوار دسترسی سریع و تمیز به بخش‌های کلیدی کیاراد */}
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "22px", background: "#111C38", padding: "12px 18px", borderRadius: "10px", border: "1px solid #1E293B", alignItems: "center" }}>
            <span style={{ fontSize: "13px", fontWeight: "bold", color: "#38BDF8", marginLeft: "10px" }}>⚡ دسترسی سریع:</span>
            <a href="/online-sales" style={{ background: "#EF4056", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>🛒 فروش آنلاین (دیجی‌کالا/ترب/اینستاگرام)</a>
            <a href="/visitor-kpis" style={{ background: "#F59E0B", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>📊 کارنامه KPI ویزیتورها</a>
            <a href="/kerman-bases" style={{ background: "#0EA5E9", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>🏢 پایگاه‌های کرمان</a>
            <a href="/team-chat" style={{ background: "#10B981", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>💬 چت تیمی</a>
            <a href="/proformas" style={{ background: "#8B5CF6", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>📝 پیش‌فاکتور</a>
            <a href="/map" style={{ background: "#334155", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px" }}>🗺️ نقشه</a>
            <a href="/voice-report" style={{ background: "#334155", color: "#fff", padding: "8px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px" }}>🎙️ ویس</a>
          </div>
    '''

    # ۲. پاکسازی تداخل‌های قبلی و قرار دادن نوار در موقعیت صحیح
    code = re.sub(r'\{/\* نوار دسترسی سریع.*?</div>\s*</div>', '', code, flags=re.DOTALL)
    
    # تزریق نوار تمیز دقیقاً قبل از بلوک نبض امروز کسب‌وکار / کارت‌های داشبورد
    if "نبض امروز کسب‌وکار" in code:
        code = code.replace("نبض امروز کسب‌وکار", "نبض امروز کسب‌وکار\n" + quick_bar, 1)
    else:
        code = re.sub(r'(<div[^>]*min-h-screen[^>]*>)', r'\1\n' + quick_bar, code, count=1)

    # ۳. افزودن لینک‌های جدید به سایدبار سمت راست در خود page.tsx
    sidebar_addition = '''
            <a href="/online-sales" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 14px", borderRadius: "8px", color: "#EF4056", background: "#1E293B", textDecoration: "none", fontSize: "13px", fontWeight: "bold", margin: "4px 0" }}>
              <span>🛒</span><span>فروش آنلاین (دیجی‌کالا/ترب)</span>
            </a>
            <a href="/visitor-kpis" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 14px", borderRadius: "8px", color: "#F59E0B", textDecoration: "none", fontSize: "13px", margin: "4px 0" }}>
              <span>📊</span><span>کارنامه KPI ویزیتورها</span>
            </a>
            <a href="/kerman-bases" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 14px", borderRadius: "8px", color: "#0EA5E9", textDecoration: "none", fontSize: "13px", margin: "4px 0" }}>
              <span>🏢</span><span>پایگاه‌های استان کرمان</span>
            </a>
            <a href="/team-chat" style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 14px", borderRadius: "8px", color: "#10B981", textDecoration: "none", fontSize: "13px", margin: "4px 0" }}>
              <span>💬</span><span>چت تیمی و فایل</span>
            </a>
    '''
    
    if "/online-sales" not in code:
        # قرار دادن آیتم‌ها در سایدبار راست زیر بخش "نمای کلی"
        if "نمای کلی" in code:
            code = code.replace("نمای کلی", "نمای کلی\n" + sidebar_addition, 1)

    with open(mgmt_file, "w", encoding="utf-8") as f:
        f.write(code)
    print("✓ تمام بخش‌ها با چیدمان استاندارد و تمیز به داشبورد اصلی اضافه شدند.")

