"use client";
import { useCallback, useEffect, useState } from "react";
import { PortalShell, Surface, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
import { formatIranDateTime } from "../../lib/iran-date";

type Automation={
  id:number;name:string;prompt:string;enabled:boolean;
  schedule_type:"interval"|"daily";interval_hours:number|null;daily_time:string|null;
  weekdays:number[]|null;next_run_at:string|null;last_run_at:string|null;
  schedule_label?:string;
  last_run?:{status:string;finished_at:string|null}|null;
};
type Run={id:number;status:string;summary:string|null;proposals:unknown;started_at:string;finished_at:string|null};

const WEEKDAYS=[["شنبه",5],["یکشنبه",6],["دوشنبه",0],["سه‌شنبه",1],["چهارشنبه",2],["پنجشنبه",3],["جمعه",4]] as const;
const statusLabel:Record<string,string>={completed:"موفق",failed:"ناموفق",no_answer:"بدون پاسخ معتبر"};
const statusClass:Record<string,string>={completed:"text-emerald-300",failed:"text-rose-300",no_answer:"text-amber-300"};

export default function AssistantAutomationsPage(){
  const [items,setItems]=useState<Automation[]>([]);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [runsFor,setRunsFor]=useState<Automation|null>(null);
  const [runs,setRuns]=useState<Run[]>([]);
  const [form,setForm]=useState({name:"",prompt:"",schedule_type:"interval" as "interval"|"daily",
    interval_hours:6,daily_time:"08:30",weekdays:[5,6,0,1,2,3] as number[]});

  const load=useCallback(function(){
    secureApi<{items:Automation[]}>("/assistant/automations")
      .then(v=>{setItems(v.items);setError("");})
      .catch(r=>setError(r instanceof Error?r.message:"فهرست دریافت نشد."));
  },[]);

  useEffect(function(){load();},[load]);

  async function create(){
    if(busy)return;setBusy(true);setError("");
    try{
      const body:Record<string,unknown>={name:form.name.trim(),prompt:form.prompt.trim(),schedule_type:form.schedule_type};
      if(form.schedule_type==="interval")body.interval_hours=form.interval_hours;
      else {body.daily_time=form.daily_time;body.weekdays=form.weekdays;}
      await secureApi("/assistant/automations",{method:"POST",body:JSON.stringify(body)});
      setForm({...form,name:"",prompt:""});load();
    }catch(r){setError(r instanceof Error?r.message:"ایجاد اتوماسیون انجام نشد.");}
    finally{setBusy(false);}
  }
  async function toggle(item:Automation){
    setBusy(true);setError("");
    try{await secureApi("/assistant/automations/"+item.id,{method:"PATCH",body:JSON.stringify({enabled:!item.enabled})});load();}
    catch(r){setError(r instanceof Error?r.message:"تغییر وضعیت انجام نشد.");}
    finally{setBusy(false);}
  }
  async function remove(item:Automation){
    if(!window.confirm(`اتوماسیون «${item.name}» و تاریخچهٔ آن حذف شود؟`))return;
    setBusy(true);setError("");
    try{await secureApi("/assistant/automations/"+item.id,{method:"DELETE"});load();}
    catch(r){setError(r instanceof Error?r.message:"حذف انجام نشد.");}
    finally{setBusy(false);}
  }
  async function runNow(item:Automation){
    setBusy(true);setError("");
    try{await secureApi("/assistant/automations/"+item.id+"/run",{method:"POST"});load();}
    catch(r){setError(r instanceof Error?r.message:"اجرای دستی ناموفق بود.");}
    finally{setBusy(false);}
  }
  function openRuns(item:Automation){
    setRunsFor(item);setRuns([]);
    secureApi<{items:Run[]}>(`/assistant/automations/${item.id}/runs`)
      .then(v=>setRuns(v.items))
      .catch(r=>setError(r instanceof Error?r.message:"تاریخچه دریافت نشد."));
  }

  return <PortalShell title="اتوماسیون‌های دستیار" eyebrow="ایجنت خودکار کیاراد">
    <div className="mx-auto max-w-4xl space-y-5 p-4 lg:p-6">
      {error&&<p role="alert" className="text-rose-300">{error}</p>}
      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">اتوماسیون جدید بساز</h2>
        <p className="text-xs text-slate-400">
          دستیار در زمان‌های تعیین‌شده با دسترسی کامل خواندنِ پنل دستور تو را اجرا می‌کند و خلاصه را اعلان می‌کند.
          هر اقدام نوشتنی فقط به‌صورت پیشنهاد ثبت می‌شود و تنها با تأیید تو در صفحهٔ «بازبینی عملیات دستیار» اعمال می‌گردد.
        </p>
        <input className="w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2.5 text-sm" placeholder="نام اتوماسیون، مثلاً: گزارش صبحگاهی فروش"
          value={form.name} onChange={e=>setForm({...form,name:e.target.value})} maxLength={120}/>
        <textarea className="min-h-[96px] w-full rounded-xl border border-white/10 bg-black/30 px-4 py-2.5 text-sm" maxLength={4000}
          placeholder="دستور، مثلاً: وضعیت فروش امروز و مانده‌های مشتریان را خلاصه کن و اگر وظیفهٔ پیگیری لازم است پیشنهاد بساز."
          value={form.prompt} onChange={e=>setForm({...form,prompt:e.target.value})}/>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2"><input type="radio" checked={form.schedule_type==="interval"} onChange={()=>setForm({...form,schedule_type:"interval"})}/>هر چند ساعت</label>
          <label className="flex items-center gap-2"><input type="radio" checked={form.schedule_type==="daily"} onChange={()=>setForm({...form,schedule_type:"daily"})}/>روزانه در ساعت مشخص</label>
        </div>
        {form.schedule_type==="interval"
          ?<label className="flex items-center gap-2 text-sm">فاصله (ساعت، ۱ تا ۱۶۸):
              <input type="number" min={1} max={168} className="w-24 rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm"
                value={form.interval_hours} onChange={e=>setForm({...form,interval_hours:Number(e.target.value)||1})}/></label>
          :<div className="space-y-2 text-sm">
              <label className="flex items-center gap-2">ساعت (تهران):
                <input type="time" className="rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-sm"
                  value={form.daily_time} onChange={e=>setForm({...form,daily_time:e.target.value})}/></label>
              <div className="flex flex-wrap gap-2">
                {WEEKDAYS.map(([label,d])=>
                  <label key={d} className="flex cursor-pointer items-center gap-1 rounded-lg border border-white/10 px-2.5 py-1 text-xs">
                    <input type="checkbox" checked={form.weekdays.includes(d)}
                      onChange={e=>setForm({...form,weekdays:e.target.checked?[...form.weekdays,d]:form.weekdays.filter(x=>x!==d)})}/>
                    {label}</label>)}
              </div>
            </div>}
        <button className={primaryButton} disabled={busy||form.name.trim().length<2||form.prompt.trim().length<5} onClick={()=>void create()}>
          {busy?"در حال ثبت…":"ایجاد اتوماسیون"}</button>
      </Surface>

      <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">اتوماسیون‌های من</h2>
        {items.length===0?<p className="text-sm text-slate-400">هنوز اتوماسیونی نساخته‌ای.</p>
          :<div className="space-y-3">
            {items.map(item=><div key={item.id} className="rounded-xl border border-white/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <b className="text-sm">{item.name}</b>
                <span className={item.enabled?"text-xs text-emerald-300":"text-xs text-slate-500"}>{item.enabled?"فعال":"غیرفعال"}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-xs text-slate-400">{item.prompt}</p>
              <p className="mt-2 text-xs text-slate-400">زمان‌بندی: {item.schedule_label ?? (item.schedule_type==="interval"?`هر ${item.interval_hours} ساعت`:`روزانه ${item.daily_time??""}`)}</p>
              <p className="text-xs text-slate-400">
                اجرای بعدی: {item.next_run_at?formatIranDateTime(item.next_run_at):"—"}
                {item.last_run?.status&&<> · آخرین اجرا: <span className={statusClass[item.last_run.status]??""}>{statusLabel[item.last_run.status]??item.last_run.status}</span></>}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <button className="rounded-lg border border-white/10 px-3 py-1.5" disabled={busy} onClick={()=>void runNow(item)}>اجرا در همین لحظه</button>
                <button className="rounded-lg border border-white/10 px-3 py-1.5" disabled={busy} onClick={()=>void toggle(item)}>{item.enabled?"غیرفعال کن":"فعال کن"}</button>
                <button className="rounded-lg border border-white/10 px-3 py-1.5" onClick={()=>openRuns(item)}>تاریخچه</button>
                <button className="rounded-lg border border-rose-500/30 px-3 py-1.5 text-rose-300" disabled={busy} onClick={()=>void remove(item)}>حذف</button>
              </div>
            </div>)}
          </div>}
      </Surface>

      {runsFor&&<Surface className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold">تاریخچه: {runsFor.name}</h2>
          <button className="text-xs text-slate-400" onClick={()=>setRunsFor(null)}>بستن</button>
        </div>
        {runs.length===0?<p className="text-sm text-slate-400">اجرایی ثبت نشده است.</p>
          :runs.map(run=><div key={run.id} className="rounded-xl border border-white/10 p-4 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className={statusClass[run.status]??""}>{statusLabel[run.status]??run.status}</span>
              <span className="text-xs text-slate-500">{formatIranDateTime(run.started_at)}</span>
            </div>
            {run.summary&&<p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-slate-300">{run.summary}</p>}
            {Array.isArray(run.proposals)&&run.proposals.length>0&&
              <div className="mt-2 space-y-1">
                {(run.proposals as Array<{label?:string;href?:string}>).map((p,i)=>
                  <a key={i} href={p.href||"/assistant-actions"} className="block text-violet-300 text-xs">پیشنهاد در انتظار تأیید: {p.label||"مشاهده"}</a>)}
              </div>}
          </div>)}
      </Surface>}
      <a href="/assistant" className="block text-violet-300">بازگشت به دستیار</a>
    </div>
  </PortalShell>;
}
