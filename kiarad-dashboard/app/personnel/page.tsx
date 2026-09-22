
"use client";
import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { secureApi } from "../../lib/secure-api";

type UserRow = { id?: number; username?: string; full_name?: string; role?: string; salesperson_name?: string; is_active?: any; };
type SpRow = { id?: number; name?: string; phone?: string; };

export default function PersonnelPage() {
  const usersInit: Array<UserRow> = new Array();
  const spInit: Array<SpRow> = new Array();
  const emptyUsers: Array<UserRow> = new Array();
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
  const [uRole, setURole] = useState("salesperson");
  const [uSp, setUSp] = useState("");
  const [saving, setSaving] = useState(false);

  const setUsersEmpty = function () { setUsers(emptyUsers); };

  const load = useCallback(async function () {
    setLoading(true); setError("");
    try {
      const d = (await secureApi("/users", { method: "GET" })) as any;
      const f: Array<UserRow> = new Array();
      if (d && d.users) d.users.forEach(function (x: UserRow) { f.push(x); });
      setUsers(f);
      const sd = (await secureApi("/salespersons", { method: "GET" })) as any;
      const fs: Array<SpRow> = new Array();
      if (sd && sd.salespersons) sd.salespersons.forEach(function (x: SpRow) { fs.push(x); });
      setSps(fs);
    } catch (err: any) {
      const m = err && err.message ? String(err.message) : "خطای ناشناخته";
      setUsersEmpty();
      setError(m.indexOf("Authentication") !== -1 ? "ابتدا از صفحه ورود وارد سیستم شوید." : "دریافت داده ناموفق بود: " + m);
    } finally { setLoading(false); }
  }, new Array());

  useEffect(function () { load(); }, new Array(load));

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
    } catch (err: any) { flash("ثبت ویزیتور ناموفق: " + (err && err.message ? err.message : "خطا")); }
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
    } catch (err: any) { flash("ساخت حساب ناموفق: " + (err && err.message ? err.message : "خطا")); }
    finally { setSaving(false); }
  };

  const is: React.CSSProperties = { width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "8px", fontSize: "13px", outline: "none" };
  const ls: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" };
  const card: React.CSSProperties = { background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" };

  return (
    <div dir="rtl" style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>👥 مدیریت پرسنل و ویزیتورها</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>ساخت حساب واقعی با رمز هش‌شده — داده زنده از دیتابیس</p>
        </div>
        <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold" }}>← داشبورد اصلی</Link>
      </div>

      {error ? <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>⚠️ {error}</div> : null}
      {msg ? <div style={{ background: "#064E3B", border: "1px solid #10B981", color: "#6EE7B7", padding: "12px 18px", borderRadius: "10px", marginBottom: "16px", fontSize: "13px" }}>{msg}</div> : null}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginBottom: "24px" }}>
        <div style={card}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>🏃 گام ۱: ثبت پروفایل ویزیتور</h3>
          <form onSubmit={addSp} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div><label style={ls}>نام و نام خانوادگی:</label>
              <input type="text" required value={spName} onChange={function(e){setSpName(e.target.value);}} placeholder="مثال: مهدی حسینی" style={is} /></div>
            <div><label style={ls}>تلفن (اختیاری):</label>
              <input type="text" value={spPhone} onChange={function(e){setSpPhone(e.target.value);}} style={is} /></div>
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#10B981", color: "#fff", border: "none", padding: "10px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>ثبت ویزیتور</button>
          </form>
        </div>

        <div style={card}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>🔐 گام ۲: ساخت حساب ورود سیستم</h3>
          <form onSubmit={addUser} style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div><label style={ls}>نام کامل:</label>
                <input type="text" required value={uFull} onChange={function(e){setUFull(e.target.value);}} style={is} /></div>
              <div><label style={ls}>نام کاربری:</label>
                <input type="text" required minLength={3} value={uUser} onChange={function(e){setUUser(e.target.value);}} style={is} /></div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div><label style={ls}>رمز عبور (حداقل ۱۰ کاراکتر):</label>
                <input type="password" required minLength={10} value={uPass} onChange={function(e){setUPass(e.target.value);}} style={is} /></div>
              <div><label style={ls}>نقش:</label>
                <select value={uRole} onChange={function(e){setURole(e.target.value);}} style={is}>
                  <option value="salesperson">ویزیتور</option>
                  <option value="sales_manager">مدیر فروش</option>
                  <option value="finance">مالی</option>
                </select></div>
            </div>
            {uRole === "salesperson" ? (
              <div><label style={ls}>پروفایل ویزیتور متصل:</label>
                <select value={uSp} onChange={function(e){setUSp(e.target.value);}} style={is}>
                  <option value="">— انتخاب کنید —</option>
                  {sps.map(function (s: SpRow) { return <option key={s.id} value={String(s.id)}>{s.name}</option>; })}
                </select></div>
            ) : null}
            <button type="submit" disabled={saving} style={{ background: saving ? "#065F46" : "#2563EB", color: "#fff", border: "none", padding: "10px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}>ساخت حساب کاربری</button>
          </form>
        </div>
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#F8FAFC" }}>📋 حساب‌های واقعی سیستم ({users.length} کاربر)</h3>
        {loading ? <div style={{ color: "#94A3B8", padding: "24px", textAlign: "center" }}>در حال دریافت...</div> : null}
        {!loading && users.length === 0 && !error ? (
          <div style={{ color: "#94A3B8", padding: "24px", textAlign: "center", background: "#111C35", borderRadius: "8px" }}>هنوز حسابی ثبت نشده است.</div>
        ) : null}
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
          <thead><tr style={{ color: "#94A3B8", borderBottom: "1px solid #1E293B" }}>
            <th style={{ padding: "10px", textAlign: "right" }}>نام</th>
            <th style={{ padding: "10px", textAlign: "right" }}>نام کاربری</th>
            <th style={{ padding: "10px", textAlign: "right" }}>نقش</th>
            <th style={{ padding: "10px", textAlign: "right" }}>ویزیتور متصل</th>
            <th style={{ padding: "10px", textAlign: "right" }}>وضعیت</th>
          </tr></thead>
          <tbody>
            {users.map(function (u: UserRow) {
              const active = u.is_active === true || u.is_active === 1 || u.is_active === "1";
              return (
                <tr key={u.id} style={{ borderBottom: "1px solid #1E293B" }}>
                  <td style={{ padding: "10px", fontWeight: "bold" }}>{u.full_name}</td>
                  <td style={{ padding: "10px", color: "#38BDF8" }}>{u.username}</td>
                  <td style={{ padding: "10px" }}>{u.role}</td>
                  <td style={{ padding: "10px", color: "#94A3B8" }}>{u.salesperson_name || "—"}</td>
                  <td style={{ padding: "10px" }}>
                    <span style={{ background: active ? "#065F46" : "#7F1D1D", color: active ? "#6EE7B7" : "#FCA5A5", padding: "3px 10px", borderRadius: "12px", fontSize: "11px" }}>{active ? "فعال" : "غیرفعال"}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
