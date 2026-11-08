"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi, type SessionUser } from "../../lib/secure-api";
import { formatIranDateTime, iranDateTimeInputToIso } from "../../lib/iran-date";
import { IranDateTimeInput } from "../../components/IranDateTimeInput";

type Task = { id: number; title: string; description?: string; priority: string; status: string; progress: number; assigned_to: number; assignee_name: string; due_date?: string; review_status: string; review_note?: string };
type Person = { id: number; full_name: string };
type Update = { id: number; author_name: string; progress: number; status: string; note?: string; created_at: string };
const labels: Record<string,string> = { new:"جدید", in_progress:"در حال انجام", completed:"گزارش پایان کار", blocked:"متوقف", approved:"تأیید مدیر", pending:"منتظر بررسی مدیر", changes_requested:"برگشت برای اصلاح", low:"کم", normal:"عادی", high:"بالا", urgent:"فوری" };
const taskLabel = (task:Task) => labels[task.review_status] || labels[task.status] || task.status;

export default function TasksPage() {
  const [session,setSession] = useState<SessionUser | null>(null);
  const [tasks,setTasks] = useState<Task[]>([]);
  const [people,setPeople] = useState<Person[]>([]);
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [message,setMessage] = useState("");
  const [showCreate,setShowCreate] = useState(false);
  const [notes,setNotes] = useState<Record<number,string>>({});
  const [progress,setProgress] = useState<Record<number,number>>({});
  const [history,setHistory] = useState<Record<number,Update[]>>({});
  const [expanded,setExpanded] = useState<number | null>(null);
  const [filter,setFilter] = useState("all");
  const manager = !!session && ["ceo","sales_manager"].includes(session.role);
  const loadTasks = useCallback(async () => {
    const result = await secureApi<{tasks:Task[]}>("/tasks");
    setTasks(result.tasks);
  },[]);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const user = await secureApi<SessionUser>("/auth/me");
        if (!active) return;
        setSession(user);
        const result = await secureApi<{tasks:Task[]}>("/tasks");
        if (!active) return;
        setTasks(result.tasks);
        if (["ceo","sales_manager"].includes(user.role)) {
          const assignees = await secureApi<{users:Person[]}>("/tasks/assignees");
          if (active) setPeople(assignees.users);
        }
      } catch(reason) { if(active) setError(reason instanceof Error ? reason.message : "دریافت کارها ناموفق بود."); }
      finally { if(active) setLoading(false); }
    }
    void load();
    return () => { active=false; };
  },[]);

  const showHistory = async (id:number) => {
    if (busy) return;
    if (expanded === id) { setExpanded(null); return; }
    setBusy(true); setError("");
    try {
      const result=await secureApi<{items:Update[]}>(`/tasks/${id}/updates`);
      setHistory(current=>({...current,[id]:result.items})); setExpanded(id);
    } catch(reason) { setError(reason instanceof Error ? reason.message : "دریافت سابقه ناموفق بود."); }
    finally { setBusy(false); }
  };
  const change = async (task:Task,status:string,amount:number) => {
    if (busy) return;
    const note=(notes[task.id] || "").trim();
    if (["completed","blocked"].includes(status) && !note) { setError("نتیجهٔ کار یا علت توقف را بنویسید."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      await secureApi(`/tasks/${task.id}/progress`,{method:"PATCH",body:JSON.stringify({status,progress:amount,note:note || null})});
      setMessage(status==="completed" ? "گزارش پایان کار برای بررسی مدیر ارسال شد." : "پیشرفت و گزارش کار ذخیره شد.");
      setNotes(current=>({...current,[task.id]:""})); setExpanded(null); await loadTasks();
    } catch(reason) { setError(reason instanceof Error ? reason.message : "ذخیرهٔ گزارش ناموفق بود."); }
    finally { setBusy(false); }
  };
  const review = async (task:Task,decision:string) => {
    if (busy) return;
    const note=(notes[task.id] || "").trim();
    if (decision==="changes_requested" && !note) { setError("علت برگشت کار را بنویسید."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      await secureApi(`/tasks/${task.id}/review`,{method:"POST",body:JSON.stringify({decision,note:note || null})});
      setMessage(decision==="approved" ? "کار تأیید شد." : "کار با توضیح شما برای اصلاح برگشت داده شد.");
      setNotes(current=>({...current,[task.id]:""})); setExpanded(null); await loadTasks();
    } catch(reason) { setError(reason instanceof Error ? reason.message : "ثبت بررسی ناموفق بود."); }
    finally { setBusy(false); }
  };
  const create = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault(); if(busy) return;
    const form=new FormData(event.currentTarget);
    setBusy(true); setError(""); setMessage("");
    try {
      const dueDateValue = String(form.get("due_date") || "");
      const dueDate = dueDateValue ? iranDateTimeInputToIso(dueDateValue) : null;
      if (dueDateValue && !dueDate) throw new Error("تاریخ و ساعت سررسید معتبر نیست.");
      await secureApi("/tasks",{method:"POST",body:JSON.stringify({title:form.get("title"),description:form.get("description") || null,priority:form.get("priority"),assigned_to:Number(form.get("assigned_to")),due_date:dueDate})});
      setShowCreate(false); setMessage("کار ثبت و به پرسنل تخصیص داده شد."); await loadTasks();
    } catch(reason) { setError(reason instanceof Error ? reason.message : "ایجاد کار ناموفق بود."); }
    finally { setBusy(false); }
  };
  const displayed=tasks.filter(task=>filter==="pending" ? task.review_status==="pending" : filter==="approved" ? task.review_status==="approved" : filter==="open" ? task.status!=="completed" : true);

  return <PortalShell title="کارها و گزارش عملکرد" eyebrow="تخصیص، گزارش و بررسی مدیر" actions={manager && <button disabled={busy || loading} onClick={()=>setShowCreate(true)} className={primaryButton}>ایجاد کار</button>}>
    {error && <div role="alert" className="mb-4 rounded-xl bg-rose-500/10 p-4 text-sm text-rose-200">{error}</div>}
    {message && <div role="status" className="mb-4 rounded-xl bg-emerald-500/10 p-4 text-sm text-emerald-200">{message}</div>}
    <p className="mb-4 text-sm leading-7 text-slate-400">پرسنل نتیجهٔ کار را گزارش می‌کند؛ مدیر آن را تأیید می‌کند یا با توضیح برای اصلاح برمی‌گرداند.</p>
    <div className="grid gap-3 sm:grid-cols-3">{[["کار باز",tasks.filter(t=>t.status!=="completed").length],["منتظر بررسی",tasks.filter(t=>t.review_status==="pending").length],["تأییدشده",tasks.filter(t=>t.review_status==="approved").length]].map(([label,count])=><Surface key={String(label)} className="p-4"><div className="text-xs text-slate-400">{label}</div><div className="mt-3 text-2xl font-bold text-white">{loading ? "…" : error ? "—" : Number(count).toLocaleString("fa-IR")}</div></Surface>)}</div>
    <label className="my-4 flex items-center gap-3 text-sm text-slate-300">نمایش<select className={fieldClass} value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">همهٔ کارها</option><option value="open">کارهای باز</option><option value="pending">منتظر بررسی مدیر</option><option value="approved">تأییدشده‌ها</option></select></label>
    {loading ? <Surface className="p-8 text-slate-400">در حال دریافت کارها…</Surface> : <div className="space-y-4">{displayed.map(task=>{
      const editable=task.assigned_to===session?.id && !["pending","approved"].includes(task.review_status);
      const canReview=manager && task.review_status==="pending" && task.assigned_to!==session?.id;
      return <Surface key={task.id} className="p-5">
        <div className="flex flex-wrap justify-between gap-3"><h2 className="font-bold text-white">{task.title}</h2><span className="text-sm text-violet-300">{taskLabel(task)}</span></div>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-300">{task.description || "بدون شرح"}</p>
        <p className="mt-3 text-xs text-slate-400">{task.assignee_name} · اولویت {labels[task.priority]} · {task.progress.toLocaleString("fa-IR")}٪ · {task.due_date ? formatIranDateTime(task.due_date) : "بدون سررسید"}</p>
        {task.review_note && <p className="mt-3 whitespace-pre-wrap rounded-xl bg-amber-500/10 p-3 text-sm text-amber-200">نظر مدیر: {task.review_note}</p>}
        <button disabled={busy} onClick={()=>showHistory(task.id)} className="mt-4 text-sm text-violet-300 underline disabled:opacity-40">{expanded===task.id ? "بستن سابقه" : "مشاهدهٔ گزارش‌ها و سابقه"}</button>
        {expanded===task.id && <ol className="mt-3 space-y-3">{history[task.id]?.map(item=><li key={item.id} className="rounded-xl border border-white/10 p-3"><div className="text-xs text-slate-400">{item.author_name} · {labels[item.status] || item.status} · {formatIranDateTime(item.created_at)}</div><p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-200">{item.note || "تغییر پیشرفت"}</p></li>)}{!history[task.id]?.length && <li className="text-sm text-slate-400">هنوز گزارشی ثبت نشده است.</li>}</ol>}
        {(editable || canReview) && <div className="mt-4 space-y-3"><label className="block text-sm text-slate-300">{canReview ? "نظر بررسی مدیر" : "گزارش نتیجه یا مانع کار"}<textarea aria-label={canReview ? "نظر بررسی مدیر" : "گزارش کار"} maxLength={5000} rows={3} className={`${fieldClass} mt-2`} value={notes[task.id] || ""} onChange={e=>setNotes(current=>({...current,[task.id]:e.target.value}))}/></label>
          {editable && <><label className="flex items-center gap-3 text-sm text-slate-300">پیشرفت<select className={fieldClass} value={progress[task.id] ?? Math.min(task.progress,99)} onChange={e=>setProgress(current=>({...current,[task.id]:Number(e.target.value)}))}>{Array.from(new Set([0,25,50,75,Math.min(task.progress,99)])).sort((a,b)=>a-b).map(value=><option key={value} value={value}>{value.toLocaleString("fa-IR")}٪</option>)}</select></label><div className="flex flex-wrap gap-3"><button disabled={busy} onClick={()=>change(task,"in_progress",progress[task.id] ?? Math.min(task.progress,99))} className={primaryButton}>ذخیرهٔ پیشرفت</button><button disabled={busy} onClick={()=>change(task,"blocked",progress[task.id] ?? Math.min(task.progress,99))} className="rounded-xl border border-amber-500/30 px-4 py-2 text-sm text-amber-200 disabled:opacity-40">ثبت مانع</button><button disabled={busy} onClick={()=>change(task,"completed",100)} className="rounded-xl bg-emerald-600 px-4 py-2 text-sm text-white disabled:opacity-40">ارسال گزارش پایان کار</button></div></>}
          {canReview && <div className="flex flex-wrap gap-3"><button disabled={busy} onClick={()=>review(task,"approved")} className={primaryButton}>تأیید نتیجهٔ کار</button><button disabled={busy} onClick={()=>review(task,"changes_requested")} className="rounded-xl border border-amber-500/30 px-4 py-2 text-sm text-amber-200 disabled:opacity-40">برگشت برای اصلاح</button></div>}
        </div>}
      </Surface>;
    })}{!displayed.length && !error && <Surface className="p-8 text-sm text-slate-400">کاری در این فهرست نیست.</Surface>}</div>}
    {showCreate && <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/70 p-4"><form onSubmit={create} className="w-full max-w-lg space-y-4 rounded-3xl border border-white/10 bg-[#0c0e19] p-5"><div className="flex justify-between text-white"><h2>ایجاد و تخصیص کار</h2><button type="button" disabled={busy} onClick={()=>setShowCreate(false)}>بستن</button></div>{error && <p role="alert" className="text-sm text-rose-300">{error}</p>}<input aria-label="عنوان کار" name="title" required minLength={2} maxLength={200} placeholder="عنوان کار" className={fieldClass}/><textarea aria-label="شرح کار" name="description" rows={3} placeholder="شرح کار و نتیجهٔ مورد انتظار" className={fieldClass}/><select aria-label="پرسنل مسئول" name="assigned_to" required className={fieldClass}><option value="">انتخاب پرسنل</option>{people.map(person=><option key={person.id} value={person.id}>{person.full_name}</option>)}</select>{!people.length && <p className="text-sm text-amber-200">حساب فعال فروشنده یا ویزیتور پیدا نشد؛ ابتدا حساب پرسنل را تعریف کنید.</p>}<select aria-label="اولویت" name="priority" defaultValue="normal" className={fieldClass}><option value="normal">عادی</option><option value="high">بالا</option><option value="urgent">فوری</option><option value="low">کم</option></select><label className="block text-sm text-slate-300">سررسید<IranDateTimeInput name="due_date" className={`${fieldClass} mt-2`} /></label><button disabled={busy || !people.length} className={`${primaryButton} w-full`}>{busy ? "در حال ثبت…" : "ثبت و تخصیص"}</button></form></div>}
  </PortalShell>;
}
