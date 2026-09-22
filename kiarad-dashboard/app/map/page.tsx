export default function MapPage() {
  return (
    <div style={{ height: "100vh", background: "#0F172A", padding: "16px", direction: "rtl", fontFamily: "tahoma" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h1 style={{ color: "#A855F7", fontSize: "20px", fontWeight: "bold" }}>🗺️ نقشه آنلاین استان کرمان و ویزیتورها</h1>
        <div style={{ display: "flex", gap: "10px" }}>
          <a href="/proformas" style={{ background: "#334155", color: "#FFF", padding: "6px 14px", borderRadius: "6px", textDecoration: "none", fontSize: "13px" }}>📄 پیش‌فاکتور</a>
          <a href="/login" style={{ background: "#7C3AED", color: "#FFF", padding: "6px 14px", borderRadius: "6px", textDecoration: "none", fontSize: "13px" }}>📊 داشبورد اصلی</a>
        </div>
      </div>
      <iframe src="/map_view.html" style={{ width: "100%", height: "calc(100vh - 85px)", border: "1px solid #334155", borderRadius: "12px" }} />
    </div>
  );
}
