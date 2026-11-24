"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PortalShell, Surface, fieldClass } from "../../components/portal-shell";
import { secureApi, type SessionUser } from "../../lib/secure-api";
import { VisitCoverage } from "../../components/visit-coverage";
import { IranDateInput } from "../../components/IranDateInput";
import { formatIranDate, iranTodayIso } from "../../lib/iran-date";

type Task = { id: number; title: string; assigned_to: number; status: string; review_status?: string; due_date?: string; progress: number };
type Target = { id: number; title: string; salesperson_id?: number; target_amount: number; status: string; start_date?: string; end_date?: string };
type Followup = { id: number; visitor_name: string; customer_name: string; notes: string; next_date: string; status: string; is_due: boolean };
type Person = SessionUser & { is_active?: boolean };
type Campaign = {id:number;title:string;description?:string;starts_at:string;ends_at:string;is_active:boolean};
type Base = {source:string;id:number;name:string;city?:string;address?:string};
type RouteStop = {id:number;monthly_stop_id?:number;outcome_status?:string;base_source:string;base_id:number;visit_date:string;stop_order:number;note?:string;base_name:string;city?:string;address?:string;checkin_status?:string;checked_in_at?:string;distance_m?:number};
const statuses: Record<string,string> = { new: "جدید", in_progress: "در حال انجام", completed: "گزارش پایان کار", blocked: "متوقف", pending: "منتظر بررسی مدیر", approved: "تأیید مدیر", changes_requested: "برگشت برای اصلاح" };
const number = (value: number) => new Intl.NumberFormat("fa-IR").format(value);
const localDate = iranTodayIso;

const visitOutcomes = {
  completed: "ویزیت انجام شد",
  no_order: "ویزیت شد، بدون سفارش",
  not_visited: "ویزیت انجام نشد",
};

