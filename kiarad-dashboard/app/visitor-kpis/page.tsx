"use client";
import React, { useState, useEffect } from "react";
import { authFetch } from "../../lib/secure-api";
import Link from "next/link";

export default function VisitorKpiPage() {
  const [kpis, setKpis] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authFetch("/operations/visitors/kpis")
      .then(r => r.json())
      .then(data => { setKpis(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: "#0F172A", color: "#F8FAFC", padding: "24px", direction: "rtl", fontFamily: "tahoma" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      <div style={{ maxWidth: "1000px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: "bold", color: "#38BDF8", margin: 0 }}>📊 کارنامه و شاخص‌های کلیدی عملکرد (KPI) ویزیتورها</h1>
            <p style={{ fontSize: "13px", color: "#94A3B8", marginTop: "4px" }}>محاسبه درصد تحقق هدف، تعداد سفارش، نرخ تبدیل و رتبه‌بندی تیم فروش کرمان</p>
          </div>
          <Link href="/management" style={{ background: "#334155", color: "#F8FAFC", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px" }}>
            ← بازگشت به داشبورد
          </Link>
        </div>

        <div style={{ background: "#1E293B", borderRadius: "12px", border: "1px solid #334155", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead>
              <tr style={{ background: "#0F172A", color: "#94A3B8", textAlign: "right", borderBottom: "1px solid #334155" }}>
                <th style={{ padding: "14px 16px" }}>رتبه</th>
                <th style={{ padding: "14px 16px" }}>نام ویزیتور</th>
                <th style={{ padding: "14px 16px" }}>تحقق تارگت</th>
                <th style={{ padding: "14px 16px" }}>فروش محقق‌شده (ریال)</th>
                <th style={{ padding: "14px 16px" }}>تعداد سفارش</th>
                <th style={{ padding: "14px 16px" }}>نرخ موفقیت</th>
              </tr>
            </thead>
            <tbody>
              {kpis.map((k, idx) => (
                <tr key={`kpi-${k.salesperson_id || idx}-${idx}`} style={{ borderBottom: "1px solid #334155" }}>
                  <td style={{ padding: "14px 16px", color: idx === 0 ? "#FBBF24" : "#94A3B8", fontWeight: "bold" }}>#{idx + 1}</td>
                  <td style={{ padding: "14px 16px", fontWeight: "bold", color: "#F1F5F9" }}>{k.name}</td>
                  <td style={{ padding: "14px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <div style={{ flex: 1, height: "8px", background: "#334155", borderRadius: "4px", overflow: "hidden", minWidth: "60px" }}>
                        <div style={{ width: `${Math.min(k.achievement_percent, 100)}%`, height: "100%", background: k.achievement_percent >= 80 ? "#10B981" : "#F59E0B" }} />
                      </div>
                      <span style={{ fontSize: "12px", fontWeight: "bold" }}>{k.achievement_percent}٪</span>
                    </div>
                  </td>
                  <td style={{ padding: "14px 16px", color: "#34D399" }}>{Number(k.actual_sales).toLocaleString()}</td>
                  <td style={{ padding: "14px 16px" }}>{k.orders_count} فاکتور</td>
                  <td style={{ padding: "14px 16px", color: "#38BDF8" }}>{k.conversion_rate}٪</td>
                </tr>
              ))}
            </tbody>
          </table>
          {kpis.length === 0 && !loading && (
            <div style={{ padding: "30px", textAlign: "center", color: "#94A3B8" }}>داده‌ای برای ویزیتورها یافت نشد.</div>
          )}
        </div>
      </div>
    </div>
  );
}
