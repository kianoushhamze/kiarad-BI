"use client";

import {useEffect,useMemo,useState} from "react";
import {PortalShell,Surface,fieldClass,primaryButton} from "../../components/portal-shell";
import {secureApi} from "../../lib/secure-api";
import ReconciliationPanel, {type ReconciliationData} from "../../components/ReconciliationPanel";
import {IranDateInput} from "../../components/IranDateInput";
import {formatIranDate,jalaliDateInputToIso,iranTodayIso} from "../../lib/iran-date";

type Base={id:number;source:string;name:string;city?:string};
type Stop={visit_date:string;base_source:string;base_id:number;stop_order:number;objective:string;base_name?:string;start_time?:string|null;end_time?:string|null;verified_visit?:boolean;has_daily_report?:boolean;conflict?:boolean;conflict_with?:string|null;locked_for_revision?:boolean};
type Plan={id:number;user_id:number;month:string;revision:number;status:string;full_name?:string;note:string};
type Summary={planned_stops:number;verified_stops:number;planned_days:number;conflicts:number;timed_stops:number;fully_completed_days:number};
type Detail={plan:Plan;stops:Stop[];summary:Summary;history:{event:string;note:string}[]};
const states:Record<string,string>={draft:"پیش‌نویس",submitted:"منتظر تأیید مدیرعامل",approved:"برنامهٔ اجرایی مصوب",returned:"برگشت برای اصلاح",superseded:"نسخهٔ قبلی؛ جایگزین شده",shared_visit_approved:"اجازهٔ ویزیت مشترک",history_retained:"انتقال سابقه"};
function nextMonth(){const parts=new Intl.DateTimeFormat("en-US-u-ca-persian",{year:"numeric",month:"2-digit",timeZone:"Asia/Tehran"}).formatToParts(new Date());let y=Number(parts.find(p=>p.type==="year")?.value),m=Number(parts.find(p=>p.type==="month")?.value)+1;if(m===13){y++;m=1;}return `${y}-${String(m).padStart(2,"0")}`;}
const weekdays=["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنجشنبه","جمعه"];
const keyOf=(s:Stop)=>`${s.base_source}:${s.base_id}`;
const timeInput="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-white";

