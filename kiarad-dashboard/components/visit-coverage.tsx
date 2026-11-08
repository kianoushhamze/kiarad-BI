"use client";

import {useCallback,useEffect,useRef,useState} from "react";
import Link from "next/link";
import {secureApi} from "../lib/secure-api";
import {Surface,fieldClass} from "./portal-shell";
import {formatIranDate} from "../lib/iran-date";

type Item={id:number;salesperson_name:string;base_name:string;city?:string;base_source:string;base_id:number;last_verified_visit:string|null;next_due_date:string;days_overdue:number;verified_visits_15_days:number;status:string};
type Base={source:string;id:number;name:string;city?:string};
const label:Record<string,string>={overdue:"عقب‌افتاده",due_today:"سررسید امروز",never_visited:"بدون بازدید معتبر",on_schedule:"در بازهٔ مجاز"};
const date=(value:string|null)=>value?formatIranDate(value):"ثبت نشده";

export function VisitCoverage({manager,salespersonId}:{manager:boolean;salespersonId?:number|null}){
  const [items,setItems]=useState<Item[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
  const [people,setPeople]=useState<{id:number;name:string}[]>([]),[bases,setBases]=useState<Base[]>([]);
  const [person,setPerson]=useState(""),[base,setBase]=useState(""),[saving,setSaving]=useState(false),[message,setMessage]=useState("");
  const requestId=useRef(0);
  const load=useCallback(async(isActive:()=>boolean=()=>true)=>{const id=++requestId.current;setLoading(true);setError("");try{const result=await secureApi<{items:Item[]}>("/api/compensation/visit-coverage"+(salespersonId?`?salesperson_id=${salespersonId}`:""));if(isActive()&&id===requestId.current)setItems(result.items);}catch{if(isActive()&&id===requestId.current)setError("پوشش بازدید دریافت نشد؛ تعداد را صفر تلقی نکنید.");}finally{if(isActive()&&id===requestId.current)setLoading(false);}},[salespersonId]);
  useEffect(()=>{
    let active=true;
     void Promise.resolve().then(()=>{if(active)void load(()=>active);});
     return()=>{active=false;};
  },[load]);
  useEffect(()=>{if(!manager)return;let active=true;Promise.all([secureApi<{salespersons:{id:number;name:string}[]}>("/salespersons"),secureApi<{items:Base[]}>("/api/compensation/bases")]).then(([p,b])=>{if(active){setPeople(p.salespersons);setBases(b.items);}}).catch(()=>{if(active)setError("فهرست تخصیص پایگاه دریافت نشد.");});return()=>{active=false;};},[manager]);
  async function assign(){if(!person||!base||saving)return;const [source,id]=base.split(":");setSaving(true);setMessage("");try{await secureApi("/api/compensation/base-portfolios",{method:"POST",body:JSON.stringify({salesperson_id:Number(person),source,base_id:Number(id)})});setMessage("مسئول پایگاه ثبت شد؛ انتقال مسئولیت، سابقهٔ مسئول قبلی را نگه می‌دارد.");await load();}catch(reason){setError(reason instanceof Error?reason.message:"تخصیص ثبت نشد.");}finally{setSaving(false);}}
  return <Surface className="p-5"><div className="flex items-center justify-between gap-3"><h2 className="font-bold text-white">پوشش بازدید ۱۵روزه</h2><button type="button" onClick={()=>void load()} disabled={loading} className="text-sm text-violet-300">تازه‌سازی پوشش</button></div>
    <p className="mt-3 text-xs leading-6 text-slate-400">فقط پایگاه‌های دارای مسئول مشخص و حضور تأییدشده سنجیده می‌شوند. اولین مهلت ۱۵ روز پس از تخصیص است؛ نبود سابقه به معنی بازدید صفر در گذشته نیست. این بخش ردیابی لایو نیست.</p>
    {manager&&<div className="mt-4 grid gap-3 md:grid-cols-3"><label className="text-xs text-slate-400">مسئول پایگاه<select className={`${fieldClass} mt-2`} value={person} onChange={e=>setPerson(e.target.value)}><option value="">انتخاب پرسنل</option>{people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="text-xs text-slate-400">پایگاه تحت مسئولیت<select className={`${fieldClass} mt-2`} value={base} onChange={e=>setBase(e.target.value)}><option value="">انتخاب پایگاه</option>{bases.map(b=><option key={`${b.source}:${b.id}`} value={`${b.source}:${b.id}`}>{b.name} · {b.city||"شهر نامشخص"}</option>)}</select></label><button type="button" disabled={saving||!person||!base} onClick={assign} className="self-end rounded-xl bg-indigo-600 px-4 py-3 text-sm text-white disabled:opacity-40">{saving?"در حال ثبت…":"ثبت مسئول پایگاه"}</button></div>}
    {error&&<p role="alert" className="mt-3 text-sm text-rose-300">{error}</p>}{message&&<p role="status" className="mt-3 text-sm text-emerald-300">{message}</p>}
    {loading?<p className="mt-4 text-sm text-slate-400">در حال دریافت پوشش…</p>:!error&&!items.length?<p className="mt-4 text-sm text-slate-400">پایگاهِ دارای مسئول در این دامنه ثبت نشده؛ هنوز نمی‌توان درصد پوشش اعلام کرد.</p>:<div className="mt-4 overflow-x-auto"><table className="w-full min-w-[720px] text-right text-xs"><thead className="text-slate-400"><tr>{["پایگاه / مسئول","وضعیت","آخرین بازدید معتبر","سررسید بعدی","تأخیر / بازدید ۱۵روز"].map(t=><th key={t} className="p-3">{t}</th>)}</tr></thead><tbody>{items.map(item=><tr key={item.id} className="border-t border-white/10 text-slate-300"><td className="p-3"><Link className="text-violet-300" href={`/kerman-bases?base_source=${encodeURIComponent(item.base_source)}&base_id=${item.base_id}`}>{item.base_name||"پایگاه نامشخص"}</Link><div className="mt-1">{item.salesperson_name} · {item.city||"شهر نامشخص"}</div></td><td className="p-3">{label[item.status]||item.status}</td><td className="p-3">{date(item.last_verified_visit)}</td><td className="p-3">{date(item.next_due_date)}</td><td className="p-3">{item.days_overdue.toLocaleString("fa-IR")} روز / {item.verified_visits_15_days.toLocaleString("fa-IR")} بازدید</td></tr>)}</tbody></table></div>}
  </Surface>;
}
