
"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { secureApi } from "../lib/secure-api";

type Staff = {
  id?: number; name?: string; sales_amount?: number;
  target?: number; achievement_percent?: number; order_count?: number;
};

export default function StaffPerformancePage() {
  const staffListInit: Array<Staff> = new Array();
  const emptyList: Array<Staff> = new Array();
  const [staffList, setStaffList] = useState<Array<Staff>>(staffListInit);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const setEmpty = function () { setStaffList(emptyList); };

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const data = (await secureApi("/api/dashboard/full", { method: "GET" })) as any;
      const fresh: Array<Staff> = new Array();
      const raw = data && data.staff && data.staff.staff;
      if (raw) raw.forEach(function (s: Staff) { fresh.push(s); });
      setStaffList(fresh);
    } catch (err: any) {
      const msg = err && err.message ? String(err.message) : "خطای ناشناخته";
      setEmpty();
      setError(msg.indexOf("Authentication") !== -1
        ? "ابتدا از صفحه ورود وارد سیستم شوید."
        : "دریافت داده از سرور ناموفق بود: " + msg);
    } finally { setLoading(false); }
  }, new Array());

  useEffect(function () { load(); }, new Array(load));

  const money = function (val?: number) {
    if (!val) return "۰ ریال";
    if (val >= 1000000000) return (val / 1000000000).toFixed(1) + " میلیارد ریال";
    if (val >= 1000000) return (val / 1000000).toFixed(1) + " میلیون ریال";
    return val.toLocaleString("fa-IR") + " ریال";
  };

  return (
    <div style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>👥 عملکرد پرسنل و تیم فروش</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>داده‌ی زنده از دیتابیس — بدون هیچ داده‌ی نمایشی</p>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button type="button" onClick={function () { load(); }}
            style={{ background: "#1E293B", border: "1px solid #334155", color: "#F8FAFC", padding: "8px 18px", borderRadius: "8px", cursor: "pointer", fontSize: "13px" }}>
            ↻ تلاش مجدد
          </button>
          <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold" }}>
            ← داشبورد اصلی
          </Link>
        </div>
      </div>

      {error ? (
        <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "16px 20px", borderRadius: "10px", marginBottom: "20px", fontSize: "14px" }}>⚠️ {error}</div>
      ) : null}

      {loading ? (
        <div style={{ color: "#94A3B8", padding: "40px", textAlign: "center" }}>در حال دریافت داده‌ی زنده...</div>
      ) : null}

      {!loading && !error && staffList.length === 0 ? (
        <div style={{ color: "#94A3B8", padding: "40px", textAlign: "center", background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px" }}>
          هنوز هیچ داده‌ی عملکردی ثبت نشده است.
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "20px" }}>
        {staffList.map(function (staff, idx) {
          const ach = staff.achievement_percent || 0;
          const good = ach >= 50;
          return (
            <div key={idx} style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "14px" }}>
                <div style={{ fontWeight: "bold", fontSize: "16px" }}>{staff.name || "بی‌نام"}</div>
                <span style={{ background: good ? "#065F46" : "#7F1D1D", color: good ? "#6EE7B7" : "#FCA5A5", padding: "4px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: "bold" }}>
                  {ach}٪ تحقق
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "16px" }}>
                <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#94A3B8" }}>فروش محقق‌شده</div>
                  <div style={{ fontSize: "15px", fontWeight: "bold", color: "#34D399", marginTop: "4px" }}>{money(staff.sales_amount)}</div>
                </div>
                <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#94A3B8" }}>هدف ماهانه</div>
                  <div style={{ fontSize: "15px", fontWeight: "bold", color: "#FBBF24", marginTop: "4px" }}>{money(staff.target)}</div>
                </div>
                <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#94A3B8" }}>تعداد سفارشات</div>
                  <div style={{ fontSize: "15px", fontWeight: "bold", color: "#fff", marginTop: "4px" }}>{staff.order_count || 0} فاکتور</div>
                </div>
                <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#94A3B8" }}>باقی‌مانده تا هدف</div>
                  <div style={{ fontSize: "15px", fontWeight: "bold", color: "#F87171", marginTop: "4px" }}>{money(Math.max((staff.target || 0) - (staff.sales_amount || 0), 0))}</div>
                </div>
              </div>
              <div style={{ width: "100%", background: "#1E293B", borderRadius: "6px", height: "8px", overflow: "hidden" }}>
                <div style={{ width: Math.min(ach, 100) + "%", background: "linear-gradient(90deg, #3B82F6, #8B5CF6)", height: "100%", borderRadius: "6px" }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