export default function MonthlyPlans(){
 const [month,setMonth]=useState(nextMonth),[person,setPerson]=useState(""),[users,setUsers]=useState<{id:number;full_name:string}[]>([]),[bases,setBases]=useState<Base[]>([]),[selected,setSelected]=useState<string[]>([]),[weekday,setWeekday]=useState("0"),[single,setSingle]=useState(""),[weekly,setWeekly]=useState(true),[objective,setObjective]=useState("ویزیت و ثبت نتیجهٔ پیگیری"),[stops,setStops]=useState<Stop[]>([]),[plans,setPlans]=useState<Plan[]>([]),[detail,setDetail]=useState<Detail|null>(null),[note,setNote]=useState(""),[reviewNote,setReviewNote]=useState(""),[allowShared,setAllowShared]=useState(false),[message,setMessage]=useState(""),[busy,setBusy]=useState(false),[canApprove,setCanApprove]=useState(false),[workDate,setWorkDate]=useState(""),[credit,setCredit]=useState("1");
 const draftDays=useMemo(()=>Array.from(new Set(stops.map(s=>s.visit_date))).sort(),[stops]);
 useEffect(()=>{let active=true;secureApi<{users:{id:number;full_name:string}[];bases:Base[];can_approve:boolean}>("/monthly-visit-plans/options").then(r=>{if(active){setUsers(r.users);setPerson(String(r.users[0]?.id||""));setBases(r.bases);setCanApprove(r.can_approve);}}).catch(e=>{if(active)setMessage(e.message);});return()=>{active=false;};},[]);
 useEffect(()=>{let active=true;secureApi<{items:Plan[]}>(`/monthly-visit-plans?month=${encodeURIComponent(month)}`).then(r=>{if(active){setPlans(r.items);setDetail(null);}}).catch(e=>{if(active)setMessage(e.message);});return()=>{active=false;};},[month]);
 async function refresh(){const r=await secureApi<{items:Plan[]}>(`/monthly-visit-plans?month=${encodeURIComponent(month)}`);setPlans(r.items);}
 const approvedPlanId=detail?.plan.status==="approved"?detail.plan.id:null;
 const [reconciliation,setReconciliation]=useState<{planId:number;data?:ReconciliationData;error?:string}|null>(null);
 useEffect(()=>{
  if(approvedPlanId===null)return;
  let active=true;
  secureApi<ReconciliationData>(`/monthly-visit-plans/${approvedPlanId}/reconciliation`)
   .then(data=>{if(active)setReconciliation({planId:approvedPlanId,data});})
   .catch(()=>{if(active)setReconciliation({planId:approvedPlanId,error:"گزارش تطبیق دریافت نشد."});});
  return()=>{active=false;};
 },[approvedPlanId]);
 async function open(id:number){setMessage("");setAllowShared(false);try{setDetail(await secureApi<Detail>(`/monthly-visit-plans/${id}`));}catch(e){setMessage(e instanceof Error?e.message:"برنامه دریافت نشد.");}}
 function itemsOf(day:string){return stops.filter(s=>s.visit_date===day).sort((a,b)=>a.stop_order-b.stop_order);}
 function replaceDay(day:string,next:Stop[]){
  const others=stops.filter(s=>s.visit_date!==day);
  const renumbered=next.map((s,index)=>({...s,stop_order:index+1}));
  setStops([...others,...renumbered].sort((a,b)=>a.visit_date.localeCompare(b.visit_date)||a.stop_order-b.stop_order));
 }
 function move(day:string,index:number,delta:number){
  const items=itemsOf(day);const target=index+delta;
  if(target<0||target>=items.length)return;
  const next=[...items];[next[index],next[target]]=[next[target],next[index]];replaceDay(day,next);
 }
 function updateTime(stop:Stop,field:"start_time"|"end_time",value:string){
  setStops(prev=>prev.map(s=>s.visit_date===stop.visit_date&&s.base_source===stop.base_source&&s.base_id===stop.base_id?{...s,[field]:value||null}:s));
 }
 function removeStop(stop:Stop){replaceDay(stop.visit_date,itemsOf(stop.visit_date).filter(s=>!(s.base_source===stop.base_source&&s.base_id===stop.base_id)));}
 async function optimize(day:string){
  const items=itemsOf(day);
  if(items.length<2){setMessage("برای مرتب‌سازی نزدیک‌ترین، دست‌کم دو توقف در این روز لازم است.");return;}
  setBusy(true);setMessage("");
  try{
   const r=await secureApi<{order:number[];distance_m:number;note:string}>("/monthly-visit-plans/order-suggestion",{method:"POST",body:JSON.stringify({stops:items.map(s=>({base_source:s.base_source,base_id:s.base_id}))})});
   replaceDay(day,r.order.map(index=>items[index]));
   setMessage(`${r.note} مسافت تقریبی: ${(r.distance_m/1000).toLocaleString("fa-IR",{maximumFractionDigits:1})} کیلومتر.`);
  }catch(e){setMessage(e instanceof Error?e.message:"مرتب‌سازی انجام نشد.");}finally{setBusy(false);}
 }
 function add(){
  const start=jalaliDateInputToIso(month.replace("-","/")+"/01");if(!start||!selected.length||objective.trim().length<3){setMessage("ماه، پایگاه و هدف ویزیت را کامل کنید.");return;}
  const dates:string[]=[];
  for(let day=1;day<=31;day++){const iso=jalaliDateInputToIso(month.replace("-","/")+"/"+String(day).padStart(2,"0"));if(!iso)continue;if(weekly?(new Date(iso+"T12:00:00Z").getUTCDay()+1)%7===Number(weekday):iso===single)dates.push(iso);}
  const next=[...stops];for(const visit_date of dates)for(const key of selected){const base=bases.find(b=>`${b.source}:${b.id}`===key);if(!base||next.some(s=>s.visit_date===visit_date&&s.base_source===base.source&&s.base_id===base.id))continue;next.push({visit_date,base_source:base.source,base_id:base.id,stop_order:next.filter(s=>s.visit_date===visit_date).length+1,objective,base_name:base.name,start_time:null,end_time:null});}
  setStops(next.sort((a,b)=>a.visit_date.localeCompare(b.visit_date)||a.stop_order-b.stop_order));setMessage(`${dates.length.toLocaleString("fa-IR")} روز به پیش‌نویس اضافه شد؛ هنوز ثبت یا تأیید نشده است.`);
 }
 async function save(){setBusy(true);setMessage("");try{const r=await secureApi<{id:number}>("/monthly-visit-plans",{method:"POST",body:JSON.stringify({user_id:Number(person),month,note,stops:stops.map(({visit_date,base_source,base_id,stop_order,objective,start_time,end_time})=>({visit_date,base_source,base_id,stop_order,objective,start_time:start_time||null,end_time:end_time||null}))})});setStops([]);await refresh();await open(r.id);setMessage("پیش‌نویس ذخیره شد؛ برای اجرا باید ارسال و توسط مدیرعامل تأیید شود.");}catch(e){setMessage(e instanceof Error?e.message:"ثبت انجام نشد.");}finally{setBusy(false);}}
 async function act(action:string,body:unknown={}){if(!detail)return;setBusy(true);setMessage("");try{await secureApi(`/monthly-visit-plans/${detail.plan.id}/${action}`,{method:"POST",body:JSON.stringify(body)});await refresh();await open(detail.plan.id);setMessage("عملیات ثبت شد.");}catch(e){setMessage(e instanceof Error?e.message:"عملیات انجام نشد.");}finally{setBusy(false);}}
 return <PortalShell title="برنامهٔ ماهانهٔ ویزیت" eyebrow="پیش‌نویس، تأیید مدیرعامل و تطبیق کارکرد"><div className="space-y-5">
  <Surface className="p-5 text-sm leading-8">برنامه فقط پس از تأیید مدیرعامل وارد مسیر اجرایی می‌شود. موقعیت یا برنامه به‌تنهایی حقوق نمی‌سازد؛ ویزیت معتبر، گزارش کار و تأیید کارکرد جداگانه لازم است. <a className="text-violet-300 underline" href="/assistant">کمک گرفتن از دستیار برای تحلیل و تهیهٔ برنامه</a></Surface>
  {message&&<p role="status" className="rounded-xl bg-amber-500/10 p-4 text-amber-200">{message}</p>}
  <Surface className="grid gap-4 p-5 sm:grid-cols-2"><label>ماه شمسی<input aria-label="ماه برنامه" className={fieldClass} value={month} onChange={e=>{setMonth(e.target.value);setStops([]);}} dir="ltr" placeholder="1405-09"/></label><label>پرسنل<select aria-label="پرسنل برنامه" className={fieldClass} value={person} onChange={e=>{setPerson(e.target.value);setStops([]);}}>{users.map(u=><option key={u.id} value={u.id}>{u.full_name}</option>)}</select></label></Surface>
  <Surface className="space-y-4 p-5"><h2>تهیهٔ پیش‌نویس چندپایگاهی</h2><label className="flex gap-2"><input type="checkbox" checked={weekly} onChange={e=>setWeekly(e.target.checked)}/>تکرار الگوی روز هفته در ماه انتخاب‌شده</label>{weekly?<select aria-label="روز هفته" className={fieldClass} value={weekday} onChange={e=>setWeekday(e.target.value)}>{weekdays.map((d,i)=><option value={i} key={d}>{d}</option>)}</select>:<IranDateInput value={single} onChange={setSingle} className={fieldClass}/>}
   <fieldset className="space-y-2"><legend>پایگاه‌های برنامه</legend>
    <div className="max-h-56 overflow-y-auto rounded-lg border border-white/10 p-2">
     {bases.map(base=>{const key=`${base.source}:${base.id}`;return <label key={key} className="flex items-center gap-2 p-1">
      <input type="checkbox" checked={selected.includes(key)} onChange={e=>{const checked=e.target.checked;setSelected(previous=>checked?[...previous,key]:previous.filter(item=>item!==key));}}/>
      {base.name} ـ {base.city}
     </label>;})}
    </div><p>{selected.length.toLocaleString("fa-IR")} پایگاه انتخاب شده</p>
   </fieldset><label className="block">هدف ویزیت<input className={fieldClass} value={objective} onChange={e=>setObjective(e.target.value)}/></label><button onClick={add} className={primaryButton}>تأیید انتخاب و افزودن به پیش‌نویس</button>
   <label className="block">توضیح برنامه<textarea className={fieldClass} value={note} onChange={e=>setNote(e.target.value)}/></label>
   {draftDays.map(day=>{const items=itemsOf(day);return <div key={day} className="rounded-xl bg-white/5 p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-bold">{formatIranDate(day)} · {items.length.toLocaleString("fa-IR")} توقف</span><button type="button" disabled={busy||items.length<2} onClick={()=>void optimize(day)} className="text-xs text-violet-300 disabled:opacity-40">مرتب‌سازی نزدیک‌ترین پایگاه</button></div>
    <div className="mt-2 space-y-2">{items.map((s,index)=><div key={keyOf(s)} className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 p-2 text-xs">
     <span className="min-w-32 flex-1">{s.stop_order.toLocaleString("fa-IR")}. {s.base_name}</span>
     <input aria-label={`ساعت شروع ${s.base_name}`} type="time" className={timeInput} value={s.start_time??""} onChange={e=>updateTime(s,"start_time",e.target.value)}/>
     <span>–</span>
     <input aria-label={`ساعت پایان ${s.base_name}`} type="time" className={timeInput} value={s.end_time??""} onChange={e=>updateTime(s,"end_time",e.target.value)}/>
     <button type="button" aria-label="جابه‌جایی به بالا" disabled={index===0} onClick={()=>move(day,index,-1)} className="px-1 text-violet-300 disabled:opacity-30">↑</button>
     <button type="button" aria-label="جابه‌جایی به پایین" disabled={index===items.length-1} onClick={()=>move(day,index,1)} className="px-1 text-violet-300 disabled:opacity-30">↓</button>
     <button type="button" onClick={()=>removeStop(s)} className="text-rose-300">حذف</button>
    </div>)}</div>
    <p className="mt-2 text-[11px] text-slate-400">ساعت‌ها اختیاری‌اند؛ اگر ثبت شوند باید همهٔ توقف‌های همان روز ساعت داشته باشند و هم‌پوشانی نکنند.</p>
   </div>;})}
   <button disabled={busy||!stops.length} onClick={()=>void save()} className={primaryButton}>ذخیرهٔ پیش‌نویس ماهانه</button>
  </Surface>
  <Surface className="space-y-3 p-5"><h2>برنامه‌های ماه انتخاب‌شده</h2>{plans.map(p=><button key={p.id} className="block w-full rounded-xl border border-white/10 p-3 text-right" onClick={()=>void open(p.id)}>{p.full_name} · نسخهٔ {p.revision.toLocaleString("fa-IR")} · {states[p.status]||p.status}</button>)}</Surface>
  {detail&&<Surface className="space-y-4 p-5"><h2>بازبینی و تطبیق برنامه</h2><p>توقف برنامه‌ریزی‌شده: {detail.summary.planned_stops.toLocaleString("fa-IR")} · ویزیت معتبر: {detail.summary.verified_stops.toLocaleString("fa-IR")} · تداخل: {detail.summary.conflicts.toLocaleString("fa-IR")} · دارای ساعت: {detail.summary.timed_stops.toLocaleString("fa-IR")}</p>
   {detail.stops.map((s,i)=><div key={i} className="rounded-xl border border-white/10 p-3 text-sm">{formatIranDate(s.visit_date)} · {s.stop_order} · {s.base_name}{s.start_time?` · ${s.start_time}–${s.end_time}`:""} · {s.objective}<p className="mt-2 text-amber-200">{s.conflict?`ویزیت مشترک با مسیر ${s.conflict_with||"نیروی دیگر"} · `:""}{s.verified_visit?"ویزیت معتبر ثبت شده":"ویزیت معتبر ثبت نشده"} · {s.has_daily_report?"گزارش کار موجود است":"گزارش کار موجود نیست"}</p></div>)}
   {['draft','returned'].includes(detail.plan.status)&&<button disabled={busy} onClick={()=>void act('submit')} className={primaryButton}>ارسال برای تأیید مدیرعامل</button>}
   {canApprove&&detail.plan.status==='submitted'&&<><label className="block">نظر مدیرعامل<textarea className={fieldClass} value={reviewNote} onChange={e=>setReviewNote(e.target.value)}/></label>
    {detail.summary.conflicts>0&&<label className="flex gap-2 rounded-xl bg-amber-500/10 p-3 text-sm text-amber-200"><input type="checkbox" checked={allowShared} onChange={e=>setAllowShared(e.target.checked)}/>ویزیت مشترک {detail.summary.conflicts.toLocaleString("fa-IR")} توقف با مسیر نیروی دیگر را با دلیل مستند می‌پذیرم.</label>}
    <button disabled={busy||(detail.summary.conflicts>0?reviewNote.trim().length<8:reviewNote.trim().length<3)||(detail.summary.conflicts>0&&!allowShared)} className={primaryButton} onClick={()=>void act('review',{decision:'approved',note:reviewNote,allow_shared:allowShared})}>تأیید و فعال‌سازی برنامه</button><button disabled={busy||reviewNote.trim().length<3} className="mr-4 text-amber-200" onClick={()=>void act('review',{decision:'returned',note:reviewNote})}>برگشت برای اصلاح</button></>}
   {['returned','approved'].includes(detail.plan.status)&&<button onClick={()=>{setPerson(String(detail.plan.user_id));setStops(detail.stops.filter(s=>detail.plan.status!=='approved'||(!s.locked_for_revision&&s.visit_date>iranTodayIso())));setNote(detail.plan.note);setMessage("روزهای آیندهٔ قابل اصلاح به فرم کپی شدند. روزهای گذشته، امروز و دارای شواهد یا کارکرد حفظ می‌شوند؛ اصلاحیه فقط با تأیید مجدد مدیرعامل اجرا می‌شود.");}} className={primaryButton}>کپی برای تهیهٔ نسخهٔ اصلاح‌شده</button>}
   {canApprove&&detail.plan.status==='approved'&&<details><summary>بازبینی کارکرد روز برای فیش حقوقی</summary><div className="mt-4 space-y-3"><IranDateInput value={workDate} onChange={setWorkDate} className={fieldClass}/><label className="block">روز کارکرد تأییدشده؛ از صفر تا یک<input className={fieldClass} type="number" min="0" max="1" step="0.001" value={credit} onChange={e=>setCredit(e.target.value)}/></label><textarea aria-label="دلیل تأیید کارکرد" className={fieldClass} value={reviewNote} onChange={e=>setReviewNote(e.target.value)} placeholder="دلیل مستند تأیید یا کارکرد جزئی"/><button disabled={busy||!workDate||reviewNote.trim().length<8} className={primaryButton} onClick={()=>void act('workday-review',{work_date:workDate,credited_days:Number(credit),note:reviewNote})}>ثبت کارکرد مستند برای بازبینی حقوق</button><p className="text-sm text-amber-200">این کار فیش را تصویب یا پرداخت نمی‌کند. منبع کارکرد ماه باید جداگانه تطبیق و تأیید شود؛ کارکرد ثبت‌شدهٔ قبلی دوباره شمرده نمی‌شود.</p></div></details>}
   {approvedPlanId!==null&&reconciliation?.planId===approvedPlanId&&(
    reconciliation.error?<p role="alert">{reconciliation.error}</p>:<ReconciliationPanel data={reconciliation.data??null}/>
   )}
   <details><summary>تاریخچهٔ برنامه</summary>{detail.history.map((h,i)=><p className="mt-2 text-sm" key={i}>{states[h.event]||"رویداد ثبت‌شده"} · {h.note}</p>)}</details>
  </Surface>}
 </div></PortalShell>;
}
