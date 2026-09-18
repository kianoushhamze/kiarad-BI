"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { getSavedUser, secureApi } from "../../lib/secure-api";

type Visitor = { id: number; name: string; phone?: string; sales_amount: number; invoice_count: number; target_amount: number; achievement_percent: number; remaining: number; open_tasks: number; overdue_tasks: number; last_report_date?: string; report_submitted_today: boolean; };
type Salesperson = { id: number; name: string; phone?: string; user_id?: number | null; username?: string | null; };

const money = (v: number) => `${new Intl.NumberFormat("fa-IR", { notation: "compact", maximumFractionDigits: 1 }).format(v || 0)} ریال`;
const num = (v: number) => new Intl.NumberFormat("fa-IR").format(v || 0);

export default function VisitorsPage() {
  const [visitors, setVisitors] = useState<Visitor[]>([]);
  const [profiles, setProfiles] = useState<Salesperson[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showProfile, setShowProfile] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const user = getSavedUser();
  const manager = user?.role === "ceo" || user?.role === "sales_manager";

  const load = useCallback(async () => {
    setError("");
    try {
      const overview = await secureApi<{ visitors: Visitor[] }>("/visitors/overview");
      setVisitors(overview.visitors);
      if (manager) setProfiles((await secureApi<{ salespersons: Salesperson[] }>("/salespersons")).salespersons);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "دریافت اطلاعات انجام نشد."); }
  }, [manager]);
  useEffect(() => { load(); }, [load]);

  const createProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); setError("");
    try {
      await secureApi("/salespersons", { method: "POST", body: JSON.stringify({ name: form.get("name"), phone: form.get("phone") || null }) });
      setMessage("پروفایل ویزیتور ایجاد شد. اکنون حساب ورود او را بسازید."); setShowProfile(false); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "ثبت انجام نشد."); }
  };
  const createAccount = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); setError("");
    try {
      await secureApi("/users", { method: "POST", body: JSON.stringify({ username: form.get("username"), full_name: form.get("full_name"), password: form.get("password"), role: "salesperson", salesperson_id: Number(form.get("salesperson_id")) }) });
      setMessage("حساب ورود ویزیتور ساخته شد."); setShowAccount(false); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "ثبت حساب انجام نشد."); }
  };

  return <PortalShell title={manager ? "مدیریت ویزیتورها" : "پنل عملکرد من"} eyebrow="تیم فروش" actions={manager && <div className="flex gap-2"><button onClick={() => setShowProfile(true)} className="rounded-xl border border-white/10 px-3 py-2 text-[10px] text-slate-300">ویزیتور جدید</button><button onClick={() => setShowAccount(true)} className={primaryButton}>ساخت حساب ورود</button></div>}>
    {(error || message) && <div className={`mb-4 rounded-xl border p-3 text-xs ${error ? "border-rose-500/20 bg-rose-500/10 text-rose-300" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"}`}>{error || message}</div>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="تعداد ویزیتورها" value={num(visitors.length)} note="پروفایل فعال" />
      <Metric label="فروش تیم" value={money(visitors.reduce((a, b) => a + Number(b.sales_amount), 0))} note="فروش ثبت‌شده" />
      <Metric label="تسک باز" value={num(visitors.reduce((a, b) => a + Number(b.open_tasks), 0))} note="نیازمند پیگیری" />
      <Metric label="گزارش امروز" value={`${num(visitors.filter(v => v.report_submitted_today).length)} از ${num(visitors.length)}`} note="ثبت گزارش شبانه" />
    </div>
    <Surface className="mt-4 overflow-hidden">
      <div className="border-b border-white/[0.06] p-5"><h2 className="text-sm font-bold text-white">کارت عملکرد ویزیتورها</h2><p className="mt-1 text-[10px] text-slate-500">فروش، تارگت، تسک و آخرین گزارش در یک نما</p></div>
      <div className="grid gap-3 p-4 lg:grid-cols-2">{visitors.map(v => <article key={v.id} className="rounded-2xl border border-white/[0.06] bg-black/15 p-4">
        <div className="flex items-start justify-between"><div><h3 className="text-sm font-bold text-white">{v.name}</h3><p className="mt-1 text-[10px] text-slate-600">{v.phone || "شماره تماس ثبت نشده"}</p></div><span className={`rounded-full px-2 py-1 text-[9px] ${v.achievement_percent >= 70 ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"}`}>{v.achievement_percent >= 70 ? "در مسیر هدف" : "نیازمند پیگیری"}</span></div>
        <div className="mt-5 grid grid-cols-3 gap-3 text-center"><Mini label="فروش" value={money(v.sales_amount)} /><Mini label="فاکتور" value={num(v.invoice_count)} /><Mini label="مانده هدف" value={money(v.remaining)} /></div>
        <div className="mt-5"><div className="mb-2 flex justify-between text-[10px]"><span className="text-slate-500">تحقق تارگت</span><b className="text-violet-300">{num(v.achievement_percent)}٪</b></div><div className="h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-gradient-to-l from-violet-500 to-cyan-400" style={{ width: `${Math.min(v.achievement_percent, 100)}%` }} /></div></div>
        <div className="mt-4 flex flex-wrap gap-2 text-[9px]"><span className="rounded-lg bg-white/[0.04] px-2 py-1.5 text-slate-400">{num(v.open_tasks)} تسک باز</span>{v.overdue_tasks > 0 && <span className="rounded-lg bg-rose-500/10 px-2 py-1.5 text-rose-300">{num(v.overdue_tasks)} عقب‌افتاده</span>}<span className={`rounded-lg px-2 py-1.5 ${v.report_submitted_today ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"}`}>{v.report_submitted_today ? "گزارش امروز ثبت شده" : "گزارش امروز ثبت نشده"}</span></div>
      </article>)}</div>
    </Surface>

    {showProfile && <Modal title="ایجاد پروفایل ویزیتور" close={() => setShowProfile(false)}><form onSubmit={createProfile} className="space-y-3"><input name="name" required placeholder="نام و نام خانوادگی" className={fieldClass} /><input name="phone" placeholder="شماره تماس" className={fieldClass} /><button className={`${primaryButton} w-full`}>ثبت پروفایل</button></form></Modal>}
    {showAccount && <Modal title="ساخت حساب ورود ویزیتور" close={() => setShowAccount(false)}><form onSubmit={createAccount} className="space-y-3"><select name="salesperson_id" required className={fieldClass}><option value="">انتخاب پروفایل ویزیتور</option>{profiles.filter(p => !p.user_id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select><input name="full_name" required placeholder="نام کامل" className={fieldClass} /><input name="username" required placeholder="نام کاربری انگلیسی" className={fieldClass} /><input name="password" type="password" minLength={10} required placeholder="رمز عبور حداقل ۱۰ کاراکتر" className={fieldClass} /><button className={`${primaryButton} w-full`}>ساخت حساب</button></form></Modal>}
  </PortalShell>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) { return <Surface className="p-4"><div className="text-[10px] text-slate-500">{label}</div><div className="mt-3 text-xl font-black text-white">{value}</div><div className="mt-2 text-[9px] text-violet-400">{note}</div></Surface>; }
function Mini({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-white/[0.035] p-2"><div className="text-[9px] text-slate-600">{label}</div><div className="mt-1 truncate text-[10px] font-bold text-slate-300">{value}</div></div>; }
function Modal({ title, close, children }: { title: string; close: () => void; children: ReactNode }) { return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"><div className="w-full max-w-md rounded-3xl border border-white/10 bg-[#0c0e19] p-5"><div className="mb-5 flex items-center justify-between"><h2 className="text-sm font-bold text-white">{title}</h2><button onClick={close} className="text-xl text-slate-500">×</button></div>{children}</div></div>; }
