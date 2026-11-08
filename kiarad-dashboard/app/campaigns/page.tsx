
"use client";

import React, { useState, useEffect, useCallback } from "react";
import { secureApi } from "../../lib/secure-api";
import { PortalShell } from "../../components/portal-shell";
import { IranDateInput } from "../../components/IranDateInput";

type Campaign = {
  id?: number; title?: string; description?: string;
  starts_at?: string; ends_at?: string;
  target_amount?: number; reward_type?: string; reward_value?: number; reward_note?: string;
  is_active?: boolean; achieved?: number; progress_percent?: number;
};

type LbRow = {
  rank?: number; name?: string; achieved?: number; invoices?: number;
};

type AiProposal = {
  title?: string; description?: string;
  starts_at?: string; ends_at?: string;
  target_amount?: number; reward_type?: string; reward_value?: number; reward_note?: string;
};

function CampaignsPageInner() {
  const listInit: Array<Campaign> = [];
  const lbInit: Array<LbRow> = [];
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

  const aiPropInit: AiProposal = new Object();
  const [aiSuggId, setAiSuggId] = useState(0);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiProp, setAiProp] = useState<AiProposal>(aiPropInit);
  const [aiRationale, setAiRationale] = useState("");
  const [aiMsg, setAiMsg] = useState("");

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const data = await secureApi<Campaign[]>("/campaigns", { method: "GET" });
      const fresh: Array<Campaign> = [];
      if (Array.isArray(data)) data.forEach(function (c: Campaign) { fresh.push(c); });
      setCampaigns(fresh);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "خطای ناشناخته";
      setCampaigns([]);
      setError(msg.indexOf("Authentication") !== -1
        ? "ابتدا از صفحه ورود وارد سیستم شوید."
        : "دریافت کمپین‌ها ناموفق بود: " + msg);
    } finally { setLoading(false); }
  }, []);

  useEffect(function () {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  const money = function (v?: number) {
    if (!v) return "۰ ریال";
    return v.toLocaleString("fa-IR") + " ریال";
  };

  const fetchAiSuggestion = async function () {
    if (aiBusy) return;
    setAiBusy(true); setAiMsg(""); setAiProp(new Object()); setAiRationale(""); setAiSuggId(0);
    try {
      const data = await secureApi<{ proposal?: AiProposal; suggestion_id?: number; rationale?: string }>("/campaigns/ai/suggest", { method: "POST", body: "{}" });
      const prop = data.proposal || {};
      setAiProp(prop);
      setAiSuggId((data && data.suggestion_id) || 0);
      setAiRationale((data && data.rationale) || "");
      setAiMsg("پیشنهاد آماده شد — بررسی کن و تأیید یا رد کن.");
    } catch (err: unknown) {
      setAiMsg("پیشنهاد ناموفق: " + (err instanceof Error ? err.message : "خطا"));
    } finally { setAiBusy(false); }
  };

  const decideAi = async function (suggId: number, action: string) {
    if (aiBusy) return;
    setAiBusy(true);
    try {
      await secureApi("/campaigns/ai/decide", {
        method: "POST",
        body: JSON.stringify({ suggestion_id: suggId, action: action })
      });
      setAiMsg(action === "approve" ? "✓ کمپین از پیشنهاد هوشمند ساخته شد." : "پیشنهاد رد شد.");
      setAiProp(new Object()); setAiRationale(""); setAiSuggId(0);
      await load();
    } catch (err: unknown) {
      setAiMsg("تصمیم ناموفق: " + (err instanceof Error ? err.message : "خطا"));
    } finally { setAiBusy(false); }
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
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "خطا";
      setOkMsg("");
      setError("ساخت کمپین ناموفق بود: " + msg);
    } finally { setSaving(false); }
  };

  const openLb = async function (id?: number) {
    if (!id) return;
    if (lbFor === id) { setLbFor(0); return; }
    try {
      const data = await secureApi<{ leaderboard?: LbRow[] }>("/campaigns/leaderboard?campaign_id=" + id, { method: "GET" });
      const fresh: Array<LbRow> = [];
      const raw = data && data.leaderboard;
      if (Array.isArray(raw)) raw.forEach(function (r: LbRow) { fresh.push(r); });
      setLbRows(fresh);
      setLbFor(id);
    } catch (err: unknown) {
      setError("دریافت رتبه‌بندی ناموفق بود: " + (err instanceof Error ? err.message : "خطا"));
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
    } catch (err: unknown) {
      setError("بستن کمپین ناموفق بود: " + (err instanceof Error ? err.message : "خطا"));
    } finally { setSaving(false); }
  };

  const is: React.CSSProperties = { width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "8px", fontSize: "13px", outline: "none" };
  const ls: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" };
  const card: React.CSSProperties = { background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" };

  return (
    <div dir="rtl" className="kiarad-campaigns" style={{ minHeight: "auto", background: "transparent", color: "#f0f3ff", padding: "0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#f0f3ff" }}>🎯 کمپین‌های فروش و پاداش</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>پیشرفت زنده از فروش واقعی — تصمیم هوشمند با تأیید انسانی</p>
        </div>
      </div>

      {error ? <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>⚠️ {error} <button type="button" onClick={function(){load();}} style={{ marginRight: "8px", background: "#7F1D1D", color: "#FCA5A5", border: "none", padding: "3px 12px", borderRadius: "6px", cursor: "pointer" }}>تلاش مجدد</button></div> : null}
      {okMsg ? <div style={{ background: "#064E3B", border: "1px solid #12a57a", color: "#6EE7B7", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>{okMsg}</div> : null}

      <div style={Object.assign({}, card, { marginBottom: "24px", borderColor: "#334155" })}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
          <h3 style={{ margin: 0, fontSize: "15px", color: "#A78BFA" }}>🤖 دستیار هوشمند — پیشنهاد کمپین از داده‌های زنده</h3>
          <button type="button" onClick={fetchAiSuggestion} disabled={aiBusy} style={{ background: aiBusy ? "#4C1D95" : "#7C3AED", color: "#fff", border: "none", padding: "8px 18px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>
            {aiBusy ? "⏳ در حال تحلیل داده‌ها..." : "✨ پیشنهاد بگیر"}
          </button>
        </div>
        <p style={{ margin: "0 0 12px 0", fontSize: "12px", color: "#94A3B8" }}>تحلیل فروش ۳۰ روزه، تفکیک ویزیتور و شهرها، روند ماهانه — هدف پیشنهادی همیشه بین ۱.۱ تا ۱.۵ برابر فروش واقعی مهار می‌شود. هیچ کمپینی بدون تأیید تو ساخته نمی‌شود.</p>
        {aiMsg ? <div style={{ fontSize: "12px", color: "#C4B5FD", marginBottom: "10px" }}>{aiMsg}</div> : null}
        {aiProp && aiProp.title ? (
          <div style={{ background: "#111C35", borderRadius: "10px", padding: "16px", border: "1px solid #4C1D95" }}>
            <div style={{ fontWeight: "bold", fontSize: "15px", marginBottom: "6px" }}>💡 {aiProp.title}</div>
            {aiProp.description ? <div style={{ fontSize: "12px", color: "#94A3B8", marginBottom: "8px" }}>{aiProp.description}</div> : null}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "18px", fontSize: "12px", marginBottom: "10px" }}>
              <div>بازه: <strong>{aiProp.starts_at} ← {aiProp.ends_at}</strong></div>
              <div>هدف: <strong style={{ color: "#34D399" }}>{money(aiProp.target_amount)}</strong></div>
              <div>پاداش: <strong style={{ color: "#FBBF24" }}>{aiProp.reward_type === "percent" ? (aiProp.reward_value || 0) + "٪" : money(aiProp.reward_value)}</strong></div>
              {aiProp.reward_note ? <div style={{ color: "#94A3B8" }}>({aiProp.reward_note})</div> : null}
            </div>
            {aiRationale ? (
              <div style={{ background: "#090E1A", borderRadius: "8px", padding: "12px", fontSize: "12px", color: "#CBD5E1", marginBottom: "12px", lineHeight: "1.9" }}>
                <strong style={{ color: "#A78BFA" }}>تحلیل دستیار: </strong>{aiRationale}
              </div>
            ) : null}
            <div style={{ display: "flex", gap: "8px" }}>
              <button type="button" onClick={function(){ if (aiSuggId) { decideAi(aiSuggId, "approve"); } }} disabled={aiBusy} style={{ background: "#12a57a", color: "#fff", border: "none", padding: "7px 18px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "12px" }}>✅ تأیید و ساخت کمپین</button>
              <button type="button" onClick={function(){ if (aiSuggId) { decideAi(aiSuggId, "reject"); } }} disabled={aiBusy} style={{ background: "#7F1D1D", color: "#FCA5A5", border: "none", padding: "7px 18px", borderRadius: "8px", cursor: "pointer", fontSize: "12px" }}>❌ رد پیشنهاد</button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="kiarad-campaigns-content" style={{ display: "grid", gridTemplateColumns: "1.1fr 2fr", gap: "24px" }}>
        <div style={card}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>➕ ساخت کمپین جدید</h3>
          <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div><label style={ls}>عنوان کمپین:</label>
              <input type="text" required value={cTitle} onChange={function(e){setCTitle(e.target.value);}} placeholder="مثال: مهرماه سوآلین ویرا" style={is} /></div>
            <div><label style={ls}>توضیح:</label>
              <input type="text" value={cDesc} onChange={function(e){setCDesc(e.target.value);}} style={is} /></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div><label style={ls}>از تاریخ:</label>
                <IranDateInput aria-label="تاریخ شروع شمسی کمپین" required value={cStart} onChange={setCStart} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-white" style={is} /></div>
              <div><label style={ls}>تا تاریخ:</label>
                <IranDateInput aria-label="تاریخ پایان شمسی کمپین" required value={cEnd} onChange={setCEnd} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-white" style={is} /></div>
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
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#12a57a", color: "#fff", border: "none", padding: "10px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>
              {saving ? "در حال ثبت..." : "🎯 ساخت کمپین در دیتابیس"}
            </button>
          </form>
        </div>

        <div>
          {loading ? <div style={{ color: "#94A3B8", padding: "40px", textAlign: "center", ...card }}>در حال دریافت کمپین‌ها...</div> : null}
          {!loading && campaigns.length === 0 && !error ? (
            <div style={{ color: "#94A3B8", padding: "40px", textAlign: "center", ...card }}>هنوز کمپینی ساخته نشده — از دستیار هوشمند پیشنهاد بگیر یا از فرم بساز.</div>
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

export default function CampaignsPage() {
  return <PortalShell title="کمپین‌ها" eyebrow="کمپین‌های فروش"><div className="kskin"><CampaignsPageInner /></div></PortalShell>;
}
