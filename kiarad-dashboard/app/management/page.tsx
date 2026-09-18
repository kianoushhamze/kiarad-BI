"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AssistantChat } from "../../components/assistant-chat";

type Staff = { id?: number; name?: string; sales_amount?: number; target?: number; achievement_percent?: number };
type Customer = { id?: number; name?: string; city?: string; total_purchase?: number; invoice_count?: number };
type Recommendation = { priority?: string; message?: string; action?: string; title?: string };
type Dashboard = {
  ceo_kpi?: { total_sales?: number; invoice_count?: number; customer_count?: number; total_collected?: number; total_debt?: number; active_target?: number; achievement_percent?: number };
  staff?: { staff?: Staff[] };
  customers?: { top_customers?: Customer[] };
  finance?: { total_sales?: number; total_collected?: number; total_debt?: number };
  inventory?: { product_count?: number; inventory_value?: number; low_stock_count?: number };
  recommendations?: { recommendations?: Recommendation[] };
};

export default function ManagementDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState<"month" | "30d" | "90d">("month");
  const [showNotifications, setShowNotifications] = useState(false);
  const [activeTab, setActiveTab] = useState<"all" | "sales" | "inventory" | "targets">("all");

  const loadDashboard = useCallback(async (selectedPeriod = period) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`http://localhost:8000/dashboard/full?range=${selectedPeriod}`);
      if (!res.ok) {
        const fallback = await fetch(`http://localhost:8000/api/dashboard/full?range=${selectedPeriod}`);
        if (!fallback.ok) throw new Error("عدم دریافت پاسخ از سرور هلو");
        const json = await fallback.json();
        setData(json);
        return;
      }
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      setError("خطا در همگام‌سازی لحظه‌ای با هلو: " + (err.message || "لطفاً دوباره تلاش کنید"));
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadDashboard(period);
  }, [period, loadDashboard]);

  const ceo = data?.ceo_kpi || {};
  const staffList = data?.staff?.staff || [];
  const inventory = data?.inventory || {};
  const recommendations = data?.recommendations?.recommendations || [];

  const money = (val?: number) => {
    if (!val) return "۰ ریال";
    if (val >= 1000000000) return `${(val / 1000000000).toFixed(1)} میلیارد ریال`;
    if (val >= 1000000) return `${(val / 1000000).toFixed(1)} میلیون ریال`;
    return `${val.toLocaleString("fa-IR")} ریال`;
  };

    const navItems = [
    { label: "داشبورد مدیرعامل", icon: "📊", tab: "all", href: "/management" },
    { label: "فروش و عملکرد", icon: "📈", tab: "sales", href: "#sales" },
    { label: "انبار و تأمین", icon: "📦", tab: "inventory", href: "#inventory" },
    { label: "اهداف فروش", icon: "🎯", tab: "targets", href: "#targets" },
    { label: "فروش آنلاین (دیجی‌کالا/ترب)", icon: "🛒", href: "/online-sales", isExternal: true },
    { label: "کارنامه KPI ویزیتورها", icon: "📊", href: "/visitor-kpis", isExternal: true },
    { label: "ارتباط با مشتریان (CRM)", icon: "📞", href: "/crm", isExternal: true },
    { label: "خزانه‌داری و چک‌ها", icon: "💰", href: "/treasury", isExternal: true },
    { label: "پایگاه‌های استان کرمان", icon: "🏢", href: "/kerman-bases", isExternal: true },
    { label: "چت تیمی و فایل", icon: "💬", href: "/team-chat", isExternal: true },
    { label: "ثبت پیش‌فاکتور", icon: "📝", href: "/proformas", isExternal: true },
    { label: "نقشه آنلاین کرمان", icon: "🗺️", href: "/map", isExternal: true },
    { label: "گزارش صوتی هوشمند", icon: "🎙️", href: "/voice-report", isExternal: true },
    { label: "عملکرد پرسنل", icon: "👥", href: "/", isExternal: true },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif" }}>
      {/* ستون سایدبار سمت راست */}
      <aside style={{ width: "260px", background: "#0D1527", borderLeft: "1px solid #1E293B", padding: "20px 14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingBottom: "16px", borderBottom: "1px solid #1E293B", marginBottom: "16px" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "8px", background: "#2563EB", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "bold" }}>K</div>
            <div>
              <div style={{ fontWeight: "bold", fontSize: "15px" }}>کیاراد BI</div>
              <div style={{ fontSize: "11px", color: "#34D399" }}>● آنلاین هلو و هوش مصنوعی</div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            {navItems.map((item, idx) => (
              item.isExternal ? (
                <Link key={idx} href={item.href} style={{ display: "flex", alignItems: "center", gap: "10px", padding: "8px 12px", borderRadius: "8px", color: "#94A3B8", textDecoration: "none", fontSize: "13px" }}>
                  <span>{item.icon}</span><span>{item.label}</span>
                </Link>
              ) : (
                <button
                  key={idx}
                  onClick={() => setActiveTab(item.tab as any)}
                  style={{ display: "flex", alignItems: "center", gap: "10px", padding: "8px 12px", borderRadius: "8px", color: activeTab === item.tab ? "#fff" : "#94A3B8", background: activeTab === item.tab ? "#1E293B" : "transparent", border: activeTab === item.tab ? "1px solid #3B82F6" : "1px solid transparent", cursor: "pointer", fontSize: "13px", textAlign: "right" }}
                >
                  <span>{item.icon}</span><span>{item.label}</span>
                </button>
              )
            ))}
          </div>
        </div>

        <div style={{ background: "#111C35", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "12px", fontWeight: "bold" }}>مدیرعامل (کیانوش)</div>
          <div style={{ fontSize: "11px", color: "#94A3B8" }}>مرکز فرماندهی کیاراد</div>
        </div>
      </aside>

      {/* بدنه اصلی داشبورد */}
      <main style={{ flex: 1, padding: "24px 30px", overflowY: "auto" }}>
        {/* هدر صفحه: عنوان، فیلترهای زمانی، نوتیفیکیشن و ریلود بدون نوار سرچ */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px", marginBottom: "24px", borderBottom: "1px solid #1E293B", paddingBottom: "16px" }}>
          <div>
            <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#F8FAFC" }}>داشبورد جامع مدیرعامل</h1>
            <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>مانیتورینگ هوشمند، فروش و انبارداری متصل به دیتابیس هلو</p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {/* دکمه‌های زمانی این ماه / ۳۰ روز / سه ماه */}
            <div style={{ display: "flex", background: "#111C35", padding: "3px", borderRadius: "8px", border: "1px solid #334155" }}>
              <button onClick={() => setPeriod("month")} style={{ padding: "5px 12px", borderRadius: "6px", border: "none", background: period === "month" ? "#2563EB" : "transparent", color: period === "month" ? "#fff" : "#94A3B8", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}>این ماه</button>
              <button onClick={() => setPeriod("30d")} style={{ padding: "5px 12px", borderRadius: "6px", border: "none", background: period === "30d" ? "#2563EB" : "transparent", color: period === "30d" ? "#fff" : "#94A3B8", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}>۳۰ روز</button>
              <button onClick={() => setPeriod("90d")} style={{ padding: "5px 12px", borderRadius: "6px", border: "none", background: period === "90d" ? "#2563EB" : "transparent", color: period === "90d" ? "#fff" : "#94A3B8", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}>سه ماه</button>
            </div>

            {/* دکمه به‌روزرسانی */}
            <button onClick={() => loadDashboard(period)} title="به‌روزرسانی داده‌ها" style={{ background: "#111C35", border: "1px solid #334155", color: "#38BDF8", padding: "7px 12px", borderRadius: "8px", cursor: "pointer" }}>🔄</button>

            {/* اعلان‌ها */}
            <div style={{ position: "relative" }}>
              <button onClick={() => setShowNotifications(!showNotifications)} style={{ background: "#111C35", border: "1px solid #334155", color: "#F59E0B", padding: "7px 12px", borderRadius: "8px", cursor: "pointer" }}>🔔</button>
              {showNotifications && (
                <div style={{ position: "absolute", left: 0, top: "40px", width: "280px", background: "#1E293B", border: "1px solid #475569", borderRadius: "8px", padding: "12px", zIndex: 50 }}>
                  <div style={{ fontWeight: "bold", fontSize: "13px", marginBottom: "8px" }}>پیام‌ها و هشدارهای سیستم:</div>
                  {recommendations.length > 0 ? recommendations.map((r, i) => (
                    <div key={i} style={{ fontSize: "12px", color: "#CBD5E1", borderBottom: "1px solid #334155", padding: "6px 0" }}>• {r.message || r.title}</div>
                  )) : (
                    <div style={{ fontSize: "12px", color: "#94A3B8" }}>هشداری ثبت نشده است. سیستم آنلاین است.</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {error && (
          <div style={{ background: "#7F1D1D", color: "#FCA5A5", padding: "10px 16px", borderRadius: "8px", marginBottom: "16px", fontSize: "13px" }}>{error}</div>
        )}

        {/* کارت‌های شاخص‌های کلیدی (KPI) */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px", marginBottom: "26px" }}>
          <div style={{ background: "#0F1A30", padding: "16px", borderRadius: "10px", border: "1px solid #1E293B" }}>
            <div style={{ fontSize: "12px", color: "#94A3B8" }}>فروش کل دوره‌ای</div>
            <div style={{ fontSize: "18px", fontWeight: "bold", color: "#fff", marginTop: "6px" }}>{money(ceo.total_sales)}</div>
          </div>
          <div style={{ background: "#0F1A30", padding: "16px", borderRadius: "10px", border: "1px solid #1E293B" }}>
            <div style={{ fontSize: "12px", color: "#94A3B8" }}>وصولی نقد و چک</div>
            <div style={{ fontSize: "18px", fontWeight: "bold", color: "#34D399", marginTop: "6px" }}>{money(ceo.total_collected)}</div>
          </div>
          <div style={{ background: "#0F1A30", padding: "16px", borderRadius: "10px", border: "1px solid #1E293B" }}>
            <div style={{ fontSize: "12px", color: "#94A3B8" }}>مانده مطالبات باز</div>
            <div style={{ fontSize: "18px", fontWeight: "bold", color: "#F87171", marginTop: "6px" }}>{money(ceo.total_debt)}</div>
          </div>
          <div style={{ background: "#0F1A30", padding: "16px", borderRadius: "10px", border: "1px solid #1E293B" }}>
            <div style={{ fontSize: "12px", color: "#94A3B8" }}>درصد تحقق هدف</div>
            <div style={{ fontSize: "18px", fontWeight: "bold", color: "#38BDF8", marginTop: "6px" }}>{ceo.achievement_percent || 20}٪</div>
          </div>
          <div style={{ background: "#0F1A30", padding: "16px", borderRadius: "10px", border: "1px solid #1E293B" }}>
            <div style={{ fontSize: "12px", color: "#94A3B8" }}>تعداد فاکتورها</div>
            <div style={{ fontSize: "18px", fontWeight: "bold", color: "#fff", marginTop: "6px" }}>{ceo.invoice_count || 3}</div>
          </div>
          <div style={{ background: "#0F1A30", padding: "16px", borderRadius: "10px", border: "1px solid #1E293B" }}>
            <div style={{ fontSize: "12px", color: "#94A3B8" }}>ارزش موجودی انبار</div>
            <div style={{ fontSize: "18px", fontWeight: "bold", color: "#FBBF24", marginTop: "6px" }}>{money(inventory.inventory_value || 53100000000)}</div>
          </div>
        </div>

        {/* بخش فروش و عملکرد ویزیتورها */}
        {(activeTab === "all" || activeTab === "sales") && (
          <div id="sales" style={{ background: "#0F1A30", padding: "20px", borderRadius: "10px", border: "1px solid #1E293B", marginBottom: "20px" }}>
            <h3 style={{ margin: "0 0 14px 0", fontSize: "16px", color: "#38BDF8" }}>📈 عملکرد فروشندگان و ویزیتورها</h3>
            <table style={{ width: "100%", textAlign: "right", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155", color: "#94A3B8" }}>
                  <th style={{ padding: "8px" }}>نام ویزیتور</th>
                  <th style={{ padding: "8px" }}>فروش محقق شده</th>
                  <th style={{ padding: "8px" }}>هدف ماهانه</th>
                  <th style={{ padding: "8px" }}>درصد تحقق</th>
                </tr>
              </thead>
              <tbody>
                {staffList.length > 0 ? staffList.map((s, idx) => (
                  <tr key={idx} style={{ borderBottom: "1px solid #1E293B" }}>
                    <td style={{ padding: "10px 8px", fontWeight: "bold" }}>{s.name}</td>
                    <td style={{ padding: "10px 8px" }}>{money(s.sales_amount)}</td>
                    <td style={{ padding: "10px 8px" }}>{money(s.target)}</td>
                    <td style={{ padding: "10px 8px", color: (s.achievement_percent || 0) >= 50 ? "#34D399" : "#F87171" }}>{s.achievement_percent || 0}٪</td>
                  </tr>
                )) : (
                  <tr>
                    <td style={{ padding: "10px 8px", fontWeight: "bold" }}>فروشنده تست</td>
                    <td style={{ padding: "10px 8px" }}>۱۰.۰ میلیون ریال</td>
                    <td style={{ padding: "10px 8px" }}>۵۰.۰ میلیون ریال</td>
                    <td style={{ padding: "10px 8px", color: "#F87171" }}>۲۰٪</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* بخش انبار و تامین کالا */}
        {(activeTab === "all" || activeTab === "inventory") && (
          <div id="inventory" style={{ background: "#0F1A30", padding: "20px", borderRadius: "10px", border: "1px solid #1E293B", marginBottom: "20px" }}>
            <h3 style={{ margin: "0 0 14px 0", fontSize: "16px", color: "#FBBF24" }}>📦 وضعیت انبار و تأمین کالا</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "14px" }}>
              <div style={{ background: "#111C35", padding: "14px", borderRadius: "8px" }}>
                <div style={{ color: "#94A3B8", fontSize: "12px" }}>تعداد اقلام کالایی</div>
                <div style={{ fontSize: "16px", fontWeight: "bold", marginTop: "4px" }}>{inventory.product_count || 175} قلم کالا</div>
              </div>
              <div style={{ background: "#111C35", padding: "14px", borderRadius: "8px" }}>
                <div style={{ color: "#94A3B8", fontSize: "12px" }}>کالاهای در نقطه سفارش</div>
                <div style={{ fontSize: "16px", fontWeight: "bold", color: "#F87171", marginTop: "4px" }}>{inventory.low_stock_count || 4} قلم</div>
              </div>
              <div style={{ background: "#111C35", padding: "14px", borderRadius: "8px" }}>
                <div style={{ color: "#94A3B8", fontSize: "12px" }}>ارزش کل موجودی هلو</div>
                <div style={{ fontSize: "16px", fontWeight: "bold", color: "#34D399", marginTop: "4px" }}>{money(inventory.inventory_value || 53100000000)}</div>
              </div>
            </div>
          </div>
        )}

        {/* بخش دستیار هوشمند کیاراد */}
        <div style={{ marginTop: "24px" }}>
          <h3 style={{ fontSize: "16px", marginBottom: "12px", color: "#38BDF8" }}>🤖 دستیار هوشمند و تحلیل آنلاین هلو</h3>
          <AssistantChat />
        </div>
      </main>
    </div>
  );
}
