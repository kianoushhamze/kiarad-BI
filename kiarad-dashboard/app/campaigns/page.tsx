
"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { secureApi } from "../../lib/secure-api";

type Campaign = {
  id?: number; title?: string; description?: string;
  starts_at?: string; ends_at?: string;
  target_amount?: number; reward_type?: string; reward_value?: number; reward_note?: string;
  is_active?: boolean; achieved?: number; progress_percent?: number;
};

type LbRow = {
  rank?: number; name?: string; achieved?: number; invoices?: number;
};

export default function CampaignsPage() {
  const listInit: Array<Campaign> = new Array();
  const emptyList: Array<Campaign> = new Array();
  const lbInit: Array<LbRow> = new Array();
  const [campaigns, setCampaigns] = useState<Array<Campaign>>(listInit);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [okMsg, setOkMsg] = useState("");
  const [lbFor, setLbFor] = useState(0);
  const [lbRows, setLbRows] = useState<Array<LbRow>>(lbInit);

  const [cTitle, setCTitle] = useState("");
  const [cDesc, setCDesc] = useState("");
  const [cStart, setCStart] = useState("");
  const [cEnd, setCEnd] = useState("");
  const [cTarget, setCTarget] = useState("");
  const [cRewardType, setCRewardType] = useState("fixed");
  const [cRewardValue, setCRewardValue] = useState("");
  const [cNote, setCNote] = useState("");

  const setEmpty = function () { setCampaigns(emptyList); };

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const data = (await secureApi("/campaigns", { method: "GET" })) as any;
      const fresh: Array<Campaign> = new Array();
      if (Array.isArray(data)) data.forEach(function (c: Campaign) { fresh.push(c); });
      setCampaigns(fresh);
    } catch (err: any) {
      const msg = err && err.message ? String(err.message) : "خطای ناشناخته";
      setEmpty();
      setError(msg.indexOf("Authentication") !== -1
        ? "ابتدا از صفحه ورود وارد سیستم شوید."
        : "دریافت کمپین‌ها ناموفق بود: " + msg);
    } finally { setLoading(false); }
  }, new Array());

  useEffect(function () { load(); }, new Array(load));

  const money = function (v?: number) {
    if (!v) return "۰ ریال";
    return v.toLocaleString("fa-IR") + " ریال";
  };

  const submit = async function (e: React.FormEvent) {
    e.preventDefault();
    if (saving) return;
    if (!cTitle.trim() || !cStart || !cEnd) { setError("عنوان و بازه‌ی تاریخ الزامی است."); return; }
    setSaving(true); setOkMsg("");
    try {
      await secureApi("/campaigns", {
        method: "POST",
        body: JSON.stringify({
          title: cTitle, description: cDesc, starts_at: cStart, ends_at: cEnd,
          target_amount: Number(cTarget || 0), reward_type: cRewardType,
          reward_value: Number(cRewardValue || 0), reward_note: cNote
        })
      });
      setCTitle(""); setCDesc(""); setCTarget(""); setCRewardValue(""); setCNote("");
      setOkMsg("✓ کمپین در دیتابیس ساخته شد.");
      await load();
    } catch (err: any) {
      const msg = err && err.message ? err.message : "خطا";
      setOkMsg("");
      setError("ساخت کمپین ناموفق بود: " + msg);
    } finally { setSaving(false); }
  };

  const openLb = async function (id?: number) {
    if (!id) return;
    if (lbFor === id) { setLbFor(0); return; }
    try {
      const data = (await secureApi("/campaigns/leaderboard?campaign_id=" + id, { method: "GET" })) as any;
      const fresh: Array<LbRow> = new Array();
      const raw = data && data.leaderboard;
      if (Array.isArray(raw)) raw.forEach(function (r: LbRow) { fresh.push(r); });
      setLbRows(fresh);
      setLbFor(id);
    } catch (err: any) {
      setError("دریافت رتبه‌بندی ناموفق بود: " + (err && err.message ? err.message : "خطا"));
    }
  };

  const closeCamp = async function (id?: number) {
    if (!id || saving) return;
    setSaving(true);
    try {
      await secureApi("/campaigns/close", {
        method: "POST",
        body: JSON.stringify({ campaign_id: id })
      });
      setOkMsg("✓ کمپین بسته شد.");
      await load();
    } catch (err: any) {
      setError("بستن کمپین ناموفق بود: " + (err && err.message ? err.message : "خطا"));
    } finally { setSaving(false); }
  };

  const is: React.CSSProperties = { width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "8px", fontSize: "13px", outline: "none" };
  const ls: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" };
  const card: React.CSSProperties = { background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" };

  return (
    <div dir="rtl" style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>🎯 کمپین‌های فروش و پاداش</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>پیشرفت زنده از فروش واقعی — بدون داده نمایشی</p>
        </div>
        <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold" }}>← داشبورد اصلی</Link>
      </div>

      {error ? <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>⚠️ {error} <button type="button" onClick={function(){load();}} style={{ marginRight: "8px", background: "#7F1D1D", color: "#FCA5A5", border: "none", padding: "3px 12px", borderRadius: "6px", cursor: "pointer" }}>تلاش مجدد</button></div> : null}
      {okMsg ? <div style={{ background: "#064E3B", border: "1px solid #10B981", color: "#6EE7B7", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>{okMsg}</div> : null}

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 2fr", gap: "24px" }}>
        <div style={card}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>➕ ساخت کمپین جدید</h3>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div><label style={ls}>عنوان کمپین:</label>
              <input type="text" required value={cTitle} onChange={function(e){setCTitle(e.target.value);}} placeholder="مثال: مهرماه سوآلین ویرا" style={is} /></div>
            <div><label style={ls}>توضیح:</label>
              <input type="text" value={cDesc} onChange={function(e){setCDesc(e.target.value);}} style={is} /></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div><label style={ls}>از تاریخ:</label>
                <input type="date" required value={cStart} onChange={function(e){setCStart(e.target.value);}} style={is} /></div>
              <div><label style={ls}>تا تاریخ:</label>
                <input type="date" required value={cEnd} onChange={function(e){setCEnd(e.target.value);}} style={is} /></div>
            </div>
            <div><label style={ls}>هدف فروش در بازه (ریال):</label>
              <input type="number" min="0" required value={cTarget} onChange={function(e){setCTarget(e.target.value);}} style={is} /></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div><label style={ls}>نوع پاداش:</label>
                <select value={cRewardType} onChange={function(e){setCRewardType(e.target.value);}} style={is}>
                  <option value="fixed">مبلغ ثابت (ریال)</option>
                  <option value="percent">درصد از فروش</option>
                </select></div>
              <div><label style={ls}>مقدار پاداش:</label>
                <input type="number" min="0" value={cRewardValue} onChange={function(e){setCRewardValue(e.target.value);}} style={is} /></div>
            </div>
            <div><label style={ls}>توضیح پاداش:</label>
              <input type="text" value={cNote} onChange={function(e){setCNote(e.target.value);}} style={is} /></div>
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#10B981", color: "#fff", border: "none", padding: "10px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>
              {saving ? "در حال ثبت..." : "🎯 ساخت کمپین در دیتابیس"}
            </button>
          </form>
        </div>

        <div>
          {loading ? <div style={{ color: "#94A3B8", padding: "40px", textAlign: "center", ...card }}>در حال دریافت کمپین‌ها...</div> : null}
          {!loading && campaigns.length === 0 && !error ? (
            <div style={{ color: "#94A3B8", padding: "40px", textAlign: "center", ...card }}>هنوز کمپینی ساخته نشده — اولین را از فرم بساز.</div>
          ) : null}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {campaigns.map(function (c: Campaign) {
              const p = c.progress_percent || 0;
              const w = Math.min(p, 100);
              const active = c.is_active === true;
              return (
                <div key={c.id} style={card}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <div style={{ fontWeight: "bold", fontSize: "16px" }}>{c.title}
                      <span style={{ marginRight: "10px", fontSize: "11px", padding: "3px 10px", borderRadius: "12px", background: active ? "#065F46" : "#1E293B", color: active ? "#6EE7B7" : "#94A3B8" }}>{active ? "🟢 فعال" : "🔒 بسته"}</span>
                    </div>
                    <div style={{ fontSize: "12px", color: "#94A3B8" }}>{c.starts_at} ← {c.ends_at}</div>
                  </div>
                  {c.description ? <div style={{ fontSize: "12px", color: "#94A3B8", marginBottom: "10px" }}>{c.description}</div> : null}
                  <div style={{ width: "100%", background: "#1E293B", borderRadius: "6px", height: "10px", overflow: "hidden", marginBottom: "6px" }}>
                    <div style={{ width: w + "%", background: "linear-gradient(90deg, #3B82F6, #8B5CF6)", height: "100%", borderRadius: "6px" }} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "12px" }}>
                    <div>پیشرفت: <strong style={{ color: "#38BDF8" }}>{p}٪</strong></div>
                    <div>محقق‌شده: <strong style={{ color: "#34D399" }}>{money(c.achieved)}</strong> از {money(c.target_amount)}</div>
                    <div>پاداش: <strong style={{ color: "#FBBF24" }}>{c.reward_type === "percent" ? (c.reward_value || 0) + "٪" : money(c.reward_value)}</strong></div>
                  </div>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <button type="button" onClick={function(){openLb(c.id);}} style={{ background: "#1E293B", border: "1px solid #334155", color: "#38BDF8", padding: "6px 14px", borderRadius: "8px", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}>
                      {lbFor === c.id ? "بستن رتبه‌بندی" : "🏆 رتبه‌بندی"}
                    </button>
                    {active ? (
                      <button type="button" onClick={function(){closeCamp(c.id);}} disabled={saving} style={{ background: "#7F1D1D", border: "none", color: "#FCA5A5", padding: "6px 14px", borderRadius: "8px", cursor: "pointer", fontSize: "12px" }}>بستن کمپین</button>
                    ) : null}
                  </div>
                  {lbFor === c.id ? (
                    <div style={{ marginTop: "12px", background: "#111C35", borderRadius: "8px", padding: "12px", border: "1px solid #1E293B" }}>
                      {lbRows.length === 0 ? <div style={{ fontSize: "12px", color: "#94A3B8" }}>رکوردی نیست.</div> : null}
                      {lbRows.map(function (r: LbRow, idx) {
                        return (
                          <div key={idx} style={{ display: "flex", justifyContent: "space-between", padding: "6px 4px", fontSize: "13px", borderBottom: "1px solid #1E293B" }}>
                            <div>{r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : "▫️"} {r.name}</div>
                            <div><strong style={{ color: "#34D399" }}>{money(r.achieved)}</strong> <span style={{ color: "#94A3B8", fontSize: "11px" }}>({r.invoices || 0} فاکتور)</span></div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
