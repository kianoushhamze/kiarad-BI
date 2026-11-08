"use client";

import React, { useState, useEffect, useCallback } from "react";
import { secureApi, getSavedUser } from "../../lib/secure-api";
import { PortalShell } from "../../components/portal-shell";
import { IranDateInput } from "../../components/IranDateInput";
import { matchesSearch, uniqueSearchOptions } from "../../lib/text-search";

type Interaction = {
  id?: number; customer_name?: string; visitor_name?: string;
  interaction_type?: string; product_discussed?: string; notes?: string;
  next_date?: string; followup_time?: string; status?: string; is_due?: boolean;
};

type CatalogProduct = { id: number; name?: string | null };
const TYPES = ["ویزیت حضوری", "تماس تلفنی", "پیام و پیش‌فاکتور"];
const STATUSES = ["در انتظار تماس", "پیگیری شد", "نیاز به پیش‌فاکتور", "سفارش ثبت شد", "عدم تمایل فعلی"];

function CrmPageInner() {
  const listInit: Array<Interaction> = [];
  const [items, setItems] = useState<Array<Interaction>>(listInit);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [okMsg, setOkMsg] = useState("");

  const [custName, setCustName] = useState("");
  const [visName, setVisName] = useState("");
  const [interType, setInterType] = useState("ویزیت حضوری");
  const [product, setProduct] = useState("");
  const [catalogProducts, setCatalogProducts] = useState<CatalogProduct[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState("");
  const [followDate, setFollowDate] = useState("");
  const [followTime, setFollowTime] = useState("10:00");
  const [status, setStatus] = useState("در انتظار تماس");

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const data = await secureApi<Interaction[]>("/crm/interactions", { method: "GET" });
      const fresh: Array<Interaction> = [];
      if (Array.isArray(data)) data.forEach(function (x: Interaction) { fresh.push(x); });
      setItems(fresh);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "خطای ناشناخته";
      setItems([]);
      setError(msg.indexOf("Authentication") !== -1
        ? "ابتدا از صفحه ورود وارد سیستم شوید."
        : "دریافت یادآوری‌ها ناموفق بود: " + msg);
    } finally { setLoading(false); }
  }, []);

  useEffect(function () {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      const u = getSavedUser();
      if (u && u.full_name) setVisName(u.full_name);
      void load();
      void secureApi<{ items: CatalogProduct[] }>("/catalog/products")
        .then(data => { if (active) { setCatalogProducts(data.items ?? []); setCatalogError(""); } })
        .catch(() => { if (active) setCatalogError("فهرست کالاها دریافت نشد؛ نام کالا را آزادانه وارد کنید."); });
    });
    return () => { active = false; };
  }, [load]);

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
      setCustName(""); setNotes(""); setProduct("");
      setOkMsg("✓ یادآوری در دیتابیس ثبت شد.");
      await load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "خطای ناشناخته";
      setOkMsg("");
      setError("ثبت ناموفق بود: " + msg);
    } finally { setSaving(false); }
  };

  const moveCard = async function (item: Interaction, nextStatus: string) {
    if (!item.id || item.status === nextStatus) return;
    const before = items;
    setItems(items.map(function (entry) { return entry.id === item.id ? { ...entry, status: nextStatus } : entry; }));
    setError("");
    try {
      await secureApi("/crm/interactions/" + item.id + "/status", {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus })
      });
    } catch (err: unknown) {
      setItems(before);
      setError("تغییر مرحله ذخیره نشد: " + (err instanceof Error ? err.message : "خطای ناشناخته"));
    }
  };

  const todayCount = items.filter(function (i: Interaction) { return i.is_due; }).length;
  const productOptions = uniqueSearchOptions([...catalogProducts.map(p => p.name), ...items.map(item => item.product_discussed)])
    .filter(name => matchesSearch(product, name));
  const visibleItems = items.filter(item => matchesSearch(query, item.customer_name, item.visitor_name, item.product_discussed, item.notes));

  const inputStyle: React.CSSProperties = { width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "6px", fontSize: "13px", outline: "none" };
  const labelStyle: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" };

  return (
    <div className="kiarad-crm" style={{ minHeight: "100vh", background: "transparent", color: "#f0f3ff", direction: "rtl", padding: "24px 32px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#f0f3ff" }}>📞 مرکز پیگیری‌ها و یادآوری ویزیت (CRM)</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>ثبت و خواندن واقعی از دیتابیس — بدون داده نمایشی</p>
        </div>
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
        <div style={{ background: "#064E3B", border: "1px solid #12a57a", color: "#6EE7B7", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "14px" }}>{okMsg}</div>
      ) : null}

      <div className="kiarad-crm-content" style={{ display: "grid", gridTemplateColumns: "1.2fr 2fr", gap: "24px" }}>
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
                <label htmlFor="crm-discussed-product" style={labelStyle}>کالای بحث‌شده:</label>
                <input id="crm-discussed-product" list="crm-product-options" value={product} onChange={e => setProduct(e.target.value)} placeholder="بخشی از نام کالا یا متن دلخواه" maxLength={200} style={inputStyle}/>
                <datalist id="crm-product-options">{productOptions.map(name => <option key={name} value={name}/>)}</datalist>
                <div role="listbox" aria-label="پیشنهادهای کالای بحث‌شده" style={{ maxHeight: "120px", overflowY: "auto", marginTop: "6px" }}>
                  {productOptions.map(name => <button type="button" role="option" aria-selected={product === name} key={name} onClick={() => setProduct(name)} style={{ display: "block", width: "100%", textAlign: "right", background: "#111C35", border: "1px solid #334155", color: "#CBD5E1", padding: "6px", fontSize: "11px" }}>{name}</button>)}
                  {!productOptions.length && <p style={{ fontSize: "11px", color: "#94A3B8" }}>پیشنهاد مطابقی نیست؛ متن نوشته‌شده بدون تغییر قابل ثبت است.</p>}
                </div>
                <p style={{ fontSize: "11px", color: "#94A3B8", marginTop: "6px" }}>{catalogError || `پیشنهاد از ${catalogProducts.length.toLocaleString("fa-IR")} کالای واقعی؛ نوشتن متن دلخواه هم مجاز است.`}</p>
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
              <textarea required rows={2} value={notes} onChange={function(e){setNotes(e.target.value);}} style={{ resize: "none", ...inputStyle }} />
            </div>
            <div style={{ background: "#111C35", padding: "12px", borderRadius: "8px", border: "1px solid #334155" }}>
              <div style={{ fontSize: "12px", fontWeight: "bold", color: "#FBBF24", marginBottom: "8px" }}>📅 زمان‌بندی پیگیری:</div>
              <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: "10px" }}>
                <div>
                  <label style={labelStyle}>تاریخ پیگیری:</label>
                  <IranDateInput aria-label="تاریخ شمسی پیگیری" value={followDate} onChange={setFollowDate} className="rounded border px-3 py-2 text-white" style={{ ...inputStyle, background: "#0F1A30" }} />
                </div>
                <div>
                  <label style={labelStyle}>ساعت تماس:</label>
                  <input type="time" value={followTime} onChange={function(e){setFollowTime(e.target.value);}} style={{ ...inputStyle, background: "#0F1A30" }} />
                </div>
              </div>
            </div>
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#12a57a", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>
              {saving ? "در حال ثبت..." : "🔔 ثبت یادآوری در دیتابیس"}
            </button>
          </form>
        </div>

        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px", minWidth: 0 }}>
          <h3 style={{ margin: "0 0 6px 0", fontSize: "15px", color: "#F8FAFC" }}>📋 کانبان پیگیری‌ها</h3>
          <label style={labelStyle}>جست‌وجوی پیگیری با بخشی از نام مشتری، مسئول پیگیری، کالا یا گزارش<input aria-label="جست‌وجوی پیگیری بر اساس نام مشتری یا مسئول پیگیری" value={query} onChange={e => setQuery(e.target.value)} style={{ ...inputStyle, marginTop: "6px" }}/></label>
          <p style={{ margin: "0 0 16px", fontSize: "11px", color: "#64748B" }}>مرحلهٔ هر پرونده را از منوی روی کارت تغییر دهید؛ تغییر بلافاصله در دیتابیس ذخیره می‌شود.</p>
          {loading ? <div style={{ color: "#94A3B8", padding: "30px", textAlign: "center" }}>در حال دریافت...</div> : null}
          {!loading && items.length === 0 && !error ? (
            <div style={{ color: "#94A3B8", padding: "30px", textAlign: "center", background: "#111C35", borderRadius: "8px" }}>هنوز یادآوری‌ای ثبت نشده — اولین را از فرم ثبت کن.</div>
          ) : null}
          {!loading && items.length > 0 && visibleItems.length === 0 && <p role="status" style={{ color: "#94A3B8" }}>پیگیری مطابق جست‌وجو پیدا نشد.</p>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(230px, 1fr))", gap: "10px", overflowX: "auto", paddingBottom: "8px" }}>
            {STATUSES.map(function (columnStatus) {
              const cards = visibleItems.filter(function (entry) { return (entry.status || "در انتظار تماس") === columnStatus; });
              return <section key={columnStatus} style={{ background: "#091224", border: "1px solid #1E293B", borderRadius: "10px", padding: "10px", minHeight: "280px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", color: "#CBD5E1", fontSize: "11px", fontWeight: 800, marginBottom: "10px" }}><span>{columnStatus}</span><span style={{ color: "#818CF8" }}>{cards.length}</span></div>
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {cards.map(function (it: Interaction) {
                  const due = it.is_due;
                  return (
                <div key={it.id} style={{ background: "#111C35", border: due ? "1px solid #F59E0B" : "1px solid #1E293B", borderRadius: "8px", padding: "12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <div style={{ fontWeight: "bold", fontSize: "14px", color: "#38BDF8" }}>
                      {it.customer_name}
                      {due ? <span style={{ marginRight: "8px", fontSize: "11px", background: "#78350F", color: "#FDE68A", padding: "2px 8px", borderRadius: "4px" }}>⚠️ نوبت امروز</span> : null}
                    </div>
                    <span style={{ fontSize: "12px", color: "#FBBF24", fontWeight: "bold" }}>{it.followup_time ? "⏰ " + it.followup_time : ""}</span>
                  </div>
                  <p style={{ margin: "0 0 10px 0", fontSize: "13px", color: "#CBD5E1" }}>{it.notes}</p>
                  <div style={{ display: "flex", flexDirection: "column", fontSize: "10px", color: "#94A3B8", borderTop: "1px solid #1E293B", paddingTop: "8px", gap: "5px" }}>
                    <div>کالا: <strong style={{ color: "#fff" }}>{it.product_discussed}</strong></div>
                    <div>مسئول: <strong style={{ color: "#fff" }}>{it.visitor_name}</strong></div>
                    <div>پیگیری: <strong style={{ color: "#34D399" }}>{it.next_date || "بدون تاریخ"}</strong></div>
                    <select aria-label="تغییر مرحله" value={it.status || "در انتظار تماس"} onChange={function(e){moveCard(it, e.target.value);}} style={{ ...inputStyle, marginTop: "4px", fontSize: "10px", padding: "6px 8px" }}>{STATUSES.map(function(stage){return <option key={stage} value={stage}>{stage}</option>;})}</select>
                  </div>
                </div>
              );
                })}
                {!cards.length ? <div style={{ color: "#475569", fontSize: "10px", textAlign: "center", padding: "22px 6px" }}>بدون پرونده</div> : null}
                </div>
              </section>;
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CrmPage() {
  return <PortalShell title="CRM" eyebrow="مدیریت ارتباط با مشتری"><div className="kskin"><CrmPageInner /></div></PortalShell>;
}
