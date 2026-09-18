import os
import re

print("==================================================================")
print(" ۱. پاکسازی هدرهای تکراری و تداخلی از app/layout.tsx")
print("==================================================================")
layout_path = r"D:\project\kiaradbi\kiarad-dashboard\app\layout.tsx"
if os.path.exists(layout_path):
    with open(layout_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # حذف هدرهای تزریق شده اضافی که روی داشبورد افتاده بودند
    content = re.sub(r'\{/\* نوار سراسری سامانه کیاراد.*?</header>', '', content, flags=re.DOTALL)
    with open(layout_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ هدر اضافی حذف شد و تداخل دولایه از بین رفت.")

print("==================================================================")
print(" ۲. زیباسازی و استانداردسازی سایدبار راست (Sidebar.tsx)")
print("==================================================================")
sidebar_candidates = [
    r"D:\project\kiaradbi\kiarad-dashboard\components\Sidebar.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\components\Sidebar.tsx",
    r"D:\project\kiaradbi\kiarad-dashboard\app\Sidebar.tsx"
]

clean_sidebar_code = '''"use client";
import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();

  const menuGroups = [
    {
      title: "عملیات اصلی",
      items: [
        { label: "داشبورد مدیرعامل", href: "/management", icon: "📊" },
        { label: "فروش آنلاین (دیجی‌کالا/ترب)", href: "/online-sales", icon: "🛒", badge: "جدید" },
        { label: "کارنامه KPI ویزیتورها", href: "/visitor-kpis", icon: "📈" },
        { label: "کل پایگاه‌های کرمان", href: "/kerman-bases", icon: "🏢" },
        { label: "چت تیمی و هماهنگی", href: "/team-chat", icon: "💬" },
      ]
    },
    {
      title: "ابزارهای میدانی و فروش",
      items: [
        { label: "ثبت پیش‌فاکتور", href: "/proformas", icon: "📝" },
        { label: "نقشه آنلاین کرمان", href: "/map", icon: "🗺️" },
        { label: "گزارش صوتی هوشمند", href: "/voice-report", icon: "🎙️" },
        { label: "عملکرد پرسنل", href: "/", icon: "👥" },
      ]
    }
  ];

  return (
    <aside style={{ width: "260px", minWidth: "260px", background: "#0B1329", borderLeft: "1px solid #1E293B", height: "100vh", position: "sticky", top: 0, padding: "20px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between", direction: "rtl", fontFamily: "tahoma, sans-serif" }}>
      <div>
        {/* برند و عنوان سامانه */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingBottom: "18px", borderBottom: "1px solid #1E293B", marginBottom: "18px" }}>
          <div style={{ width: "38px", height: "38px", borderRadius: "10px", background: "linear-gradient(135deg, #2563EB, #38BDF8)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "bold", fontSize: "18px", color: "#fff" }}>K</div>
          <div>
            <div style={{ fontSize: "16px", fontWeight: "bold", color: "#F8FAFC" }}>کیاراد BI</div>
            <div style={{ fontSize: "11px", color: "#34D399" }}>● آنلاین هلو و هوش مصنوعی</div>
          </div>
        </div>

        {/* منوهای گروه‌بندی‌شده */}
        {menuGroups.map((group, gIdx) => (
          <div key={gIdx} style={{ marginBottom: "18px" }}>
            <div style={{ fontSize: "11px", color: "#64748B", fontWeight: "bold", paddingRight: "8px", marginBottom: "6px" }}>{group.title}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              {group.items.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "9px 12px",
                      borderRadius: "8px",
                      textDecoration: "none",
                      fontSize: "13px",
                      color: isActive ? "#FFFFFF" : "#94A3B8",
                      background: isActive ? "#1E293B" : "transparent",
                      border: isActive ? "1px solid #3B82F6" : "1px solid transparent",
                      transition: "all 0.15s ease",
                      fontWeight: isActive ? "bold" : "normal"
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>{item.icon}</span>
                      <span>{item.label}</span>
                    </div>
                    {item.badge && (
                      <span style={{ fontSize: "10px", background: "#EF4056", color: "#fff", padding: "1px 6px", borderRadius: "10px" }}>{item.badge}</span>
                    )}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* بخش پایین سایدبار: وضعیت کاربر */}
      <div style={{ background: "#131E3A", padding: "12px", borderRadius: "8px", border: "1px solid #1E293B" }}>
        <div style={{ fontSize: "12px", color: "#F8FAFC", fontWeight: "bold" }}>مدیریت (کیانوش)</div>
        <div style={{ fontSize: "11px", color: "#94A3B8" }}>مرکز فرماندهی کیاراد زیست</div>
      </div>
    </aside>
  );
}
'''

for s_path in sidebar_candidates:
    os.makedirs(os.path.dirname(s_path), exist_ok=True)
    with open(s_path, "w", encoding="utf-8") as f:
        f.write(clean_sidebar_code)
    print(f"✓ سایدبار مدرن و استاندارد در {os.path.basename(s_path)} مستقر شد.")

print("==================================================================")
print(" ۳. پاکسازی و آراستن هدر داخلی در داشبورد مدیریت (app/management/page.tsx)")
print("==================================================================")
mgmt_path = r"D:\project\kiaradbi\kiarad-dashboard\app\management\page.tsx"
if os.path.exists(mgmt_path):
    with open(mgmt_path, "r", encoding="utf-8") as f:
        m_code = f.read()
    
    # حذف نوارهای بنری بنفش یا دکمه‌های متداخل قدیمی در بالای صفحه
    m_code = re.sub(r'<div[^>]*>.*?ثبت پیش‌فاکتور و اعتبار.*?</div>', '', m_code, flags=re.DOTALL)
    m_code = re.sub(r'\{/\* منوی دسترسی سریع سیستم یکپارچه کیاراد \*/\}.*?</div>\s*</div>', '', m_code, flags=re.DOTALL)
    
    with open(mgmt_path, "w", encoding="utf-8") as f:
        f.write(m_code)
    print("✓ هدرهای بنفش و عناصر زائد داخل صفحه مدیریت پاکسازی شدند.")

print("==================================================================")
print(" تمام مراحل سروسامان دادن به داشبورد با موفقیت ۱۰۰٪ پایان یافت!")
print("==================================================================")
