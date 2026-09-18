"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "../../lib/api";
import { saveSession, type SessionUser } from "../../lib/secure-api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const response = await fetch(`${API_URL}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.detail ?? "نام کاربری یا رمز عبور درست نیست.");
      saveSession(body.access_token, body.user as SessionUser);
      router.replace(body.user.role === "salesperson" ? "/visitors" : body.user.role === "finance" ? "/treasury" : "/management");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "ورود انجام نشد."); }
    finally { setLoading(false); }
  };

  return <div dir="rtl" className="relative grid min-h-screen place-items-center overflow-hidden bg-[#070810] p-4 text-slate-200">
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_15%,rgba(124,58,237,.3),transparent_30%),radial-gradient(circle_at_15%_85%,rgba(34,211,238,.1),transparent_24%)]" />
    <form onSubmit={submit} className="relative w-full max-w-md rounded-3xl border border-white/10 bg-[#0c0e19]/90 p-7 shadow-[0_30px_100px_rgba(0,0,0,.55)] backdrop-blur-xl">
      <div className="mb-7 flex items-center gap-3"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-700 text-xl font-black">K</span><div><h1 className="text-lg font-black text-white">ورود به کیاراد BI</h1><p className="mt-1 text-[11px] text-slate-500">دسترسی مدیرعامل، مالی و ویزیتورها</p></div></div>
      <label className="text-[11px] text-slate-400">نام کاربری<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-violet-400/50" /></label>
      <label className="mt-4 block text-[11px] text-slate-400">رمز عبور<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none focus:border-violet-400/50" /></label>
      {error && <div className="mt-4 rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-[11px] text-rose-300">{error}</div>}
      <button disabled={loading} className="mt-6 w-full rounded-xl bg-violet-600 py-3 text-sm font-bold text-white hover:bg-violet-500 disabled:opacity-60">{loading ? "در حال ورود…" : "ورود به سامانه"}</button>
      <p className="mt-5 text-center text-[10px] leading-5 text-slate-600">اطلاعات ورود را مدیر سامانه ایجاد می‌کند.</p>
    </form>
  </div>;
}
