"use client";


import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearSession, getSavedUser, getToken, secureApi } from "../../lib/secure-api";
import { AssistantChat } from "../../components/assistant-chat";

type Staff = { id?: number; name?: string; sales_amount?: number; target?: number; achievement_percent?: number };
type Customer = { id?: number; name?: string; city?: string; total_purchase?: number; invoice_count?: number };
type Recommendation = { priority?: string; message?: string };
type Trend = { month?: string; sales_amount?: number };
type Dashboard = {
  ceo_kpi?: { total_sales?: number; invoice_count?: number; customer_count?: number; total_collected?: number; total_debt?: number; active_target?: number; achievement_percent?: number };
  staff?: { staff?: Staff[] };
  customers?: { top_customers?: Customer[] };
  finance?: { total_sales?: number; total_collected?: number; total_debt?: number };
  inventory?: { product_count?: number; inventory_value?: number; low_stock_count?: number };
  recommendations?: { recommendations?: Recommendation[] };
  sales_trend?: Trend[];
};

type IconName = "grid" | "sales" | "users" | "wallet" | "box" | "target" | "tasks" | "report" | "spark" | "bell" | "refresh" | "search" | "menu" | "arrow";

const paths: Record<IconName, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  sales: <><path d="M4 18 10 12l4 4 6-8"/><path d="M15 8h5v5"/></>,
  users: <><circle cx="9" cy="8" r="3"/><path d="M3 20c0-4 2.5-6 6-6s6 2 6 6"/><circle cx="17" cy="7" r="2"/><path d="M16 13c3 .3 5 2 5 5"/></>,
  wallet: <><rect x="3" y="5" width="18" height="15" rx="3"/><path d="M3 9h18"/><path d="M16 14h2"/></>,
  box: <><path d="m4 7 8-4 8 4-8 4-8-4Z"/><path d="M4 7v10l8 4 8-4V7M12 11v10"/></>,
  target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></>,
  tasks: <><rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 9 2 2 4-4M8 16h8"/></>,
  report: <><path d="M6 3h9l4 4v14H6Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/></>,
  spark: <><path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Z"/><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7"/><path d="M10 19a2 2 0 0 0 4 0"/></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2 5"/><path d="M20 4v7h-7"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16"/></>,
  arrow: <><path d="m9 18 6-6-6-6"/></>,
};

function Icon({ name, className = "h-5 w-5" }: { name: IconName; className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className}>{paths[name]}</svg>;
}

const money = (value?: number) => `${new Intl.NumberFormat("fa-IR", { notation: "compact", maximumFractionDigits: 1 }).format(value ?? 0)} ریال`;
const number = (value?: number) => new Intl.NumberFormat("fa-IR").format(value ?? 0);
const percent = (value?: number) => `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(value ?? 0)}٪`;

const nav = [
  ["نمای کلی", "grid", "/management"], ["فروش و عملکرد", "sales", "/management"], ["ویزیتورها", "users", "/visitors"], ["خزانه‌داری", "wallet", "/treasury"],
  ["انبار و تأمین", "box", "/management"], ["اهداف فروش", "target", "/management"], ["تسک‌ها", "tasks", "/tasks"], ["گزارش‌های شبانه", "report", "/daily-reports"],
] as const;

