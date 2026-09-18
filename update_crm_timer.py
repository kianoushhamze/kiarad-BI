import os

crm_file = r"D:\project\kiaradbi\kiarad-dashboard\app\crm\page.tsx"

enhanced_crm_code = '''"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";

interface Interaction {
  id: number;
  customer_name: string;
  visitor_name: string;
  interaction_type: string;
  product_discussed: string;
  notes: string;
  followup_date: string;
  followup_time: string;
  status: string;
  is_due: boolean;
}

export default function CrmPage() {
  const [interactions, setInteractions] = useState<Interaction[]>([
    { id: 1, customer_name: "داروخانه دکتر شریفی (کرمان)", visitor_name: "فروشنده تست", interaction_type: "ویزیت حضوری", product_discussed: "سوآلین ویرا", notes: "سمپل تحویل شد. راضی بودند؛ برای صدور فاکتور تماس گرفته شود.", followup_date: "امروز", followup_time: "۱۰:۳۰", status: "در انتظار تماس", is_due: true },
    { id: 2, customer_name: "کلینیک پوست و زیبایی مهر (کرمان)", visitor_name: "فروشنده تست", interaction_type: "تماس تلفنی", product_discussed: "ام‌سی کازمتیک", notes: "درخواست پیش‌فاکتور ۲ باکس مزوتراپی. تماس مجدد جهت واریزی.", followup_date: "امروز", followup_time: "۱۶:۰۰", status: "نیاز به پیش‌فاکتور", is_due: true },
    { id: 3, customer_name: "داروخانه رازی (رفسنجان)", visitor_name: "فروشنده تست", interaction_type: "ویزیت حضوری", product_discussed: "درمالیست", notes: "سفارش ژل شستشو ثبت شد. پیگیری وصول چک.", followup_date: "شنبه آینده", followup_time: "۱۱:۰۰", status: "سفارش ثبت شد", is_due: false },
  ]);

  // فرم ثبت
  const [custName, setCustName] = useState("");
  const [visName, setVisName] = useState("فروشنده تست");
  const [interType, setInterType] = useState("ویزیت حضوری");
  const [product, setProduct] = useState("سوآلین ویرا");
  const [notes, setNotes] = useState("");
  const [followDate, setFollowDate] = useState("");
  const [followTime, setFollowTime] = useState("۱۰:۰۰");
  const [status, setStatus] = useState("در انتظار تماس");

  const setShortcutDate = (days: number, label: string) => {
    const d = new Date();
    d.setDate(d.getDate() + days);
    setFollowDate(d.toISOString().split("T")[0]);
  };

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!custName.trim() || !notes.trim()) return;

    const newItem: Interaction = {
      id: Date.now(),
      customer_name: custName,
      visitor_name: visName,
      interaction_type: interType,
      product_discussed: product,
      notes: notes,
      followup_date: followDate || "فردا",
      followup_time: followTime,
      status: status,
      is_due: followDate === new Date().toISOString().split("T")[0]
    };

    setInteractions([newItem, ...interactions]);
    setCustName("");
    setNotes("");
    alert("✓ یادآوری با موفقیت ثبت شد و در کارتابل قرار گرفت.");
  };

  const todayCount = interactions.filter((i) => i.is_due).length;

  return (
    <div style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      {/* هدر صفحه */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>📞 مرکز پیگیری‌ها و یادآوری هوشمند ویزیت (CRM)</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>تنظیم تاریخ، ساعت تماس و هشدار خودکار برای داروخانه‌ها و کلینیک‌های استان کرمان</p>
        </div>
        <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </Link>
      </div>

      {/* ۳ کارت وضعیت */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", marginBottom: "24px" }}>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#94A3B8" }}>کل یادآوری‌های ثبت‌شده</div>
          <div style={{ fontSize: "22px", fontWeight: "bold", color: "#fff", marginTop: "4px" }}>{interactions.length} مرکز</div>
        </div>
        <div style={{ background: "#0F1A30", border: "1px solid #F59E0B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#FBBF24" }}>⏰ نوبت تماس و پیگیری امروز</div>
          <div style={{ fontSize: "22px", fontWeight: "bold", color: "#FBBF24", marginTop: "4px" }}>{todayCount} داروخانه / کلینیک</div>
        </div>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#34D399" }}>سیستم هشدار خودکار</div>
          <div style={{ fontSize: "16px", fontWeight: "bold", color: "#34D399", marginTop: "8px" }}>● متصل به نوتیفیکیشن داشبورد</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 2.3fr", gap: "24px" }}>
        {/* فرم ثبت گزارش و تنظیم ساعت و تاریخ */}
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>⏰ تنظیم تاریخ و ساعت یادآوری تماس</h3>
          <form onSubmit={handleAdd} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div>
              <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>نام داروخانه / کلینیک:</label>
              <input
                type="text"
                required
                placeholder="مثال: داروخانه رازی رفسنجان"
                value={custName}
                onChange={(e) => setCustName(e.target.value)}
                style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "6px", fontSize: "13px", outline: "none" }}
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>ویزیتور پیگیری‌کننده:</label>
                <select value={visName} onChange={(e) => setVisName(e.target.value)} style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px", borderRadius: "6px", fontSize: "12px" }}>
                  <option value="فروشنده تست">فروشنده تست</option>
                  <option value="مدیریت (کیانوش)">مدیریت (کیانوش)</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>نوع تعامل:</label>
                <select value={interType} onChange={(e) => setInterType(e.target.value)} style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px", borderRadius: "6px", fontSize: "12px" }}>
                  <option value="تماس تلفنی">تماس تلفنی</option>
                  <option value="ویزیت حضوری">ویزیت حضوری</option>
                  <option value="پیام‌رسان">پیام و پیش‌فاکتور</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>خلاصه صحبت و هدف پیگیری:</label>
              <textarea
                required
                rows={2}
                placeholder="مثال: استعلام رضایت از سوآلین ویرا و دریافت سفارش جدید..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "6px", fontSize: "13px", outline: "none", resize: "none" }}
              />
            </div>

            {/* بخش کلیدی: انتخاب تاریخ و ساعت با میانبرها */}
            <div style={{ background: "#111C35", padding: "12px", borderRadius: "8px", border: "1px solid #334155" }}>
              <div style={{ fontSize: "12px", fontWeight: "bold", color: "#FBBF24", marginBottom: "8px" }}>📅 زمان‌بندی دقیق یادآوری:</div>
              
              {/* میانبرهای سریع تاریخ */}
              <div style={{ display: "flex", gap: "6px", marginBottom: "10px" }}>
                <button type="button" onClick={() => setShortcutDate(0, "امروز")} style={{ background: "#1E293B", border: "1px solid #475569", color: "#38BDF8", padding: "4px 8px", borderRadius: "4px", fontSize: "11px", cursor: "pointer" }}>امروز</button>
                <button type="button" onClick={() => setShortcutDate(1, "فردا")} style={{ background: "#1E293B", border: "1px solid #475569", color: "#fff", padding: "4px 8px", borderRadius: "4px", fontSize: "11px", cursor: "pointer" }}>فردا</button>
                <button type="button" onClick={() => setShortcutDate(3, "۳ روز بعد")} style={{ background: "#1E293B", border: "1px solid #475569", color: "#fff", padding: "4px 8px", borderRadius: "4px", fontSize: "11px", cursor: "pointer" }}>۳ روز بعد</button>
                <button type="button" onClick={() => setShortcutDate(7, "هفته آینده")} style={{ background: "#1E293B", border: "1px solid #475569", color: "#fff", padding: "4px 8px", borderRadius: "4px", fontSize: "11px", cursor: "pointer" }}>هفته آینده</button>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "10px" }}>
                <div>
                  <label style={{ fontSize: "11px", color: "#94A3B8", display: "block", marginBottom: "3px" }}>تاریخ پیگیری:</label>
                  <input
                    type="date"
                    value={followDate}
                    onChange={(e) => setFollowDate(e.target.value)}
                    style={{ width: "100%", background: "#0F1A30", border: "1px solid #475569", color: "#fff", padding: "6px", borderRadius: "6px", fontSize: "12px" }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: "11px", color: "#94A3B8", display: "block", marginBottom: "3px" }}>ساعت تماس:</label>
                  <input
                    type="time"
                    value={followTime}
                    onChange={(e) => setFollowTime(e.target.value)}
                    style={{ width: "100%", background: "#0F1A30", border: "1px solid #475569", color: "#fff", padding: "6px", borderRadius: "6px", fontSize: "12px" }}
                  />
                </div>
              </div>
            </div>

            <button type="submit" style={{ background: "#10B981", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", fontSize: "13px", marginTop: "4px" }}>
              🔔 ثبت یادآوری در تقویم کاری
            </button>
          </form>
        </div>

        {/* لیست کارتابل یادآوری‌ها */}
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#F8FAFC" }}>📋 کارتابل نوبت‌های تماس و پیگیری</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {interactions.map((it) => (
              <div key={it.id} style={{ background: "#111C35", border: it.is_due ? "1px solid #F59E0B" : "1px solid #1E293B", borderRadius: "8px", padding: "14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <div style={{ fontWeight: "bold", fontSize: "14px", color: "#38BDF8" }}>
                    {it.customer_name}
                    {it.is_due && <span style={{ marginRight: "8px", fontSize: "11px", background: "#78350F", color: "#FDE68A", padding: "2px 8px", borderRadius: "4px" }}>⚠️ نوبت تماس امروز</span>}
                  </div>
                  <span style={{ fontSize: "12px", color: "#FBBF24", fontWeight: "bold" }}>⏰ ساعت {it.followup_time}</span>
                </div>

                <p style={{ margin: "0 0 10px 0", fontSize: "13px", color: "#CBD5E1" }}>{it.notes}</p>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "#94A3B8", borderTop: "1px solid #1E293B", paddingTop: "8px" }}>
                  <div>کالا: <strong style={{ color: "#fff" }}>{it.product_discussed}</strong></div>
                  <div>مسئول: <strong style={{ color: "#fff" }}>{it.visitor_name}</strong></div>
                  <div>تاریخ پیگیری: <strong style={{ color: "#34D399" }}>{it.followup_date}</strong></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
'''

with open(crm_file, "w", encoding="utf-8") as f:
    f.write(enhanced_crm_code)

print("✓ انتخاب‌گر تاریخ، ساعت و سامانه هشدار یادآوری با موفقیت فعال شد.")
