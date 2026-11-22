"use client";

import React, { useState, useEffect, useCallback } from "react";
import { secureApi } from "../../lib/secure-api";
import { PortalShell } from "../../components/portal-shell";

type UserRow = { id?: number; username?: string; full_name?: string; role?: string; salesperson_id?: number | null; salesperson_name?: string; is_active?: boolean | number | string; };
type SpRow = { id?: number; name?: string; phone?: string; };
const errorMessage = (err: unknown) => err instanceof Error ? err.message : "خطا";

function PersonnelPageInner() {
  const usersInit: UserRow[] = [];
  const spInit: SpRow[] = [];
  const [users, setUsers] = useState<Array<UserRow>>(usersInit);
  const [sps, setSps] = useState<Array<SpRow>>(spInit);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [spName, setSpName] = useState("");
  const [spPhone, setSpPhone] = useState("");
  const [uFull, setUFull] = useState("");
  const [uUser, setUUser] = useState("");
  const [uPass, setUPass] = useState("");
  const uRole = "salesperson";
  const [uSp, setUSp] = useState("");
  const [saving, setSaving] = useState(false);
  const [editUser, setEditUser] = useState<UserRow | null>(null);
  const [editFull, setEditFull] = useState("");
  const [editUser2, setEditUser2] = useState("");
  const [editRole, setEditRole] = useState("salesperson");
  const [editSp, setEditSp] = useState("");
  const [editActive, setEditActive] = useState(1);
  const [pwdUser, setPwdUser] = useState<UserRow | null>(null);
  const [pwdVal, setPwdVal] = useState("");
  const [pwdConfirm, setPwdConfirm] = useState("");
  const [pwdError, setPwdError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const d = await secureApi<UserRow[] | { users?: UserRow[] }>("/users", { method: "GET" });
      setUsers(Array.isArray(d) ? d : d.users || []);
      const sd = await secureApi<SpRow[] | { salespersons?: SpRow[] }>("/salespersons", { method: "GET" });
      setSps(Array.isArray(sd) ? sd : sd.salespersons || []);
    } catch (err: unknown) {
      const m = errorMessage(err);
      setUsers([]);
      setError(m.indexOf("Authentication") !== -1 ? "ابتدا از صفحه ورود وارد سیستم شوید." : "دریافت داده ناموفق بود: " + m);
    } finally { setLoading(false); }
  }, []);

  useEffect(function () { void Promise.resolve().then(load); }, [load]);

  const flash = function (t: string) { setMsg(t); setTimeout(function(){ setMsg(""); }, 5000); };

  const addSp = async function (e: React.FormEvent) {
    e.preventDefault();
    if (!spName.trim() || saving) return;
    setSaving(true);
    try {
      await secureApi("/salespersons", { method: "POST", body: JSON.stringify({ name: spName, phone: spPhone || null }) });
      setSpName(""); setSpPhone("");
      flash("✓ ویزیتور در دیتابیس ثبت شد.");
      await load();
    } catch (err: unknown) { flash("ثبت ویزیتور ناموفق: " + errorMessage(err)); }
    finally { setSaving(false); }
  };

  const addUser = async function (e: React.FormEvent) {
    e.preventDefault();
    if (saving) return;
    if (uPass.length < 10) { flash("رمز عبور باید حداقل ۱۰ کاراکتر باشد."); return; }
    if (uRole === "salesperson" && !uSp) { flash("برای نقش ویزیتور، انتخاب پروفایل ویزیتور الزامی است."); return; }
    setSaving(true);
    try {
      await secureApi("/users", { method: "POST", body: JSON.stringify({
        username: uUser, full_name: uFull, password: uPass, role: uRole,
        salesperson_id: uRole === "salesperson" && uSp ? Number(uSp) : null }) });
      setUFull(""); setUUser(""); setUPass(""); setUSp("");
      flash("✓ حساب کاربری واقعی ساخته شد — از این لحظه می‌تواند وارد سیستم شود.");
      await load();
    } catch (err: unknown) { flash("ساخت حساب ناموفق: " + errorMessage(err)); }
    finally { setSaving(false); }
  };

  const openEdit = function (u: UserRow) {
    setEditUser(u);
    setEditFull(u.full_name || "");
    setEditUser2(u.username || "");
    setEditRole(u.role || "salesperson");
    setEditSp(u.salesperson_id ? String(u.salesperson_id) : "");
    setEditActive(u.is_active ? 1 : 0);
  };

  const saveEdit = async function () {
    if (!editUser || busy) return;
    setBusy(true);
    try {
      const payload = {
        full_name: editFull,
        ...((editUser.role === "salesperson" || editUser.role === "visitor") && editUser2.trim() !== editUser.username ? { username: editUser2.trim() } : {}),
        ...(editRole !== editUser.role ? { role: editRole } : {}),
        is_active: editActive,
        salesperson_id: (editRole === "salesperson" || editRole === "visitor") && editSp ? Number(editSp) : null,
      };
      await secureApi("/users/" + editUser.id, { method: "PATCH", body: JSON.stringify(payload) });
      flash("\u2713 \u0648\u06cc\u0631\u0627\u06cc\u0634 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f.");
      setEditUser(null);
      await load();
    } catch (err: unknown) { flash("ویرایش ناموفق: " + errorMessage(err)); }
    finally { setBusy(false); }
  };

  const savePwd = async function () {
    if (!pwdUser || busy) return;
    setPwdError("");
    if (pwdVal.length < 10 || pwdVal.length > 200) { setPwdError("رمز عبور باید بین ۱۰ و ۲۰۰ نویسه باشد."); return; }
    if (pwdVal !== pwdConfirm) { setPwdError("رمز جدید و تکرار آن یکسان نیستند."); return; }
    setBusy(true);
    try {
      await secureApi("/users/" + pwdUser.id + "/password", { method: "POST", body: JSON.stringify({ password: pwdVal }) });
      flash("\u2713 \u0631\u0645\u0632 \u0639\u0628\u0648\u0631 \u062a\u063a\u06cc\u06cc\u0631 \u06cc\u0627\u0641\u062a.");
      setPwdUser(null);
      setPwdVal("");
      setPwdConfirm("");
    } catch (err: unknown) { setPwdError("ریست رمز ناموفق: " + errorMessage(err)); }
    finally { setBusy(false); }
  };

  const deleteUser = async function (u: UserRow) {
    if (!u.id) return;
    if (u.id === 1) { flash("\u062d\u0633\u0627\u0628 \u0645\u062f\u06cc\u0631\u0639\u0627\u0645\u0644 \u0642\u0627\u0628\u0644 \u062d\u0630\u0641 \u0646\u06cc\u0633\u062a."); return; }
    if (!confirm("\u062d\u0630\u0641 \u06a9\u0627\u0631\u0628\u0631 " + (u.full_name || "") + "\u061f")) return;
    setBusy(true);
    try {
      await secureApi("/users/" + u.id, { method: "DELETE" });
      flash("\u2713 \u06a9\u0627\u0631\u0628\u0631 \u062d\u0630\u0641 \u0634\u062f.");
      await load();
    } catch (err: unknown) { flash("حذف ناموفق: " + errorMessage(err)); }
    finally { setBusy(false); }
  };

  const is: React.CSSProperties = { width: "100%", background: "rgba(10, 15, 34, .5)", border: "1px solid rgba(177, 190, 255, .20)", color: "#f0f3ff", padding: "8px 12px", borderRadius: "11px", fontSize: "13px", outline: "none" };
  const ls: React.CSSProperties = { fontSize: "12px", color: "#aab5d2", display: "block", marginBottom: "4px" };
  const card: React.CSSProperties = { background: "linear-gradient(145deg, rgba(25, 31, 58, .78), rgba(15, 21, 41, .76))", border: "1px solid rgba(177, 190, 255, .14)", borderRadius: "22px", padding: "20px", backdropFilter: "blur(16px)" };

  return (
    <div dir="rtl" className="kiarad-personnel" style={{ minHeight: "auto", background: "transparent", color: "#f0f3ff", padding: "0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#f0f3ff" }}>👥 مدیریت پرسنل و ویزیتورها</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#aab5d2" }}>ساخت حساب واقعی با رمز هش‌شده — داده زنده از دیتابیس</p>
        </div>
      </div>

      {error ? <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>⚠️ {error}</div> : null}
      {msg ? <div style={{ background: "#064E3B", border: "1px solid #12a57a", color: "#6EE7B7", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>{msg}</div> : null}

      <div className="kiarad-personnel-form-grid">
        <div style={card}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#d8dbff" }}>🏃 گام ۱: ثبت پروفایل ویزیتور</h3>
          <form onSubmit={addSp} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div><label style={ls}>نام و نام خانوادگی:</label>
              <input type="text" required value={spName} onChange={function(e){setSpName(e.target.value);}} placeholder="مثال: مهدی حسینی" style={is} /></div>
            <div><label style={ls}>تلفن (اختیاری):</label>
              <input type="text" value={spPhone} onChange={function(e){setSpPhone(e.target.value);}} style={is} /></div>
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#12a57a", color: "#fff", border: "none", padding: "10px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>ثبت ویزیتور</button>
          </form>
        </div>

        <div style={card}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#d8dbff" }}>🔐 گام ۲: ساخت حساب ورود سیستم</h3>
          <form onSubmit={addUser} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div className="kiarad-personnel-input-grid">
              <div><label style={ls}>نام کامل:</label>
                <input type="text" required value={uFull} onChange={function(e){setUFull(e.target.value);}} style={is} /></div>
              <div><label style={ls}>نام کاربری:</label>
                <input type="text" required minLength={3} value={uUser} onChange={function(e){setUUser(e.target.value);}} style={is} /></div>
            </div>
            <div className="kiarad-personnel-input-grid">
              <div><label style={ls}>رمز عبور (حداقل ۱۰ کاراکتر):</label>
                <input type="password" required minLength={10} value={uPass} onChange={function(e){setUPass(e.target.value);}} style={is} /></div>
              <div><label style={ls}>نوع حساب:</label><div style={{...is, color: "#CBD5E1"}}>پرسنل / ویزیتور</div></div>
            </div>
            {uRole === "salesperson" ? (
              <div><label style={ls}>پروفایل ویزیتور متصل:</label>
                <select value={uSp} onChange={function(e){setUSp(e.target.value);}} style={is}>
                  <option value="">— انتخاب کنید —</option>
                  {sps.map(function (s: SpRow) { return <option key={s.id} value={String(s.id)}>{s.name}</option>; })}
                </select></div>
            ) : null}
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#4f5fc4", color: "#fff", border: "none", padding: "10px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>ساخت حساب کاربری</button>
          </form>
        </div>
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#F8FAFC" }}>📋 حساب‌های واقعی سیستم ({users.length} کاربر)</h3>
        {loading ? <div style={{ color: "#94A3B8", padding: "24px", textAlign: "center" }}>در حال دریافت...</div> : null}
        {!loading && users.length === 0 && !error ? (
          <div style={{ color: "#94A3B8", padding: "24px", textAlign: "center", background: "#111C35", borderRadius: "8px" }}>هنوز حسابی ثبت نشده است.</div>
        ) : null}
        <div className="kiarad-personnel-table-scroll"><table style={{ width: "100%", minWidth: "650px", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead><tr style={{ color: "#94A3B8", borderBottom: "1px solid #1E293B" }}>
            <th style={{ padding: "10px", textAlign: "right" }}>نام</th>
            <th style={{ padding: "10px", textAlign: "right" }}>نام کاربری</th>
            <th style={{ padding: "10px", textAlign: "right" }}>نقش</th>
            <th style={{ padding: "10px", textAlign: "right" }}>ویزیتور متصل</th>
            <th style={{ padding: "10px", textAlign: "right" }}>وضعیت</th>
            <th style={{ padding: "10px", textAlign: "right" }}>عملیات</th>
          </tr></thead>
          <tbody>
            {users.map(function (u: UserRow) {
              const active = u.is_active === true || u.is_active === 1 || u.is_active === "1";
              return (
                <tr key={u.id} style={{ borderBottom: "1px solid #1E293B" }}>
                  <td style={{ padding: "10px", fontWeight: "bold" }}>{u.full_name}</td>
                  <td style={{ padding: "10px", color: "#38BDF8" }}>{u.username}</td>
                  <td style={{ padding: "10px" }}>{u.role === "ceo" ? "مدیرعامل" : u.role === "salesperson" ? "پرسنل / ویزیتور" : u.role}</td>
                  <td style={{ padding: "10px", color: "#94A3B8" }}>{u.salesperson_name || "—"}</td>
                  <td style={{ padding: "10px" }}>
                    <span style={{ background: active ? "#065F46" : "#7F1D1D", color: active ? "#6EE7B7" : "#FCA5A5", padding: "3px 10px", borderRadius: "12px", fontSize: "11px" }}>{active ? "فعال" : "غیرفعال"}</span>
                  </td>
                  <td style={{ padding: "10px" }}>
                    <button onClick={function(){openEdit(u);}} style={{ background: "transparent", border: "1px solid #4f5fc4", color: "#a5b4fc", padding: "4px 10px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", marginLeft: "4px" }} title="ویرایش">✏️</button>
                    <button onClick={function(){setPwdUser(u); setPwdVal(""); setPwdConfirm(""); setPwdError("");}} style={{ background: "transparent", border: "1px solid #d97706", color: "#fbbf24", padding: "4px 10px", borderRadius: "6px", cursor: "pointer", fontSize: "12px", marginLeft: "4px" }} title="ریست رمز این حساب">🔐 ریست رمز</button>
                    <button onClick={function(){deleteUser(u);}} style={{ background: "transparent", border: "1px solid #b91c1c", color: "#fca5a5", padding: "4px 10px", borderRadius: "6px", cursor: "pointer", fontSize: "12px" }} title="حذف">🗑️</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
      </div>

      {editUser ? (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000, display: "grid", placeItems: "center", padding: "16px" }} onClick={function(){setEditUser(null);}}>
          <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "14px", padding: "22px", width: "100%", maxWidth: "480px" }} onClick={function(e){e.stopPropagation();}}>
            <h3 style={{ margin: "0 0 16px 0", color: "#38BDF8", fontSize: "15px" }}>ویرایش کاربر</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <div><label style={ls}>نام کامل:</label><input value={editFull} onChange={function(e){setEditFull(e.target.value);}} style={is} /></div>
              <div><label style={ls}>نام کاربری:</label><input value={editUser2} onChange={(e)=>setEditUser2(e.target.value)} disabled={editUser.role !== "salesperson" && editUser.role !== "visitor"} minLength={3} maxLength={100} style={is} /></div>
              <div><label style={ls}>نقش:</label>
                <select value={editRole} onChange={function(e){setEditRole(e.target.value);}} style={is}>
                  <option value="salesperson">ویزیتور</option>
                  {editUser.role === "visitor" && <option value="visitor">ویزیتور (حساب قدیمی)</option>}
                  <option value="ceo">مدیرعامل</option>
                </select></div>
              {editRole === "salesperson" || editRole === "visitor" ? (
                <div><label style={ls}>پروفایل ویزیتور:</label>
                  <select value={editSp} onChange={function(e){setEditSp(e.target.value);}} style={is}>
                    <option value="">— انتخاب کنید —</option>
                    {sps.map(function(s: SpRow){ return <option key={s.id} value={String(s.id)}>{s.name}</option>; })}
                  </select></div>
              ) : null}
              <div><label style={ls}>وضعیت:</label>
                <select value={editActive} onChange={function(e){setEditActive(Number(e.target.value));}} style={is}>
                  <option value={1}>فعال</option>
                  <option value={0}>غیرفعال</option>
                </select></div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "18px" }}>
              <button onClick={function(){setEditUser(null);}} style={{ background: "transparent", border: "1px solid #334155", color: "#94A3B8", padding: "8px 16px", borderRadius: "8px", cursor: "pointer", fontSize: "13px" }}>انصراف</button>
              <button onClick={saveEdit} disabled={busy} style={{ background: busy ? "#334155" : "#4f5fc4", color: "#fff", border: "none", padding: "8px 20px", borderRadius: "8px", cursor: busy ? "default" : "pointer", fontSize: "13px", fontWeight: "bold" }}>{busy ? "..." : "ذخیره"}</button>
            </div>
          </div>
        </div>
      ) : null}

      {pwdUser ? (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000, display: "grid", placeItems: "center", padding: "16px" }} onClick={function(){if (!busy) setPwdUser(null);}}>
          <form role="dialog" aria-modal="true" aria-labelledby="reset-password-title" aria-busy={busy} onSubmit={function(e){e.preventDefault(); void savePwd();}} style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "14px", padding: "22px", width: "100%", maxWidth: "420px" }} onClick={function(e){e.stopPropagation();}}>
            <h3 id="reset-password-title" style={{ margin: "0 0 12px 0", color: "#fbbf24", fontSize: "15px" }}>🔐 ریست رمز — {pwdUser.full_name}</h3>
            <p style={{ color: "#aab5d2", fontSize: "12px", lineHeight: 1.9, marginBottom: "16px" }}>برای حساب «{pwdUser.username}» رمز جدید تعیین کنید. پس از ریست، ورودهای قبلی این حساب منقضی می‌شوند.</p>
            <div><label htmlFor="reset-password" style={ls}>رمز جدید (بین ۱۰ و ۲۰۰ نویسه):</label>
              <input id="reset-password" name="reset_password" type="password" autoComplete="new-password" required minLength={10} maxLength={200} value={pwdVal} onChange={function(e){setPwdVal(e.target.value);}} disabled={busy} style={is} dir="ltr" autoFocus /></div>
            <div style={{marginTop:"12px"}}><label htmlFor="reset-password-confirm" style={ls}>تکرار رمز جدید:</label>
              <input id="reset-password-confirm" name="reset_password_confirm" type="password" autoComplete="new-password" required minLength={10} maxLength={200} value={pwdConfirm} onChange={function(e){setPwdConfirm(e.target.value);}} disabled={busy} style={is} dir="ltr" /></div>
            {pwdError ? <p role="alert" style={{color:"#fca5a5",fontSize:"12px",lineHeight:1.9,marginTop:"12px"}}>{pwdError}</p> : null}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "18px" }}>
              <button type="button" disabled={busy} onClick={function(){setPwdUser(null);}} style={{ background: "transparent", border: "1px solid #334155", color: "#94A3B8", padding: "8px 16px", borderRadius: "8px", cursor: "pointer", fontSize: "13px" }}>انصراف</button>
              <button type="submit" disabled={busy} style={{ background: busy ? "#334155" : "#d97706", color: "#fff", border: "none", padding: "8px 20px", borderRadius: "8px", cursor: busy ? "default" : "pointer", fontSize: "13px", fontWeight: "bold" }}>{busy ? "در حال ریست…" : "ذخیرهٔ رمز جدید"}</button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}

export default function PersonnelPage() {
  return <PortalShell title="پرسنل" eyebrow="کاربران و ویزیتورها"><PersonnelPageInner /></PortalShell>;
}
