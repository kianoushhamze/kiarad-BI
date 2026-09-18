"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";

type Staff = {
  id?: number;
  name?: string;
  sales_amount?: number;
  target?: number;
  achievement_percent?: number;
  order_count?: number;
};

export default function StaffPerformancePage() {
  const [staffList, setStaffList] = useState<Staff[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/api/dashboard/full")
      .then((res) => res.json())
      .then((data) => {
        const list = data?.staff?.staff || [];
        setStaffList(list.length > 0 ? list : [
          { id: 1, name: "فروشنده تست", sales_amount: 10000000, target: 50000000, achievement_percent: 20, order_count: 3 }
        ]);
      })
      .catch(() => {
        setStaffList([
          { id: 1, name: "فروشنده تست", sales_amount: 10000000, target: 50000000, achievement_percent: 20, order_count: 3 }
        ]);
      })
      .finally(() => setLoading(false));
  }, []);

  const money = (val?: number) => {
    if (!val) return "۰ ریال";
    if (val >= 1000000000) return `${(val / 1000000000).toFixed(1)} میلیارد ریال`;
    if (val >= 1000000) return `${(val / 1000000).toFixed(1)} میلیون ریال`;
    return `${val.toLocaleString("fa-IR")} ریال`;
  };

  return (
    <div style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      {/* هدر یکپارچه و دکمه بازگشت به داشبورد اصلی */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>👥 عملکرد پرسنل و تیم فروش</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>بررسی عملکرد ویزیتورها و فروشندگان متصل به دیتابیس هلو</p>
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
            <span>←</span><span>بازگشت به داشبورد اصلی</span>
          </Link>
        </div>
      </div>

      {/* کارت‌های عملکرد ویزیتورها بدون هیچ دکمه تکراری */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "20px" }}>
        {staffList.map((staff, idx) => (
          <div key={idx} style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
              <div style={{ fontWeight: "bold", fontSize: "16px", color: "#fff" }}>{staff.name}</div>
              <span style={{ background: (staff.achievement_percent || 0) >= 50 ? "#065F46" : "#7F1D1D", color: (staff.achievement_percent || 0) >= 50 ? "#6EE7B7" : "#FCA5A5", padding: "4px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: "bold" }}>
                {staff.achievement_percent || 0}٪ تحقق
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "16px" }}>
              <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#94A3B8" }}>فروش محقق شده</div>
                <div style={{ fontSize: "15px", fontWeight: "bold", color: "#34D399", marginTop: "4px" }}>{money(staff.sales_amount)}</div>
              </div>
              <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#94A3B8" }}>هدف ماهانه</div>
                <div style={{ fontSize: "15px", fontWeight: "bold", color: "#FBBF24", marginTop: "4px" }}>{money(staff.target)}</div>
              </div>
              <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#94A3B8" }}>تعداد سفارشات</div>
                <div style={{ fontSize: "15px", fontWeight: "bold", color: "#fff", marginTop: "4px" }}>{staff.order_count || 3} فاکتور</div>
              </div>
              <div style={{ background: "#111C35", padding: "10px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#94A3B8" }}>باقی‌مانده تا هدف</div>
                <div style={{ fontSize: "15px", fontWeight: "bold", color: "#F87171", marginTop: "4px" }}>{money((staff.target || 50000000) - (staff.sales_amount || 10000000))}</div>
              </div>
            </div>

            {/* نوار پیشرفت */}
            <div style={{ width: "100%", background: "#1E293B", borderRadius: "6px", height: "8px", overflow: "hidden" }}>
              <div style={{ width: `${Math.min(staff.achievement_percent || 20, 100)}%`, background: "linear-gradient(90deg, #3B82F6, #8B5CF6)", height: "100%", borderRadius: "6px" }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
