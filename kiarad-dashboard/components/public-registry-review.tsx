"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { secureApi } from "../lib/secure-api";
import { formatIranDate } from "../lib/iran-date";
import { Surface,fieldClass } from "./portal-shell";
import styles from "./treasury-strategy.module.css";

type Batch={id:string;title:string;records:number;source_url:string;source_file_modified:string|null};
type Item={source_id:string;batch_id:string;source_row:number;name:string;city?:string;address?:string;phone?:string;gln?:string;category:string;
 possible_matches_count:number;possible_matches:{customer_id:number;customer_name:string;basis:string;base:null|{source:string;id:number}}[]};
type Report={observed_at:string;notice:string;batches:Batch[];items:Item[];total_source_rows:number;rows_with_possible_matches:number;total_matches:number;offset:number;limit:number};
type SourceJob={status:string;sources:Array<{id:string;title:string;status:string;records:number;source_url:string}>};
const category:Record<string,string>={pharmacy:"داروخانه",distributor:"شرکت پخش",hospital_identity:"شناسهٔ بیمارستان",sales_point:"نقطهٔ فروش برند؛ نوع نیازمند بررسی"};

export function PublicRegistryReview(){
 const [open,setOpen]=useState(false),[query,setQuery]=useState(""),[batch,setBatch]=useState(""),[offset,setOffset]=useState(0);
 const [report,setReport]=useState<Report|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState("");
 const [refreshing,setRefreshing]=useState(false),[refreshMessage,setRefreshMessage]=useState(""),[revision,setRevision]=useState(0);
 const [importing,setImporting]=useState("");
 const [sourceJob,setSourceJob]=useState<SourceJob|null>(null);
 useEffect(()=>{
  if(!open)return;
  let active=true;let timer:ReturnType<typeof setTimeout>;
  async function poll(){
   try{
    const result=await secureApi<SourceJob>("/kerman/coach/public-registry/refresh-status");
    if(!active)return;
    setSourceJob(result);
    if(result.status==="running")timer=setTimeout(()=>void poll(),3000);
    else setRevision(value=>value+1);
   }catch{/* گزارش اصلی خطای دسترسی را نمایش می‌دهد. */}
  }
  void poll();return()=>{active=false;clearTimeout(timer);};
 },[open,refreshing]);
 async function refreshAll(){
  if(refreshing||sourceJob?.status==="running")return;
  setRefreshing(true);
  try{setSourceJob(await secureApi<SourceJob>("/kerman/coach/public-registry/refresh-all",{method:"POST"}));}
  catch(reason){setRefreshMessage(reason instanceof Error?reason.message:"شروع به‌روزرسانی انجام نشد.");}
  finally{setRefreshing(false);}
 }
 async function importCustomer(item:Item){
  if(importing||!window.confirm(`«${item.name}» در ${item.city} به مشتریان اضافه شود؟ فعالیت فعلی این واحد هنوز تأیید نشده است.`))return;
  setImporting(item.source_id);setRefreshMessage("");
  try{
   const result=await secureApi<{status:string}>("/kerman/coach/public-registry/import",{method:"POST",body:JSON.stringify({source_id:item.source_id,confirm:true})});
   setRefreshMessage(result.status==="already_imported"?"این ردیف قبلاً وارد شده است؛ مشتری تکراری ساخته نشد.":"مشتری با نگهداری منبع ثبت شد؛ هیچ اطلاعاتی در هلو نوشته نشد.");
   setRevision(value=>value+1);
  }catch(reason){setRefreshMessage(reason instanceof Error?reason.message:"افزودن مشتری انجام نشد.");}
  finally{setImporting("");}
 }
 async function refreshSources(){
  if(refreshing)return;
  setRefreshing(true);setRefreshMessage("");
  try{
   const result=await secureApi<{message:string}>("/kerman/coach/public-registry/refresh",{method:"POST"});
   setRefreshMessage(result.message);setRevision(value=>value+1);
  }catch(reason){setRefreshMessage(reason instanceof Error?reason.message:"به‌روزرسانی انجام نشد؛ فهرست قبلی حفظ شد.");}
  finally{setRefreshing(false);}
 }
 useEffect(()=>{
  if(!open)return;
  let active=true;const controller=new AbortController();
  const timer=window.setTimeout(()=>{
   setLoading(true);
   void secureApi<Report>(`/kerman/coach/public-registry?q=${encodeURIComponent(query)}&batch=${encodeURIComponent(batch)}&offset=${offset}&limit=20`,{signal:controller.signal})
    .then(value=>{if(active){setReport(value);setError("");}})
    .catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"فهرست منابع دریافت نشد.");})
    .finally(()=>{if(active)setLoading(false);});
  },250);
  return()=>{active=false;controller.abort();window.clearTimeout(timer);};
 },[open,query,batch,offset,revision]);
 return <Surface className="mb-5 p-5"><details onToggle={event=>setOpen(event.currentTarget.open)}>
  <summary className="cursor-pointer text-base font-bold">فهرست‌های مرجع استان و سرنخ‌های قابل بررسی</summary>
  <button type="button" className={`${styles.secondary} mt-4`} disabled={refreshing} onClick={()=>void refreshSources()}>{refreshing?"در حال بررسی منبع…":"به‌روزرسانی شبکهٔ فروش مای"}</button>
  <button type="button" className={`${styles.secondary} mr-3 mt-4`} disabled={refreshing||sourceJob?.status==="running"} onClick={()=>void refreshAll()}>{sourceJob?.status==="running"?"در حال بررسی منابع…":"به‌روزرسانی همهٔ منابع متصل"}</button>
  {sourceJob&&<div role="status" className="mt-3 space-y-2 text-xs">{sourceJob.sources.map(source=><p key={source.id}><a href={source.source_url} target="_blank" rel="noreferrer" className="text-violet-300">{source.title}</a> · {source.status==="updated"?"دریافت تازه موفق": "دریافت ناموفق؛ نسخهٔ قبلی حفظ شد"} · {source.records.toLocaleString("fa-IR")} ردیف</p>)}</div>}
  {refreshMessage&&<p role="status" className="mt-3 text-xs leading-6">{refreshMessage}</p>}
  <p className="mt-3 text-xs leading-6 text-slate-400">ردیف‌های منابع رسمی و شبکهٔ فروش برند، با مشتری فعال متفاوت‌اند؛ تطبیق‌های زیر فقط برای بازبینی مدیرند و هیچ مشتری، گرید یا مسئول خودکار ثبت نمی‌شود.</p>
  <div className="my-4 grid gap-3 md:grid-cols-2">
   <label>جست‌وجوی سرنخ با بخشی از نام، شهر یا نشانی<input className={`${fieldClass} mt-2`} value={query} maxLength={100} onChange={event=>{setQuery(event.target.value);setOffset(0);}}/></label>
   <label>منبع فهرست<select className={`${fieldClass} mt-2`} value={batch} onChange={event=>{setBatch(event.target.value);setOffset(0);}}><option value="">همهٔ منابع؛ دارای همپوشانی</option>{report?.batches.map(source=><option key={source.id} value={source.id}>{source.title} · {source.records.toLocaleString("fa-IR")} ردیف</option>)}</select></label>
  </div>
  {loading&&<p role="status">در حال دریافت سرنخ‌ها…</p>}{error&&<p role="alert" className={styles.error}>{error}</p>}
  {report&&!loading&&!error&&<>
   <p role="status" className="text-sm">{report.total_source_rows.toLocaleString("fa-IR")} ردیف منابع با همپوشانی؛ {report.rows_with_possible_matches.toLocaleString("fa-IR")} ردیف دارای مشتری احتمالی. این اعداد تعداد پایگاه یکتا یا درصد پوشش استان نیستند.</p>
   <p className="my-3 text-xs leading-6 text-amber-200">{report.notice}</p>
   <details className="mb-4 text-xs"><summary>منبع و زمان فایل‌ها</summary>{report.batches.map(source=><p key={source.id} className="my-2 leading-6"><a className="text-violet-300" href={source.source_url} target="_blank" rel="noreferrer">{source.title}</a> · آخرین ذخیرهٔ فایل: {source.source_file_modified?formatIranDate(source.source_file_modified.slice(0,10)):"نامشخص"}</p>)}</details>
   <p className="mb-3 text-xs text-slate-400">{report.total_matches.toLocaleString("fa-IR")} نتیجه در فیلتر فعلی؛ تاریخ دریافت {formatIranDate(report.observed_at)}</p>
   <div className="mb-4 flex flex-wrap gap-2">{report.items.filter(item=>!item.possible_matches_count&&item.city&&["pharmacy","sales_point"].includes(item.category)).map(item=><button key={item.source_id} type="button" className={styles.secondary} disabled={!!importing} onClick={()=>void importCustomer(item)}>{importing===item.source_id?"در حال ثبت…":`افزودن ${item.name} · ${item.city}`}</button>)}</div>
   <div className="overflow-x-auto"><table className="w-full min-w-[850px] text-right text-xs"><thead><tr>{["نام و نوع","شهر و نشانی","شناسهٔ تجاری و تلفن","تطبیق پیشنهادی"].map(label=><th className="p-3" key={label}>{label}</th>)}</tr></thead><tbody>{report.items.map(item=><tr key={item.source_id} className="border-t border-white/10"><td className="p-3"><b>{item.name}</b><p>{category[item.category]||"نیازمند بررسی"}</p><small>ردیف منبع {item.source_row.toLocaleString("fa-IR")}</small></td><td className="p-3">{item.city||"شهر در این منبع مشخص نیست"}<p className="mt-1 leading-6">{item.address||"نشانی ندارد"}</p></td><td className="p-3">{item.gln&&<p>جی‌ال‌ان: <bdi>{item.gln}</bdi></p>}<bdi>{item.phone||"تلفن در این منبع ثبت نشده"}</bdi></td><td className="p-3">{item.possible_matches.length?item.possible_matches.map(candidate=><div key={candidate.customer_id} className="my-2"><p>{candidate.customer_name}</p><p className="text-slate-400">{candidate.basis==="same_full_phone"?"شمارهٔ کامل یکسان":"نام و شهر مشابه پس از یکسان‌سازی حروف"}؛ هویت تأیید نشده</p>{candidate.base&&<Link className="text-violet-300" href={`/kerman-bases?base_source=${encodeURIComponent(candidate.base.source)}&base_id=${candidate.base.id}#base-coach`}>بازکردن پروندهٔ مشتری برای بررسی</Link>}</div>):"تطبیق قطعی نداریم؛ نیازمند بررسی"}{item.possible_matches_count>5&&<p>بیش از پنج تطبیق احتمالی؛ فقط پنج مورد اول نمایش داده شد.</p>}</td></tr>)}</tbody></table></div>
   {!report.items.length&&<p className="my-4">سرنخی با این جست‌وجو پیدا نشد.</p>}
   <div className="mt-4 flex gap-3"><button className={styles.secondary} disabled={offset===0} onClick={()=>setOffset(value=>Math.max(0,value-20))}>صفحهٔ قبل</button><button className={styles.secondary} disabled={offset+report.items.length>=report.total_matches} onClick={()=>setOffset(value=>value+20)}>صفحهٔ بعد</button></div>
  </>}
 </details></Surface>;
}
