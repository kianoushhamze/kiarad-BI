"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { secureApi } from "../lib/secure-api";
import { matchesSearch } from "../lib/text-search";
import { fieldClass } from "./portal-shell";
import styles from "./treasury-strategy.module.css";

const gapLabels: Record<string,string> = {
  owner:"مسئول فعال", location:"مختصات معتبر", grade:"گرید", capacity:"ظرفیت ماهانه",
  customer:"پیوند مشتری", type:"تعیین نوع طرف حساب",
};
type Report={total:number;without_structural_gaps:number;counts:Record<string,number>;notice:string;
  items:{source:string;id:number;name:string;city:string|null;missing:string[]}[]};

export function BaseReadiness({onOpen,refreshKey,disabled=false}:{onOpen:(key:string)=>void;refreshKey:number;disabled?:boolean}) {
  const [report,setReport]=useState<Report|null>(null);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  const [query,setQuery]=useState("");
  const [gap,setGap]=useState("");
  useEffect(()=>{
    let active=true;
    secureApi<Report>("/kerman/coach/readiness").then(data=>{
      if(active){setReport(data);setError("");}
    }).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"فهرست نقص‌ها دریافت نشد.");})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[refreshKey,revision]);
  const items=report?.items.filter(item=>(!gap||item.missing.includes(gap))&&matchesSearch(query,item.name,item.city??""))??[];
  return <details className={styles.warning}>
    <summary>آمادگی اطلاعات پایگاه‌ها برای برنامه‌ریزی</summary>
    <p className={styles.help}>این فهرست نقص‌ها را نشان می‌دهد؛ مسئول، گرید و موقعیت خودکار تعیین نمی‌شوند.</p>
    <button type="button" className={styles.secondary} disabled={loading} onClick={()=>{setLoading(true);setRevision(value=>value+1);}}>بازخوانی نقص‌های پایگاه‌ها</button>
    {loading&&<p role="status">در حال بررسی دفتر پایگاه‌ها…</p>}
    {error&&<p role="alert" className={styles.error}>{error}</p>}
    {report&&!loading&&!error&&<>
      <p role="status">{report.total.toLocaleString("fa-IR")} پایگاه؛ {report.without_structural_gaps.toLocaleString("fa-IR")} ورودی بدون نقص ساختاری در این بررسی.</p>
      <div className={styles.buttons}>{Object.entries(gapLabels).map(([key,label])=><button type="button" key={key} aria-pressed={gap===key} className={styles.secondary} onClick={()=>setGap(gap===key?"":key)}>{label}: {(report.counts[key]??0).toLocaleString("fa-IR")} نقص</button>)}</div>
      <label className={styles.field}>جست‌وجو در فهرست نقص‌های پایگاه<input className={fieldClass} value={query} onChange={event=>setQuery(event.target.value)}/></label>
      <p className={styles.help}>{items.length.toLocaleString("fa-IR")} نتیجه؛ حداکثر ۲۰ مورد اول نمایش داده می‌شود. {report.notice}</p>
      <ul>{items.slice(0,20).map(item=><li key={`${item.source}:${item.id}`} className="my-3">
        <button type="button" disabled={disabled} className={styles.secondary} onClick={()=>onOpen(`${item.source}:${item.id}`)}>بررسی پروندهٔ {item.name}</button>
        <p>{item.city||"شهر نامشخص"} · {item.missing.map(key=>gapLabels[key]).join("، ")||"بدون نقص ساختاری"}</p>
      </li>)}</ul>
      <Link href="/my-plan" className={styles.secondary}>تخصیص مسئول در برنامهٔ من</Link>
    </>}
  </details>;
}