function StopActions({ stop, today, onOutcome, onReminder }: {
  stop: RouteStop; today: string; onOutcome: (status: string) => void; onReminder: () => void;
}) {
  const [action, setAction] = useState<"outcome" | "reminder" | null>(null);
  const [outcome, setOutcome] = useState("completed");
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(today);
  const [time, setTime] = useState("10:00");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const name = stop.base_name?.trim();
  const canRecord = stop.monthly_stop_id && !stop.outcome_status && stop.visit_date <= today;
  if (!name) return null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !action) return;
    setBusy(true);
    setMessage("");
    try {
      if (action === "outcome") {
        await secureApi(`/monthly-visit-plans/stops/${stop.monthly_stop_id}/outcome`, {
          method: "POST", body: JSON.stringify({ outcome_status: outcome, outcome_notes: notes, only_if_unreported: true }),
        });
        onOutcome(outcome);
        setMessage("نتیجه ثبت شد.");
      } else {
        await secureApi("/crm/interactions", {
          method: "POST", body: JSON.stringify({
            customer_name: name, interaction_type: "ویزیت حضوری", product_discussed: "",
            next_followup_date: date, followup_time: time, notes,
          }),
        });
        onReminder();
        setMessage("یادآوری ثبت شد.");
      }
      setAction(null);
      setNotes("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ثبت انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="mt-3 w-full space-y-2">
    {stop.outcome_status && <p className="text-xs text-emerald-300">نتیجه: {visitOutcomes[stop.outcome_status as keyof typeof visitOutcomes] ?? "ثبت شده"}</p>}
    <div className="flex flex-wrap gap-2 text-sm text-violet-300">
      {canRecord && <button type="button" disabled={busy} onClick={() => setAction("outcome")} className="rounded-lg border border-white/15 px-3 py-2">ثبت نتیجه</button>}
      <button type="button" disabled={busy} onClick={() => setAction("reminder")} className="rounded-lg border border-white/15 px-3 py-2">یادآوری</button>
      <Link href={`/proformas#customer=${encodeURIComponent(name)}`} className="rounded-lg border border-white/15 px-3 py-2">پیش‌فاکتور</Link>
    </div>
    {action && <form onSubmit={save} className="grid gap-2 rounded-lg bg-white/5 p-3">
      {action === "outcome" ? <label>نتیجه<select className={fieldClass} value={outcome} onChange={event => setOutcome(event.target.value)}>
        {Object.entries(visitOutcomes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label> : <div className="grid gap-2 sm:grid-cols-2">
        <IranDateInput aria-label="تاریخ یادآوری" className={fieldClass} value={date} onChange={setDate} />
        <input aria-label="ساعت یادآوری" type="time" required className={fieldClass} value={time} onChange={event => setTime(event.target.value)} />
      </div>}
      <textarea aria-label="توضیح اختیاری" placeholder="توضیح اختیاری" className={fieldClass} maxLength={500} value={notes} onChange={event => setNotes(event.target.value)} />
      <div className="flex gap-4 text-sm">
        <button type="submit" disabled={busy || (action === "reminder" && (!date || !time))} className="rounded-lg bg-violet-700 px-3 py-2 disabled:opacity-50">{busy ? "در حال ثبت…" : "ذخیره"}</button>
        <button type="button" disabled={busy} onClick={() => setAction(null)}>انصراف</button>
      </div>
    </form>}
    {message && <p role="status" className="text-sm text-slate-300">{message}</p>}
  </div>;
}

export default function MyPlanPage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [peopleReady, setPeopleReady] = useState(false);
  const routePrefillApplied = useRef(false);
  const [person, setPerson] = useState("");
  const [manager, setManager] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [followups, setFollowups] = useState<Followup[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [choices, setChoices] = useState<Campaign[]>([]);
  const [campaignId, setCampaignId] = useState("");
  const [campaignError, setCampaignError] = useState("");
  const [assigning, setAssigning] = useState(false);
  const [showAllRoutes, setShowAllRoutes] = useState(false);
  const [routes, setRoutes] = useState<RouteStop[]>([]);
  const [bases, setBases] = useState<Base[]>([]);
  const [routeDate, setRouteDate] = useState(localDate());
  const [routeBase, setRouteBase] = useState("");
  const [routeOrder, setRouteOrder] = useState("1");
  const [routeNote, setRouteNote] = useState("");
  const [routeBusy, setRouteBusy] = useState(false);
  const [routeError, setRouteError] = useState("");
  const [routePrefillMessage, setRoutePrefillMessage] = useState("");
  useEffect(() => {
    if (!manager || !peopleReady || !bases.length || routePrefillApplied.current) return;
    const params = new URLSearchParams(window.location.search);
    const source = params.get("base_source"), baseId = params.get("base_id"), profileId = params.get("salesperson_id");
    routePrefillApplied.current = true;
    if (!source && !baseId && !profileId) return;
    const safeId = (value: string | null) => value !== null && /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0;
    const requestedBase = safeId(baseId) ? bases.find(base => base.source === source && base.id === Number(baseId)) : undefined;
    const requestedPerson = profileId && safeId(profileId) ? people.find(candidate => candidate.salesperson_id === Number(profileId)) : undefined;
    void Promise.resolve().then(() => {
      if (!requestedBase || (profileId !== null && !requestedPerson)) {
        setRoutePrefillMessage("پایگاه یا پرسنل این لینک در فهرست مجاز پیدا نشد؛ از فهرست‌های همین صفحه انتخاب کنید.");
        return;
      }
      setRouteBase(`${requestedBase.source}:${requestedBase.id}`);
      if (requestedPerson) setPerson(String(requestedPerson.id));
      setRoutePrefillMessage("پایگاه تأییدشده برای مسیر انتخاب شد؛ تاریخ، ترتیب و پرسنل را بررسی کنید و برای ذخیره، «افزودن به مسیر» را بزنید.");
    });
  }, [manager, peopleReady, bases, people]);
  useEffect(() => {
    if (!person) return;
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setCampaigns([]); setCampaignError("");
      return secureApi<{items:Campaign[]}>(`/tasks/campaign-assignments?user_id=${encodeURIComponent(person)}`)
        .then(data=>{if(active) setCampaigns(data.items || []);})
        .catch(()=>{if(active) setCampaignError("دریافت کمپین‌های شخصی ناموفق بود.");});
    });
    return ()=>{active=false;};
  },[person]);
  useEffect(() => {
    if (!person) return;
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setRoutes([]); setRouteError("");
      return secureApi<{items:RouteStop[]}>(`/api/compensation/visit-routes?user_id=${encodeURIComponent(person)}`)
        .then(data=>{if(active) setRoutes(data.items || []);})
        .catch(()=>{if(active) setRouteError("برنامهٔ مسیر دریافت نشد.");});
    });
    return ()=>{active=false;};
  },[person]);
  useEffect(() => {
    if (!manager) return;
    Promise.allSettled([
      secureApi<Campaign[]>("/campaigns"),
      secureApi<{items:Base[]}>("/api/compensation/bases"),
    ]).then(([campaignResult,baseResult])=>{
      if(campaignResult.status==="fulfilled") setChoices(campaignResult.value.filter(c=>c.is_active));
      else setCampaignError("فهرست کمپین‌های قابل تخصیص دریافت نشد.");
      if(baseResult.status==="fulfilled") setBases(baseResult.value.items || []);
      else setRouteError("فهرست پایگاه‌ها دریافت نشد.");
    });
  },[manager]);
  const assign = async () => {
    if (!person || !campaignId || assigning) return;
    setAssigning(true); setCampaignError("");
    try {
      await secureApi("/tasks/campaign-assignments",{method:"POST",body:JSON.stringify({user_id:Number(person),campaign_id:Number(campaignId)})});
      const result=await secureApi<{items:Campaign[]}>(`/tasks/campaign-assignments?user_id=${person}`);
      setCampaigns(result.items); setCampaignId("");
    } catch {setCampaignError("تخصیص یا بازخوانی کمپین ناموفق بود؛ دوباره تلاش کنید.");}
    finally {setAssigning(false);}
  };
  const assignRoute = async () => {
    if (!person || !routeBase || !routeDate || routeBusy) return;
    const [source,id] = routeBase.split(":");
    setRouteBusy(true); setRouteError("");
    try {
      await secureApi("/api/compensation/visit-routes",{method:"POST",body:JSON.stringify({user_id:Number(person),source,base_id:Number(id),visit_date:routeDate,stop_order:Number(routeOrder),note:routeNote})});
      const result=await secureApi<{items:RouteStop[]}>(`/api/compensation/visit-routes?user_id=${encodeURIComponent(person)}`);
      setRoutes(result.items || []); setRouteBase(""); setRouteNote(""); setRoutePrefillMessage("");
    } catch { setRouteError("ثبت یا بازخوانی برنامهٔ مسیر ناموفق بود."); }
    finally { setRouteBusy(false); }
  };
  const removeRoute = async (id:number) => {
    if (routeBusy) return;
    setRouteBusy(true); setRouteError("");
    try {
      await secureApi(`/api/compensation/visit-routes/${id}`,{method:"DELETE"});
      setRoutes(current=>current.filter(item=>item.id!==id));
    } catch { setRouteError("حذف ایستگاه برنامه ناموفق بود."); }
    finally { setRouteBusy(false); }
  };

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const user = await secureApi<Person>("/auth/me");
        if (!active) return;
        const isManager = ["ceo", "sales_manager"].includes(user.role);
        setManager(isManager); setPerson(String(user.id)); setPeople([user]);
        if (isManager) {
          try {
            const result = await secureApi<{users:Person[]}>("/tasks/assignees");
            if (active) setPeople([user, ...result.users.filter(p => p.id !== user.id && p.is_active !== false)]);
          } catch {
            if (active) setErrors(current => ({...current, people:"فهرست پرسنل دریافت نشد."}));
          }
        }
        if (active) setPeopleReady(true);
      } catch {
        if (active) {
          setErrors({identity:"دریافت برنامه ناموفق بود؛ اتصال و ورود را بررسی کنید."});
          setLoading(false);
        }
      }
    }
    void load();
    return () => { active = false; };
  }, []);

  const selected = people.find(p => String(p.id) === person);
  useEffect(() => {
    if (!person || !selected) return;
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      setLoading(true);
      setTasks([]); setTargets([]); setFollowups([]);
      setErrors(current => { const next = {...current}; delete next.tasks; delete next.targets; delete next.followups; return next; });
      const targetUrl = manager && selected.salesperson_id
        ? `/targets/person-targets?salesperson_id=${encodeURIComponent(String(selected.salesperson_id))}`
        : "/targets/person-targets";
      return Promise.allSettled([
        secureApi<{tasks:Task[]}>("/tasks"),
        secureApi<{items:Target[]}>(targetUrl),
        secureApi<Followup[]>("/crm/interactions"),
      ]).then(([taskResult,targetResult,followupResult]) => {
        if (!active) return;
        const next: Record<string,string> = {};
        if (taskResult.status === "fulfilled") setTasks(taskResult.value.tasks || []); else next.tasks = "وظایف دریافت نشد.";
        if (targetResult.status === "fulfilled") setTargets(targetResult.value.items || []); else next.targets = "هدف‌ها دریافت نشد.";
        if (followupResult.status === "fulfilled") setFollowups(followupResult.value || []); else next.followups = "پیگیری‌ها دریافت نشد.";
        setErrors(current => ({...current, ...next}));
        setLoading(false);
      });
    });
    return () => { active = false; };
  }, [person, manager, selected]);

  const ownTasks = tasks.filter(t => String(t.assigned_to) === person);
  const ownTargets = targets.filter(t => selected?.salesperson_id != null && t.salesperson_id === selected.salesperson_id && t.status === "active");
  const ownFollowups = followups.filter(f => selected && [selected.full_name, "@" + selected.username].includes(f.visitor_name));
  const openTasks = ownTasks.filter(t => t.status !== "completed");
  const today = localDate();
  const shownRoutes = manager || showAllRoutes ? routes : routes.filter(stop => stop.visit_date === today);
  function reloadFollowups() {
    void secureApi<Followup[]>("/crm/interactions").then(setFollowups).catch(() => {
      setErrors(current => ({ ...current, followups: "یادآوری ثبت شد، اما بازخوانی فهرست ناموفق بود." }));
    });
  }
  const overdue = openTasks.filter(t => t.due_date && t.due_date.slice(0,10) < today);

  return <PortalShell title={manager ? "برنامهٔ تیم" : "امروز من"} eyebrow="ویزیت و پیگیری مشتری">
    <div className="kskin space-y-5" dir="rtl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-400">برنامهٔ {selected?.full_name || "شما"} · {formatIranDate(new Date())}</p>
        {manager && <label className="flex items-center gap-3 text-sm text-slate-300">انتخاب پرسنل<select className={fieldClass} value={person} onChange={e=>setPerson(e.target.value)}>{people.map(p=><option key={p.id} value={p.id}>{p.full_name}</option>)}</select></label>}
      </div>
      {Object.values(errors).length > 0 && <div role="alert" className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-4 text-sm text-amber-200">{Object.values(errors).join(" ")} اطلاعات ناقص است؛ بخش‌های سالم همچنان نمایش داده می‌شوند.</div>}
      {manager && person && <VisitCoverage manager={manager} salespersonId={selected?.salesperson_id} />}
      {loading ? <Surface className="p-8 text-center text-slate-400">در حال دریافت برنامه…</Surface> : <>
        <Surface className="p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-bold text-white">{manager ? "برنامهٔ مسیر ویزیت" : "ویزیت‌های امروز"}</h2><p className="mt-2 text-xs text-slate-400">ایستگاه‌ها به‌ترتیب روز نمایش داده می‌شوند و تیک حضور همان روز به‌صورت خودکار کنار آن‌ها می‌آید.</p></div><Link className="text-sm text-violet-300" href="/map?view=bases">ثبت حضور پایگاه ←</Link></div>
          {routeError && <p role="alert" className="mt-3 text-sm text-amber-300">{routeError}</p>}
          {routePrefillMessage && <p role="status" className="mt-3 rounded-xl bg-indigo-500/10 p-3 text-sm leading-7 text-indigo-200">{routePrefillMessage}</p>}
          {manager && <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5"><IranDateInput aria-label="تاریخ ویزیت شمسی" className={fieldClass} value={routeDate} onChange={setRouteDate}/><select aria-label="پایگاه مسیر" className={fieldClass} value={routeBase} onChange={e=>setRouteBase(e.target.value)}><option value="">انتخاب پایگاه</option>{bases.map(b=><option key={`${b.source}:${b.id}`} value={`${b.source}:${b.id}`}>{b.name} — {b.city || "بدون شهر"}</option>)}</select><input aria-label="ترتیب ایستگاه" type="number" min="1" max="999" className={fieldClass} value={routeOrder} onChange={e=>setRouteOrder(e.target.value)}/><input aria-label="یادداشت مسیر" className={fieldClass} placeholder="یادداشت اختیاری" value={routeNote} onChange={e=>setRouteNote(e.target.value)}/><button type="button" disabled={routeBusy || !routeBase || !routeDate} onClick={assignRoute} className="rounded-xl bg-indigo-600 px-4 py-3 text-sm text-white disabled:opacity-40">{routeBusy ? "در حال ثبت…" : "افزودن به مسیر"}</button></div>}
          <div className="mt-4 space-y-3">{!manager && <button type="button" onClick={() => setShowAllRoutes(value => !value)} className="mb-2 text-sm text-violet-300">{showAllRoutes ? "فقط امروز" : "نمایش همهٔ روزها"}</button>}{shownRoutes.map(stop=><article key={stop.id} className="rounded-xl border border-white/10 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs text-violet-300">ایستگاه {number(stop.stop_order)} · {formatIranDate(stop.visit_date)}</div><h3 className="mt-2 text-sm font-bold text-white">{stop.base_name || "پایگاه حذف‌شده"}</h3><p className="mt-1 text-xs text-slate-400">{[stop.city,stop.address].filter(Boolean).join(" · ") || "نشانی ثبت نشده"}</p>{stop.note && <p className="mt-2 text-xs text-slate-300">{stop.note}</p>}{!manager && <Link href={`/map?view=bases&base_source=${encodeURIComponent(stop.base_source)}&base_id=${stop.base_id}`} className="mt-3 inline-block text-sm text-violet-300 underline">گزارش و ثبت حضور در این پایگاه ←</Link>}</div><div className="flex items-center gap-2">{stop.checkin_status ? <span className={`rounded-full px-3 py-1 text-xs ${stop.checkin_status==="verified" ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"}`}>{stop.checkin_status==="verified" ? "حضور تأیید شد" : stop.checkin_status==="outside_radius" ? "بیرون محدوده" : stop.checkin_status==="rejected" ? "حضور رد شد" : "نیازمند بررسی"}</span> : <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">حضور ثبت نشده</span>}{manager && <button type="button" disabled={routeBusy} onClick={()=>removeRoute(stop.id)} className="text-xs text-rose-300 disabled:opacity-40">حذف</button>}</div>
          {!manager && <StopActions stop={stop} today={today} onOutcome={status => setRoutes(current => current.map(item => item.id === stop.id ? {...item, outcome_status: status} : item))} onReminder={reloadFollowups} />}
          </div></article>)}{!shownRoutes.length && !routeError && <p className="text-sm text-slate-400">{manager || showAllRoutes ? "مسیر ویزیتی دریافت نشد." : "برای امروز توقفی در برنامه نیست."}</p>}</div>
        </Surface>
        <div className="grid gap-3 sm:grid-cols-3">{[["وظایف باز",openTasks.length,"tasks"],["عقب‌افتاده",overdue.length,"tasks"],["پیگیری سررسیدشده",ownFollowups.filter(f=>f.is_due && !["سفارش ثبت شد","عدم تمایل فعلی"].includes(f.status)).length,"followups"]].map(([label,count,source])=><Surface key={String(label)} className="p-5"><div className="text-sm text-slate-400">{label}</div><div className="mt-3 text-2xl font-bold text-white">{errors[String(source)] ? "—" : number(Number(count))}</div></Surface>)}</div>
        <Surface className="p-5"><div className="flex justify-between gap-3"><h2 className="font-bold text-white">وظایف و سررسیدها</h2><Link className="text-sm text-violet-300" href="/tasks">مدیریت وظایف ←</Link></div>{errors.tasks && <p role="alert" className="mt-3 text-sm text-amber-300">{errors.tasks}</p>}<div className="mt-4 space-y-3">{ownTasks.map(t=><article key={t.id} className="rounded-xl border border-white/10 p-4"><div className="flex flex-wrap justify-between gap-2"><h3 className="text-sm text-white">{t.title}</h3><span className="text-xs text-violet-300">{statuses[t.review_status || ""] || statuses[t.status] || t.status}</span></div><p className="mt-2 text-xs text-slate-400">{t.due_date ? formatIranDate(t.due_date) : "بدون سررسید"} · پیشرفت {number(t.progress)}٪</p></article>)}{!ownTasks.length && !errors.tasks && <p className="text-sm text-slate-400">وظیفه‌ای برای این حساب دریافت نشد.</p>}</div></Surface>
        <div className="grid gap-5 lg:grid-cols-2"><Surface className="p-5"><h2 className="font-bold text-white">هدف‌های فعال</h2>{errors.targets && <p role="alert" className="mt-3 text-sm text-amber-300">{errors.targets}</p>}{ownTargets.map(t=><article key={t.id} className="mt-4 border-t border-white/10 pt-4"><h3 className="text-sm text-white">{t.title}</h3><p className="mt-2 text-sm text-violet-300">{number(Number(t.target_amount))} ریال</p><p className="mt-1 text-xs text-slate-400">{t.start_date && t.end_date ? `${formatIranDate(t.start_date)} تا ${formatIranDate(t.end_date)}` : "بازهٔ معتبر ثبت نشده؛ تحقق قابل محاسبه نیست."}</p></article>)}{!ownTargets.length && !errors.targets && <p className="mt-4 text-sm text-slate-400">هدف شخصی فعالی دریافت نشد.</p>}</Surface>
        <Surface className="p-5"><h2 className="font-bold text-white">پیگیری مشتریان</h2>{errors.followups && <p role="alert" className="mt-3 text-sm text-amber-300">{errors.followups}</p>}{ownFollowups.map(f=><article key={f.id} className="mt-4 border-t border-white/10 pt-4"><h3 className="text-sm text-white">{f.customer_name}</h3><p className="mt-2 text-xs leading-6 text-slate-400">{f.notes}</p><p className="mt-2 text-xs text-violet-300">{f.status} · {f.next_date || "بدون تاریخ"}</p></article>)}{!ownFollowups.length && !errors.followups && <p className="mt-4 text-sm text-slate-400">پیگیری منتسب به این حساب دریافت نشد.</p>}</Surface></div>
        <Surface className="p-5"><h2 className="font-bold text-white">دسترسی‌های روزانه</h2><div className="mt-4 flex flex-wrap gap-3">{[["ثبت گزارش صوتی","/voice-report"],["ثبت بازدید پایگاه","/map?view=bases"],["دستیار هوشمند","/assistant"],["پیش‌فاکتورها","/proformas"]].map(([label,href])=><Link key={href} href={href} className="rounded-xl border border-white/10 px-4 py-3 text-sm text-violet-300">{label}</Link>)}</div><p className="mt-4 text-xs leading-6 text-slate-400">پیگیری‌های مشتری بر اساس نام یا شناسهٔ حساب تطبیق داده می‌شوند؛ موارد قدیمی با نام متفاوت ممکن است نمایش داده نشوند.</p></Surface>
        <Surface className="p-5"><h2 className="font-bold text-white">کمپین‌های تخصیص‌یافته</h2>
          {campaignError && <p role="alert" className="mt-3 text-sm text-amber-300">{campaignError}</p>}
          {manager && <div className="mt-4 flex flex-wrap gap-3"><select aria-label="کمپین قابل تخصیص" className={fieldClass} disabled={assigning} value={campaignId} onChange={e=>setCampaignId(e.target.value)}><option value="">انتخاب کمپین فعال</option>{choices.map(c=><option key={c.id} value={c.id}>{c.title}</option>)}</select><button type="button" disabled={assigning || !campaignId} onClick={assign} className="rounded-xl bg-indigo-600 px-4 py-3 text-sm text-white disabled:opacity-40">{assigning ? "در حال تخصیص…" : "تخصیص به فرد انتخاب‌شده"}</button></div>}
          {campaigns.map(c=><article key={c.id} className="mt-4 rounded-xl border border-white/10 p-4"><h3 className="text-sm font-bold text-white">{c.title}</h3><p className="mt-2 text-sm leading-7 text-slate-400">{c.description || "بدون توضیح"}</p><p className="mt-2 text-xs text-violet-300">{c.is_active ? "فعال" : "بسته‌شده"} · پایان: {formatIranDate(c.ends_at)}</p></article>)}
          {!campaigns.length && !campaignError && <p className="mt-4 text-sm text-slate-400">کمپینی برای این حساب دریافت نشد.</p>}
        </Surface>
      </>}
    </div>
  </PortalShell>;
}
