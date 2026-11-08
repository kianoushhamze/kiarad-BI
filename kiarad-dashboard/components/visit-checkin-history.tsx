"use client";

import { useCallback, useEffect, useState } from "react";
import { secureApi } from "../lib/secure-api";
import { Surface, fieldClass, primaryButton } from "./portal-shell";
import { formatIranDateTime } from "../lib/iran-date";

type Checkin = { id:number; salesperson_id:number; salesperson_name:string; base_name:string; status:string; checked_in_at:string; distance_m?:number | null; accuracy_m?:number | null; note?:string; review_note?:string; reviewer_name?:string; reviewed_at?:string; original_status?:string };
const labels:Record<string,string>={verified:"حضور تأییدشده",outside_radius:"بیرون محدوده",pending_review:"نیازمند بررسی",rejected:"حضور ردشده"};
const meters=(value:number | null | undefined)=>value==null ? "نامشخص" : `${Number(value).toLocaleString("fa-IR")} متر`;

export function VisitCheckinHistory({manager,salespersonId,reloadKey}:{manager:boolean;salespersonId?:number | null;reloadKey:number}) {
  const [items,setItems]=useState<Checkin[]>([]);
  const [filter,setFilter]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [notes,setNotes]=useState<Record<number,string>>({});
  const [refreshVersion,setRefreshVersion]=useState(0);
  const load=useCallback(async()=>{
    const result=await secureApi<{items:Checkin[]}>(`/api/compensation/base-checkins?limit=100${filter ? `&status=${encodeURIComponent(filter)}` : ""}`);
    return result.items;
  },[filter]);
  useEffect(()=>{
    let active=true;
    void Promise.resolve().then(()=>{
      if(!active)return;
      setLoading(true);setError("");setItems([]);
      return load().then(result=>{if(active)setItems(result);}).catch(reason=>{if(active)setError(reason instanceof Error ? reason.message : "دریافت حضورها ناموفق بود.");}).finally(()=>{if(active)setLoading(false);});
    });
    return ()=>{active=false;};
  },[load,reloadKey,refreshVersion]);
  const review=async(item:Checkin,decision:string)=>{
    if(busy)return;
    const note=(notes[item.id]||"").trim();
    if(!note){setError("علت تصمیم مدیر را بنویسید.");return;}
    setBusy(true);setError("");setMessage("");
    try{
      await secureApi(`/api/compensation/base-checkins/${item.id}/review`,{method:"POST",body:JSON.stringify({decision,note})});
      setMessage(decision==="verified" ? "حضور با ثبت علت تأیید شد." : "حضور با ثبت علت رد شد.");
      setNotes(current=>({...current,[item.id]:""}));setItems(await load());
    }catch(reason){setError(reason instanceof Error ? reason.message : "بررسی حضور ناموفق بود.");}
    finally{setBusy(false);}
  };
  return <Surface className="mb-5 p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-bold text-white">{manager ? "بررسی حضور و گزارش بازدید" : "سابقهٔ حضور و گزارش‌های من"}</h2><label className="flex items-center gap-2 text-xs text-slate-300">وضعیت<select disabled={busy} className={fieldClass} value={filter} onChange={e=>setFilter(e.target.value)}><option value="">همه</option>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div>
    <p className="mt-3 text-xs leading-6 text-slate-400">آخرین ۱۰۰ حضور مطابق فیلتر نمایش داده می‌شود. بررسی مدیر همراه علت و نام بررسی‌کننده نگهداری می‌شود.</p>
    <button type="button" disabled={loading || busy} onClick={()=>setRefreshVersion(value=>value+1)} className="mt-3 text-sm text-violet-300 underline disabled:opacity-40">تازه‌سازی حضورها</button>
    {error && <p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}
    {message && <p role="status" className="mt-3 text-sm text-emerald-300">{message}</p>}
    {loading ? <p className="mt-4 text-sm text-slate-400">در حال دریافت حضورها…</p> : <div className="mt-4 space-y-4">{items.map(item=><article key={item.id} className="rounded-xl border border-white/10 p-4">
      <div className="flex flex-wrap justify-between gap-3"><h3 className="text-sm font-bold text-white">{item.base_name}</h3><span className="text-xs text-violet-300">{labels[item.status] || "نیازمند بررسی"}</span></div>
      <p className="mt-2 text-xs text-slate-400">{item.salesperson_name} · {formatIranDateTime(item.checked_in_at)}</p>
      <p className="mt-2 text-xs text-slate-400">فاصله از مرجع: {meters(item.distance_m)} · دقت دستگاه: {meters(item.accuracy_m)}</p>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200">{item.note || "برای این حضور قدیمی گزارش ثبت نشده است."}</p>
      {item.review_note && <div className="mt-3 rounded-xl bg-white/5 p-3 text-xs leading-7 text-slate-300"><p className="whitespace-pre-wrap">نظر مدیر: {item.review_note}</p><p>{item.reviewer_name} · وضعیت اولیه: {labels[item.original_status || ""] || "نامشخص"}{item.reviewed_at ? ` · ${formatIranDateTime(item.reviewed_at)}` : ""}</p></div>}
      {manager && item.salesperson_id!==salespersonId && ["pending_review","outside_radius"].includes(item.status) && <div className="mt-4 space-y-3"><label className="block text-sm text-slate-300">علت تأیید یا رد<textarea disabled={busy} maxLength={2000} rows={2} value={notes[item.id]||""} onChange={e=>setNotes(current=>({...current,[item.id]:e.target.value}))} className={`${fieldClass} mt-2`}/></label><div className="flex flex-wrap gap-3"><button type="button" disabled={busy} onClick={()=>review(item,"verified")} className={primaryButton}>تأیید حضور</button><button type="button" disabled={busy} onClick={()=>review(item,"rejected")} className="rounded-xl border border-rose-500/30 px-4 py-2 text-sm text-rose-300 disabled:opacity-40">رد حضور</button></div></div>}
    </article>)}{!items.length && !error && <p className="text-sm text-slate-400">حضوری با این وضعیت ثبت نشده است.</p>}</div>}
  </Surface>;
}
