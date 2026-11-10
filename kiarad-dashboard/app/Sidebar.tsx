"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();

  
  const menuGroups = [
    {
      title: "مدیریت و مالی",
      items: [
        { label: "داشبورد مدیرعامل", href: "/management", icon: "📊" },
        { label: "گزارش صبحگاهی", href: "/morning-brief", icon: "🌅", badge: "جدید" },
        { label: "خزانه", href: "/treasury", icon: "💰" },
        { label: "نرخ‌نامه و کاتالوگ", href: "/catalog", icon: "🏷️" },
        { label: "فروش آنلاین (دیجی‌کالا/ترب)", href: "/online-sales", icon: "🛒", badge: "جدید" }
      ]
    },
    {
      title: "فروش و کمپین",
      items: [
        { label: "ثبت پیش‌فاکتور", href: "/proformas", icon: "📝" },
        { label: "کمپین‌های فروش و پاداش", href: "/campaigns", icon: "🎯", badge: "هوشمند" },
        { label: "کارنامه KPI ویزیتورها", href: "/management", icon: "📈" },
        { label: "کل پایگاه‌های کرمان", href: "/kerman-bases", icon: "🏢" },
        { label: "نقشه آنلاین کرمان", href: "/map", icon: "🗺️" }
      ]
    },
    {
      title: "تیم و پرسنل",
      items: [
        { label: "قرارداد و حقوق ویزیتور", href: "/compensation", icon: "📄" },
        { label: "تعریف و مدیریت ویزیتورها", href: "/manager", icon: "👥" },
        { label: "پنل عملیات ویزیتور", href: "/personnel", icon: "💼" },
        { label: "تسک‌ها و پیگیری‌ها", href: "/tasks", icon: "✅" },
        { label: "چت تیمی و هماهنگی", href: "/team-chat", icon: "💬" }
      ]
    },
    {
      title: "گزارش‌های میدانی",
      items: [
        { label: "گزارش صوتی هوشمند", href: "/voice-report", icon: "🎙️" },
        { label: "گزارش روزانه", href: "/daily-reports", icon: "🗒️" },
        { label: "گزارش بازدیدها", href: "/visitors", icon: "📍" },
        { label: "عملکرد پرسنل", href: "/", icon: "👥" }
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
