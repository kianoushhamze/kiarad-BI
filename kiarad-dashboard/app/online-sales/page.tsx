"use client";

import React, { useState } from "react";

export default function OnlineSalesPage() {
  const [activeTab, setActiveTab] = useState("digikala");
  const [syncStatus, setSyncStatus] = useState("همگام با انبار هلو");

  return (
    <div style={{ maxWidth: "1200px", margin: "20px auto", padding: "20px", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      {/* هدر صفحه */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #334155", paddingBottom: "16px", marginBottom: "20px" }}>
        <div>
          <h1 style={{ fontSize: "22px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>🌐 مرکز مدیریت فروش آنلاین و چندکاناله (Omnichannel)</h1>
          <p style={{ margin: "6px 0 0 0", color: "#94A3B8", fontSize: "13px" }}>اتصال مستقیم به پنل فروشندگان دیجی‌کالا، ربات ترب، موتور ایمالز، فروشگاه اینترنتی و دایرکت اینستاگرام</p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <span style={{ background: "#065F46", color: "#6EE7B7", padding: "6px 14px", borderRadius: "20px", fontSize: "12px", border: "1px solid #059669" }}>● {syncStatus}</span>
          <button onClick={() => { setSyncStatus("در حال همگام‌سازی..."); setTimeout(() => setSyncStatus("همگام با انبار هلو"), 1500); }} style={{ background: "#2563EB", color: "#fff", border: "none", padding: "7px 14px", borderRadius: "8px", cursor: "pointer", fontSize: "12px" }}>🔄 به‌روزرسانی قیمت و موجودی</button>
        </div>
      </div>

      {/* تب‌های پلتفرم‌ها */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "20px", borderBottom: "1px solid #1E293B", paddingBottom: "10px" }}>
        {[
          { id: "digikala", label: "🛒 دیجی‌کالا (Digikala)", color: "#EF4056" },
          { id: "torob_emalls", label: "🔍 ترب و ایمالز (Torob & Emalls)", color: "#D97706" },
          { id: "website", label: "🛍️ وب‌سایت فروشگاهی (Ordibeauty)", color: "#2563EB" },
          { id: "instagram", label: "📸 اینستاگرام و دایرکت (Instagram)", color: "#E1306C" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "10px 18px",
              borderRadius: "8px",
              border: activeTab === tab.id ? `2px solid ${tab.color}` : "1px solid #334155",
              background: activeTab === tab.id ? "#1E293B" : "transparent",
              color: activeTab === tab.id ? "#fff" : "#94A3B8",
              cursor: "pointer",
              fontWeight: activeTab === tab.id ? "bold" : "normal",
              fontSize: "14px"
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* محتوای تب دیجی‌کالا */}
      {activeTab === "digikala" && (
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "20px" }}>
          <div style={{ background: "#1E293B", padding: "20px", borderRadius: "10px", border: "1px solid #334155" }}>
            <h3 style={{ color: "#EF4056", marginTop: 0 }}>📦 سفارشات فعال دیجی‌کالا (آماده ارسال به انبار)</h3>
            <table style={{ width: "100%", textAlign: "right", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #475569", color: "#94A3B8" }}>
                  <th style={{ padding: "8px" }}>کد سفارش</th>
                  <th style={{ padding: "8px" }}>کالا</th>
                  <th style={{ padding: "8px" }}>تعداد</th>
                  <th style={{ padding: "8px" }}>مهلت ارسال</th>
                  <th style={{ padding: "8px" }}>عملیات</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: "1px solid #334155" }}>
                  <td style={{ padding: "10px 8px" }}>DKP-847291</td>
                  <td style={{ padding: "10px 8px" }}>کرم ترمیم‌کننده سوآلین ویرا</td>
                  <td style={{ padding: "10px 8px" }}>۲ عدد</td>
                  <td style={{ padding: "10px 8px", color: "#FBBF24" }}>تا فردا ساعت ۱۲:۰۰</td>
                  <td style={{ padding: "10px 8px" }}>
                    <button onClick={() => alert("ارسال دستور پرینت لیبل به پرینتر لیبل‌زن Brother QL-800")} style={{ background: "#EF4056", color: "#fff", border: "none", padding: "5px 10px", borderRadius: "5px", cursor: "pointer", fontSize: "12px" }}>🖨️ چاپ لیبل QL-800</button>
                  </td>
                </tr>
                <tr style={{ borderBottom: "1px solid #334155" }}>
                  <td style={{ padding: "10px 8px" }}>DKP-912048</td>
                  <td style={{ padding: "10px 8px" }}>ژل شستشوی درمالیست</td>
                  <td style={{ padding: "10px 8px" }}>۱ عدد</td>
                  <td style={{ padding: "10px 8px", color: "#34D399" }}>ارسال شده به هاب کرمان</td>
                  <td style={{ padding: "10px 8px" }}>
                    <span style={{ color: "#94A3B8", fontSize: "12px" }}>تکمیل شده</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div style={{ background: "#1E293B", padding: "20px", borderRadius: "10px", border: "1px solid #334155" }}>
            <h3 style={{ color: "#F8FAFC", marginTop: 0 }}>⚙️ تنظیمات اتصال به Seller Center</h3>
            <p style={{ fontSize: "12px", color: "#94A3B8" }}>تنظیم کلیدهای دسترسی جهت سینک خودکار موجودی انبار هلو با پنل فروشندگان دیجی‌کالا:</p>
            <div style={{ marginBottom: "12px" }}>
              <label style={{ fontSize: "12px", display: "block", marginBottom: "4px" }}>API Key فروشنده:</label>
              <input type="password" value="********************************" readOnly style={{ width: "100%", background: "#0F172A", border: "1px solid #475569", color: "#fff", padding: "8px", borderRadius: "6px" }} />
            </div>
            <div style={{ marginBottom: "12px" }}>
              <label style={{ fontSize: "12px", display: "block", marginBottom: "4px" }}>پرینتر پیش‌فرض لیبل:</label>
              <select style={{ width: "100%", background: "#0F172A", border: "1px solid #475569", color: "#fff", padding: "8px", borderRadius: "6px" }}>
                <option>Brother QL-800 (DK-11209 Label 29x90mm)</option>
                <option>Brother QL-800 (DK-22205 Continuous 62mm)</option>
              </select>
            </div>
            <button onClick={() => alert("تنظیمات با موفقیت ذخیره شد.")} style={{ width: "100%", background: "#10B981", color: "#fff", border: "none", padding: "8px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold" }}>ذخیره اتصال</button>
          </div>
        </div>
      )}

      {/* محتوای تب ترب و ایمالز */}
      {activeTab === "torob_emalls" && (
        <div style={{ background: "#1E293B", padding: "20px", borderRadius: "10px", border: "1px solid #334155" }}>
          <h3 style={{ color: "#D97706", marginTop: 0 }}>📊 پایش قیمت رقبا و جایگاه در ترب و ایمالز</h3>
          <p style={{ fontSize: "13px", color: "#94A3B8" }}>بررسی خودکار قیمت‌های ثبت‌شده در بازار و پیشنهاد قیمت بهینه جهت حفظ جایگاه اول خرید:</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px", marginTop: "14px" }}>
            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px", border: "1px solid #334155" }}>
              <div style={{ fontWeight: "bold", fontSize: "15px", marginBottom: "8px" }}>کرم ترمیم‌کننده سوآلین ویرا</div>
              <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "4px" }}>قیمت فروش شما: <span style={{ color: "#34D399", fontWeight: "bold" }}>۴۸۰,۰۰۰ تومان</span></div>
              <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "8px" }}>کمترین قیمت در ترب: <span style={{ color: "#F87171" }}>۴۹۵,۰۰۰ تومان</span></div>
              <span style={{ background: "#065F46", color: "#6EE7B7", padding: "4px 8px", borderRadius: "4px", fontSize: "11px" }}>✓ شما جایگاه اول ترب هستید</span>
            </div>

            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px", border: "1px solid #334155" }}>
              <div style={{ fontWeight: "bold", fontSize: "15px", marginBottom: "8px" }}>سرم ضدلک ام‌سی کازمتیک</div>
              <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "4px" }}>قیمت فروش شما: <span style={{ color: "#FBBF24", fontWeight: "bold" }}>۱,۲۵۰,۰۰۰ تومان</span></div>
              <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "8px" }}>کمترین قیمت در ترب: <span style={{ color: "#F87171" }}>۱,۲۳۰,۰۰۰ تومان</span></div>
              <span style={{ background: "#7F1D1D", color: "#FCA5A5", padding: "4px 8px", borderRadius: "4px", fontSize: "11px" }}>⚠️ نیاز به تعدیل قیمت جهت رقابت</span>
            </div>
          </div>
        </div>
      )}

      {/* محتوای تب سایت اختصاصی */}
      {activeTab === "website" && (
        <div style={{ background: "#1E293B", padding: "20px", borderRadius: "10px", border: "1px solid #334155" }}>
          <h3 style={{ color: "#2563EB", marginTop: 0 }}>🌐 وضعیت درگاه و سفارشات سایت Ordibeauty.com</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", marginBottom: "20px" }}>
            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px" }}>
              <div style={{ color: "#94A3B8", fontSize: "12px" }}>سفارشات امروز سایت</div>
              <div style={{ fontSize: "20px", fontWeight: "bold", color: "#fff", marginTop: "6px" }}>۱۲ سفارش</div>
            </div>
            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px" }}>
              <div style={{ color: "#94A3B8", fontSize: "12px" }}>فروش ریالی امروز وب‌سایت</div>
              <div style={{ fontSize: "20px", fontWeight: "bold", color: "#34D399", marginTop: "6px" }}>۱۸,۴۰۰,۰۰۰ ریال</div>
            </div>
            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px" }}>
              <div style={{ color: "#94A3B8", fontSize: "12px" }}>وضعیت اتصال به انبار مرکزی</div>
              <div style={{ fontSize: "16px", fontWeight: "bold", color: "#38BDF8", marginTop: "8px" }}>آنلاین و پایدار</div>
            </div>
          </div>
        </div>
      )}

      {/* محتوای تب اینستاگرام */}
      {activeTab === "instagram" && (
        <div style={{ background: "#1E293B", padding: "20px", borderRadius: "10px", border: "1px solid #334155" }}>
          <h3 style={{ color: "#E1306C", marginTop: 0 }}>📱 اینستاگرام، ریلز و دایرکت‌های فروش</h3>
          <p style={{ fontSize: "13px", color: "#94A3B8" }}>مدیریت لیدهای دریافتی از اینستاگرام، کمپین‌های ویدیویی و صدور سریع فاکتور از دایرکت:</p>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px" }}>
              <h4 style={{ margin: "0 0 10px 0", color: "#fff" }}>📥 آخرین سفارش‌های ثبت‌شده از دایرکت</h4>
              <div style={{ fontSize: "12px", color: "#CBD5E1", lineHeight: "1.8" }}>
                <div>• پیج dr_zandi: سفارش ۲ باکس مزوتراپی MC (پیش‌فاکتور صادر شد)</div>
                <div>• مشتری خانگی (کرمان): ۱ عدد کرم سوآلین ویرا (ارسال با پیک شهری)</div>
              </div>
            </div>
            <div style={{ background: "#0F172A", padding: "16px", borderRadius: "8px" }}>
              <h4 style={{ margin: "0 0 10px 0", color: "#fff" }}>🎬 تقویم تولید محتوا و ریلز</h4>
              <div style={{ fontSize: "12px", color: "#CBD5E1", lineHeight: "1.8" }}>
                <div>• سناریو ویدیویی: نکات کلیدی ترمیم سوختگی با سوآلین ویرا</div>
                <div>• زمان انتشار: سه‌شنبه ساعت ۲۰:۰۰</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
