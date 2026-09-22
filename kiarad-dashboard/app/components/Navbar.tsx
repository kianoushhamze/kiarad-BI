"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();
  const navItems = [
    { label: "داشبورد اصلی", href: "/management" },
    { label: "عملکرد پرسنل", href: "/" },
    { label: "📊 KPI ویزیتورها", href: "/visitor-kpis" },
    { label: "🏢 پایگاه‌های کرمان", href: "/kerman-bases" },
    { label: "💬 چت تیمی", href: "/team-chat" },
    { label: "📝 پیش‌فاکتور", href: "/proformas" },
    { label: "🗺️ نقشه آنلاین", href: "/map" },
    { label: "🎙️ گزارش صوتی", href: "/voice-report" },
  ];

  return (
    <header style={{ background: "#0F172A", borderBottom: "1px solid #1E293B", padding: "10px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "18px", fontWeight: "bold", color: "#38BDF8" }}>سیستم یکپارچه کیاراد</span>
          <span style={{ fontSize: "11px", background: "#1E293B", color: "#94A3B8", padding: "2px 8px", borderRadius: "12px" }}>هوشمند آنلاین</span>
        </div>

        <nav style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                style={{
                  padding: "6px 12px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: isActive ? "bold" : "normal",
                  textDecoration: "none",
                  color: isActive ? "#fff" : "#94A3B8",
                  background: isActive ? "#2563EB" : "transparent",
                  border: isActive ? "1px solid #3B82F6" : "1px solid transparent",
                  transition: "all 0.2s",
                }}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
