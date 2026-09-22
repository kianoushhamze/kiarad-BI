"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { secureApi, getSavedUser } from "../../lib/secure-api";

type Interaction = {
  id?: number; customer_name?: string; visitor_name?: string;
  interaction_type?: string; product_discussed?: string; notes?: string;
  next_date?: string; followup_time?: string; status?: string; is_due?: boolean;
};

const PRODUCTS = new Array("سوآلین ویرا", "درمالیست", "ام‌سی کازمتیک", "توتال درم");
const TYPES = new Array("ویزیت حضوری", "تماس تلفنی", "پیام و پیش‌فاکتور");
const STATUSES = new Array("در انتظار تماس", "پیگیری شد", "سفارش ثبت شد");

export default function CrmPage() {
  const listInit: Array<Interaction> = new Array();
  const emptyList: Array<Interaction> = new Array();
  const [items, setItems] = useState<Array<Interaction>>(listInit);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [okMsg, setOkMsg] = useState("");

  const [custName, setCustName] = useState("");
  const [visName, setVisName] = useState("");
  const [interType, setInterType] = useState("ویزیت حضوری");
  const [product, setProduct] = useState("سوآلین ویرا");
  const [notes, setNotes] = useState("");
  const [followDate, setFollowDate] = useState("");
  const [followTime, setFollowTime] = useState("10:00");
  const [status, setStatus] = useState("در انتظار تماس");

  const setItemsEmpty = function () { setItems(emptyList); };

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const data = (await secureApi("/crm/interactions", { method: "GET" })) as any;
      const fresh: Array<Interaction> = new Array();
      if (Array.isArray(data)) data.forEach(function (x: Interaction) { fresh.push(x); });
      setItems(fresh);
    } catch (err: any) {
      const msg = err && err.message ? String(err.message) : "خطای ناشناخته";
      setItemsEmpty();
      setError(msg.indexOf("Authentication") !== -1
        ? "ابتدا از صفحه ورود وارد سیستم شوید."
        : "دریافت یادآوری‌ها ناموفق بود: " + msg);
    } finally { setLoading(false); }
  }, new Array());

  useEffect(function () {
    const u = getSavedUser();
    if (u && u.full_name) setVisName(u.full_name);
    load();
  }, new Array(load));

  const submit = async function (e: React.FormEvent) {
    e.preventDefault();
    if (!custName.trim() || !notes.trim() || saving) return;
    setSaving(true); setOkMsg("");
    try {
      await secureApi("/crm/interactions", {
        method: "POST",
        body: JSON.stringify({
          customer_name: custName, visitor_name: visName || "مدیریت",
          interaction_type: interType, product_discussed: product,
          notes: notes, status: status,
          next_followup_date: followDate || null,
          followup_time: followTime || null
        })
      });
      setCustName(""); setNotes("");
      setOkMsg("✓ یادآوری در دیتابیس ثبت شد.");
      await load();
    } catch (err: any) {
      const msg = err && err.message ? String(err.message) : "خطای ناشناخته";
      setOkMsg("");
      setError("ثبت ناموفق بود: " + msg);
    } finally { setSaving(false); }
  };

  const todayCount = items.filter(function (i: Interaction) { return i.is_due; }).length;

  const inputStyle: React.CSSProperties = { width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "6px", fontSize: "13px", outline: "none" };
  const labelStyle: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" };

  return (
    <div style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>📞 مرکز پیگیری‌ها و یادآوری ویزیت (CRM)</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>ثبت و خواندن واقعی از دیتابیس — بدون داده نمایشی</p>
        </div>
        <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold" }}>← داشبورد اصلی</Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px", marginBottom: "24px" }}>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#94A3B8" }}>کل یادآوری‌های ثبت‌شده</div>
          <div style={{ fontSize: "22px", fontWeight: "bold", marginTop: "4px" }}>{items.length} مرکز</div>
        </div>
        <div style={{ background: "#0F1A30", border: "1px solid #F59E0B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#FBBF24" }}>⏰ نوبت تماس امروز</div>
          <div style={{ fontSize: "22px", fontWeight: "bold", color: "#FBBF24", marginTop: "4px" }}>{todayCount} مورد</div>
        </div>
      </div>

      {error ? (
        <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "14px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "14px" }}>⚠️ {error} <button type="button" onClick={function(){load();}} style={{ marginRight: "10px", background: "#7F1D1D", color: "#FCA5A5", border: "none", padding: "4px 12px", borderRadius: "6px", cursor: "pointer" }}>تلاش مجدد</button></div>
      ) : null}
      {okMsg ? (
        <div style={{ background: "#064E3B", border: "1px solid #10B981", color: "#6EE7B7", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "14px" }}>{okMsg}</div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 2fr", gap: "24px" }}>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>📝 ثبت یادآوری جدید</h3>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div>
              <label style={labelStyle}>نام داروخانه / کلینیک:</label>
              <input type="text" required value={custName} onChange={function(e){setCustName(e.target.value);}} placeholder="مثال: داروخانه رازی رفسنجان" style={inputStyle} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label style={labelStyle}>مسئول پیگیری:</label>
                <input type="text" value={visName} onChange={function(e){setVisName(e.target.value);}} style={inputStyle} />
              </div>
              <div>
                <label style={labelStyle}>نوع تعامل:</label>
                <select value={interType} onChange={function(e){setInterType(e.target.value);}} style={inputStyle}>
                  {TYPES.map(function(t: string, i: number){ return <option key={i} value={t}>{t}</option>; })}
                </select>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label style={labelStyle}>کالای بحث‌شده:</label>
                <select value={product} onChange={function(e){setProduct(e.target.value);}} style={inputStyle}>
                  {PRODUCTS.map(function(t: string, i: number){ return <option key={i} value={t}>{t}</option>; })}
                </select>
              </div>
              <div>
                <label style={labelStyle}>وضعیت:</label>
                <select value={status} onChange={function(e){setStatus(e.target.value);}} style={inputStyle}>
                  {STATUSES.map(function(t: string, i: number){ return <option key={i} value={t}>{t}</option>; })}
                </select>
              </div>
            </div>
            <div>
              <label style={labelStyle}>خلاصه گفتگو و هدف پیگیری:</label>
              <textarea required rows={2} value={notes} onChange={function(e){setNotes(e.target.value);}} style={{ resize: "none" as any, ...inputStyle }} />
            </div>
            <div style={{ background: "#111C35", padding: "12px", borderRadius: "8px", border: "1px solid #334155" }}>
              <div style={{ fontSize: "12px", fontWeight: "bold", color: "#FBBF24", marginBottom: "8px" }}>📅 زمان‌بندی پیگیری:</div>
              <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "10px" }}>
                <div>
                  <label style={labelStyle}>تاریخ پیگیری:</label>
                  <input type="date" value={followDate} onChange={function(e){setFollowDate(e.target.value);}} style={{ ...inputStyle, background: "#0F1A30" }} />
                </div>
                <div>
                  <label style={labelStyle}>ساعت تماس:</label>
                  <input type="time" value={followTime} onChange={function(e){setFollowTime(e.target.value);}} style={{ ...inputStyle, background: "#0F1A30" }} />
                </div>
              </div>
            </div>
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#10B981", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>
              {saving ? "در حال ثبت..." : "🔔 ثبت یادآوری در دیتابیس"}
            </button>
          </form>
        </div>

        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#F8FAFC" }}>📋 کارتابل یادآوری‌ها (زنده)</h3>
          {loading ? <div style={{ color: "#94A3B8", padding: "30px", textAlign: "center" }}>در حال دریافت...</div> : null}
          {!loading && items.length === 0 && !error ? (
            <div style={{ color: "#94A3B8", padding: "30px", textAlign: "center", background: "#111C35", borderRadius: "8px" }}>هنوز یادآوری‌ای ثبت نشده — اولین را از فرم ثبت کن.</div>
          ) : null}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {items.map(function (it: Interaction) {
              const due = it.is_due;
              return (
                <div key={it.id} style={{ background: "#111C35", border: due ? "1px solid #F59E0B" : "1px solid #1E293B", borderRadius: "8px", padding: "14px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <div style={{ fontWeight: "bold", fontSize: "14px", color: "#38BDF8" }}>
                      {it.customer_name}
                      {due ? <span style={{ marginRight: "8px", fontSize: "11px", background: "#78350F", color: "#FDE68A", padding: "2px 8px", borderRadius: "4px" }}>⚠️ نوبت امروز</span> : null}
                    </div>
                    <span style={{ fontSize: "12px", color: "#FBBF24", fontWeight: "bold" }}>{it.followup_time ? "⏰ " + it.followup_time : ""}</span>
                  </div>
                  <p style={{ margin: "0 0 10px 0", fontSize: "13px", color: "#CBD5E1" }}>{it.notes}</p>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94A3B8", borderTop: "1px solid #1E293B", paddingTop: "8px", flexWrap: "wrap", gap: "6px" }}>
                    <div>کالا: <strong style={{ color: "#fff" }}>{it.product_discussed}</strong></div>
                    <div>مسئول: <strong style={{ color: "#fff" }}>{it.visitor_name}</strong></div>
                    <div>پیگیری: <strong style={{ color: "#34D399" }}>{it.next_date || "بدون تاریخ"}</strong></div>
                    <div>وضعیت: <strong style={{ color: "#fff" }}>{it.status}</strong></div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