function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-white/[0.07] bg-white/[0.035] shadow-[0_20px_70px_rgba(0,0,0,.18)] ${className}`}>{children}</section>;
}

function Kpi({ title, value, note, icon, color }: { title: string; value: string; note: string; icon: IconName; color: string }) {
  return <Panel className="group overflow-hidden p-4 transition hover:-translate-y-0.5 hover:border-white/15">
    <div className="flex items-center justify-between"><span className="text-[11px] text-slate-400">{title}</span><span className={`grid h-8 w-8 place-items-center rounded-xl ${color}`}><Icon name={icon} className="h-4 w-4"/></span></div>
    <div className="mt-3 text-xl font-extrabold tracking-tight text-white">{value}</div>
    <div className="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400"/>{note}</div>
  </Panel>;
}

function SalesChart({ data }: { data: Trend[] }) {
  const values = data.length ? data.map(x => x.sales_amount ?? 0) : [3, 4, 3.4, 5.8, 5.2, 7.6, 8.5, 7.9, 10];
  const max = Math.max(...values, 1);
  const points = values.map((v, i) => `${24 + i * (552 / Math.max(values.length - 1, 1))},${180 - (v / max) * 140}`).join(" ");
  const area = `24,180 ${points} 576,180`;
  return <div>
    <svg viewBox="0 0 600 205" className="h-[220px] w-full">
      <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8b5cf6" stopOpacity=".38"/><stop offset="1" stopColor="#8b5cf6" stopOpacity="0"/></linearGradient></defs>
      {[40, 85, 130, 175].map(y => <line key={y} x1="24" x2="576" y1={y} y2={y} stroke="rgba(255,255,255,.06)" strokeDasharray="3 6"/>)}
      <polygon points={area} fill="url(#area)"/><polyline points={points} fill="none" stroke="#9b7bff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
      {points.split(" ").map((p, i) => { const [x,y]=p.split(","); return <circle key={i} cx={x} cy={y} r="3" fill="#090b14" stroke="#a78bfa" strokeWidth="2"/>; })}
    </svg>
    <div className="flex justify-between px-5 text-[10px] text-slate-600"><span>ابتدای دوره</span><span>میانه دوره</span><span>امروز</span></div>
  </div>;
}

function AchievementRing({ value }: { value: number }) {
  const r=46, c=2*Math.PI*r, offset=c-(Math.min(value,100)/100)*c;
  return <div className="relative h-32 w-32"><svg viewBox="0 0 120 120" className="-rotate-90"><circle cx="60" cy="60" r={r} fill="none" stroke="rgba(255,255,255,.07)" strokeWidth="10"/><circle cx="60" cy="60" r={r} fill="none" stroke="#8b5cf6" strokeWidth="10" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}/></svg><div className="absolute inset-0 grid place-content-center text-center"><strong className="text-2xl text-white">{percent(value)}</strong><span className="mt-1 text-[10px] text-slate-500">تحقق هدف</span></div></div>;
}

export default function ManagementPage() {
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [copilot, setCopilot] = useState(false);
  const sessionUser = getSavedUser();

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      if (!getToken()) { router.replace("/login"); return; }
      setData(await secureApi<Dashboard>("/dashboard/full"));
    }
    catch { setError("ارتباط با سرویس اطلاعاتی برقرار نشد."); }
    finally { setLoading(false); }
  }, [router]);
  useEffect(() => { load(); }, [load]);

  const ceo=data?.ceo_kpi ?? {}, staff=data?.staff?.staff ?? [], customers=data?.customers?.top_customers ?? [], recs=data?.recommendations?.recommendations ?? [];
  const ranked=useMemo(()=>[...staff].sort((a,b)=>(b.sales_amount??0)-(a.sales_amount??0)),[staff]);
  const achievement=ceo.achievement_percent ?? 0;

  return <div dir="rtl" className="min-h-screen bg-[#070810] text-slate-200">
    <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_75%_-10%,rgba(124,58,237,.18),transparent_32%),radial-gradient(circle_at_10%_90%,rgba(34,211,238,.08),transparent_25%)]"/>
    {mobileNav && <button aria-label="بستن منو" className="fixed inset-0 z-40 bg-black/70 lg:hidden" onClick={()=>setMobileNav(false)}/>}
    <aside className={`fixed inset-y-0 right-0 z-50 flex w-[252px] flex-col border-l border-white/[0.07] bg-[#0b0d17]/95 backdrop-blur-xl transition-transform lg:translate-x-0 ${mobileNav?"translate-x-0":"translate-x-full"}`}>
      <div className="flex h-[76px] items-center gap-3 border-b border-white/[0.07] px-5"><div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-700 font-black text-white shadow-[0_0_28px_rgba(139,92,246,.35)]">K</div><div><div className="text-sm font-extrabold text-white">کیاراد BI</div><div className="text-[10px] text-slate-500">مرکز فرماندهی کسب‌وکار</div></div></div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-3">{nav.map(([label,icon,href],i)=><Link href={href} key={label} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-xs transition ${i===0?"bg-violet-500/15 text-violet-300 ring-1 ring-violet-400/15":"text-slate-500 hover:bg-white/5 hover:text-white"}`}><Icon name={icon}/><span>{label}</span>{i===6&&<span className="mr-auto rounded-full bg-rose-500 px-1.5 text-[9px] text-white">۳</span>}</Link>)}
        <a
          href="/treasury"
          className="flex items-center gap-3 px-4 py-3 text-slate-300 hover:text-white hover:bg-slate-800/80 rounded-xl font-medium transition duration-150 group"
        >
          <span className="text-lg">??</span>
          <span>?????????? ? ?????</span>
          <span className="mr-auto text-[10px] px-2 py-0.5 bg-violet-900/60 text-violet-300 rounded-full">????</span>
        </a>

      </nav>
      <div className="m-3 rounded-xl border border-violet-400/15 bg-violet-500/[0.07] p-3"><div className="flex items-center gap-2 text-xs font-bold text-violet-300"><Icon name="spark" className="h-4 w-4"/>دستیار هوشمند</div><p className="mt-2 text-[10px] leading-5 text-slate-500">تحلیل، پیش‌بینی و پیشنهاد اقدام مدیریتی</p><button onClick={()=>setCopilot(true)} className="mt-3 w-full rounded-lg bg-violet-600 py-2 text-[11px] font-bold text-white hover:bg-violet-500">شروع گفتگو</button></div>
      <div className="border-t border-white/[0.06] px-5 py-4 text-[10px] text-slate-600"><div>سامانه هوش تجاری کیاراد · نسخه داخلی</div><button onClick={()=>{clearSession();router.replace("/login");}} className="mt-2 text-rose-300">خروج از حساب</button></div>
    </aside>

    <div className="relative lg:mr-[252px]">
      <header className="sticky top-0 z-30 flex h-[76px] items-center justify-between border-b border-white/[0.07] bg-[#070810]/85 px-4 backdrop-blur-xl sm:px-7">
        <div className="flex items-center gap-3"><button onClick={()=>setMobileNav(true)} className="rounded-xl border border-white/10 p-2 lg:hidden"><Icon name="menu"/></button><div><div className="text-[10px] text-violet-400">نمای مدیریتی</div><h1 className="mt-1 text-base font-extrabold text-white sm:text-lg">داشبورد مدیرعامل</h1></div></div>
        <div className="flex items-center gap-2"><div className="hidden items-center gap-2 rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-2 text-[11px] text-slate-500 md:flex"><Icon name="search" className="h-4 w-4"/>جست‌وجو در سامانه...</div><button className="relative rounded-xl border border-white/[0.07] bg-white/[0.03] p-2.5"><Icon name="bell" className="h-4 w-4"/><span className="absolute left-2 top-2 h-1.5 w-1.5 rounded-full bg-rose-500"/></button><button onClick={load} className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-2.5 hover:bg-white/[0.07]"><Icon name="refresh" className={`h-4 w-4 ${loading?"animate-spin":""}`}/></button><div className="mr-1 hidden h-9 items-center gap-2 rounded-xl bg-white/[0.04] px-2 sm:flex"><div className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-violet-400 to-indigo-700 text-[10px] font-bold">{sessionUser?.full_name?.slice(0,2) || "م‌ع"}</div><div className="pl-2"><div className="text-[10px] font-bold text-white">{sessionUser?.full_name || "مدیرعامل"}</div><div className="text-[9px] text-emerald-400">● آنلاین</div></div></div></div>
      </header>

      <main className="mx-auto max-w-[1600px] p-4 sm:p-6 lg:p-7">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs text-slate-500">سلام؛ این تصویر لحظه‌ای وضعیت کیاراد است.</p><h2 className="mt-1 text-xl font-black text-white">نبض امروز کسب‌وکار</h2></div><div className="flex rounded-xl border border-white/[0.07] bg-white/[0.03] p-1 text-[10px]"><button className="rounded-lg bg-violet-600 px-3 py-1.5 text-white">این ماه</button><button className="px-3 py-1.5 text-slate-500">۳۰ روز</button><button className="px-3 py-1.5 text-slate-500">سه‌ماهه</button></div></div>
        {error&&<div className="mb-5 rounded-xl border border-rose-500/25 bg-rose-500/10 p-3 text-xs text-rose-300">{error}</div>}

        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Kpi title="فروش کل" value={money(ceo.total_sales)} note="داده قطعی فروش" icon="sales" color="bg-violet-500/15 text-violet-300"/>
          <Kpi title="وصولی" value={money(ceo.total_collected)} note="ثبت‌شده در سیستم" icon="wallet" color="bg-emerald-500/15 text-emerald-300"/>
          <Kpi title="مانده مطالبات" value={money(ceo.total_debt)} note="نیازمند برنامه وصول" icon="report" color="bg-rose-500/15 text-rose-300"/>
          <Kpi title="تحقق هدف" value={percent(achievement)} note={`هدف ${money(ceo.active_target)}`} icon="target" color="bg-amber-500/15 text-amber-300"/>
          <Kpi title="فاکتور" value={number(ceo.invoice_count)} note="در دوره انتخابی" icon="tasks" color="bg-cyan-500/15 text-cyan-300"/>
          <Kpi title="ارزش موجودی" value={money(data?.inventory?.inventory_value)} note={`${number(data?.inventory?.product_count)} قلم کالا`} icon="box" color="bg-fuchsia-500/15 text-fuchsia-300"/>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[1.55fr_.75fr]">
          <Panel className="p-5"><div className="flex items-start justify-between"><div><span className="text-[10px] text-violet-400">روند عملکرد</span><h3 className="mt-1 text-sm font-extrabold text-white">فروش و پیش‌بینی پایان دوره</h3></div><div className="text-left"><div className="text-sm font-bold text-emerald-400">{money(ceo.total_sales)}</div><div className="text-[9px] text-slate-600">فروش محقق‌شده</div></div></div><SalesChart data={data?.sales_trend ?? []}/></Panel>
          <Panel className="p-5"><div><span className="text-[10px] text-amber-400">هشدار نقدینگی</span><h3 className="mt-1 text-sm font-extrabold text-white">آمادگی پوشش تعهدات</h3></div><div className="mt-5 flex items-center justify-around"><AchievementRing value={achievement}/><div className="space-y-3 text-[10px]"><div><span className="text-slate-500">مطالبات باز</span><div className="mt-1 font-bold text-rose-300">{money(ceo.total_debt)}</div></div><div><span className="text-slate-500">وصول‌شده</span><div className="mt-1 font-bold text-emerald-300">{money(ceo.total_collected)}</div></div></div></div><div className="mt-4 rounded-xl border border-amber-400/15 bg-amber-400/[0.06] p-3 text-[10px] leading-5 text-amber-200">تقویم دقیق کسری نقدینگی پس از ورود اسناد دریافتنی و پرداختنی فعال می‌شود.</div></Panel>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[1.15fr_.85fr]">
          <Panel className="overflow-hidden"><div className="flex items-center justify-between border-b border-white/[0.06] p-4"><div><span className="text-[10px] text-cyan-400">تیم فروش</span><h3 className="mt-1 text-sm font-bold text-white">عملکرد ویزیتورها</h3></div><button className="text-[10px] text-violet-400">مشاهده همه</button></div><div className="divide-y divide-white/[0.05]">{ranked.length?ranked.slice(0,5).map((s,i)=><div key={s.id??i} className="grid grid-cols-[1fr_1fr_70px] items-center gap-3 px-4 py-3 text-[11px]"><div className="flex items-center gap-3"><span className="grid h-7 w-7 place-items-center rounded-lg bg-white/[0.05] text-slate-400">{number(i+1)}</span><div><div className="font-bold text-white">{s.name}</div><div className="text-[9px] text-slate-600">{money(s.sales_amount)} فروش</div></div></div><div><div className="mb-1.5 flex justify-between text-[9px]"><span className="text-slate-600">تحقق</span><span className="text-violet-300">{percent(s.achievement_percent)}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-gradient-to-l from-violet-500 to-cyan-400" style={{width:`${Math.min(s.achievement_percent??0,100)}%`}}/></div></div><span className={`rounded-full px-2 py-1 text-center text-[9px] ${(s.achievement_percent??0)>=70?"bg-emerald-500/10 text-emerald-300":"bg-rose-500/10 text-rose-300"}`}>{(s.achievement_percent??0)>=70?"در مسیر":"پیگیری"}</span></div>):<div className="p-8 text-center text-xs text-slate-600">داده ویزیتورها موجود نیست.</div>}</div></Panel>
          <Panel className="p-4"><div className="flex items-center justify-between"><div><span className="text-[10px] text-violet-400">اقدام هوشمند</span><h3 className="mt-1 text-sm font-bold text-white">پیشنهادهای اولویت‌دار</h3></div><Icon name="spark" className="h-5 w-5 text-violet-400"/></div><div className="mt-4 space-y-2.5">{recs.length?recs.slice(0,4).map((r,i)=><div key={i} className="rounded-xl border border-white/[0.06] bg-black/15 p-3"><div className="mb-2 flex items-center justify-between"><span className={`rounded-md px-2 py-0.5 text-[8px] ${r.priority==="high"?"bg-rose-500/10 text-rose-300":"bg-amber-500/10 text-amber-300"}`}>{r.priority==="high"?"اولویت بالا":"بررسی"}</span><button className="text-[9px] text-violet-400">ایجاد تسک</button></div><p className="text-[10px] leading-5 text-slate-300">{r.message}</p></div>):<div className="rounded-xl border border-dashed border-white/10 p-6 text-center text-[10px] text-slate-600">پیشنهاد جدیدی وجود ندارد.</div>}</div></Panel>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-2"><Panel className="overflow-hidden"><div className="border-b border-white/[0.06] p-4"><span className="text-[10px] text-fuchsia-400">مشتریان</span><h3 className="mt-1 text-sm font-bold text-white">مشتریان برتر و فرصت وصول</h3></div><div className="divide-y divide-white/[0.05]">{customers.slice(0,5).map((c,i)=><div key={c.id??i} className="grid grid-cols-[1fr_90px_100px] items-center px-4 py-3 text-[10px]"><div><div className="font-bold text-white">{c.name}</div><div className="mt-1 text-[9px] text-slate-600">{c.city} · {number(c.invoice_count)} فاکتور</div></div><span className="text-slate-500">{money(c.total_purchase)}</span><div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-fuchsia-500" style={{width:`${Math.max(8,100-i*18)}%`}}/></div></div>)}</div></Panel><Panel className="p-4"><div className="flex items-center justify-between"><div><span className="text-[10px] text-emerald-400">کنترل عملیات</span><h3 className="mt-1 text-sm font-bold text-white">کارهای مهم امروز</h3></div><span className="rounded-full bg-rose-500/10 px-2 py-1 text-[9px] text-rose-300">۳ مورد</span></div><div className="mt-4 space-y-2">{["پیگیری مشتریان بدون خرید ۹۰ روزه","بررسی عقب‌ماندگی تارگت فروش","تکمیل اطلاعات اسناد دریافتنی"].map((x,i)=><div key={x} className="flex items-center gap-3 rounded-xl border border-white/[0.05] bg-black/10 p-3"><span className={`h-2 w-2 rounded-full ${i===0?"bg-rose-400":i===1?"bg-amber-400":"bg-cyan-400"}`}/><span className="text-[10px] text-slate-300">{x}</span><Icon name="arrow" className="mr-auto h-4 w-4 text-slate-600"/></div>)}</div></Panel></div>
      </main>
    </div>

    <button onClick={()=>setCopilot(true)} className="fixed bottom-5 left-5 z-40 flex items-center gap-2 rounded-2xl border border-violet-300/20 bg-violet-600 px-4 py-3 text-xs font-bold text-white shadow-[0_0_40px_rgba(124,58,237,.45)] hover:bg-violet-500"><Icon name="spark" className="h-5 w-5"/><span className="hidden sm:inline">از دستیار کیاراد بپرس</span></button>
    <AssistantChat open={copilot} onClose={()=>setCopilot(false)} />
  </div>;
}
