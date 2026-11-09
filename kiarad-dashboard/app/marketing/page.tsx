"use client";
import { useCallback, useEffect, useState } from "react";
import { PortalShell, Surface, primaryButton, fieldClass } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";

type QuestionItem={id:number;asked_on:string|null;topic:string;question:string;source:string;signal_score:number;created_at:string};
type QuestionGroup={topic:string;count:number;items:QuestionItem[]};
type DemandItem={code:string;category:string|null;kerman_sales_pct:string|null;web_signal:number;sales_source:string;updated_at:string|null;product_name:string;tier:string};
type ContentItem={id:number;created_at:string;kind:string;title:string;body:string;status:string};
type LeadItem={id:number;created_at:string;source:string;name:string;city:string|null;phone:string|null;address:string|null;status:string};
type SourceCount={source:string;count:number};

const KIND_LABELS:Record<string,string>={post:"پست اینستاگرام",story:"ایدهٔ استوری",seo:"مقاله سئو"};
const KIND_BADGES:Record<string,string>={post:"bg-violet-500/15 text-violet-200",story:"bg-sky-500/15 text-sky-200",seo:"bg-emerald-500/15 text-emerald-200"};
const LEAD_STATUS_LABELS:Record<string,string>={new:"جدید",contacted:"تماس‌شده",qualified:"واجد شرایط",lost:"منتفی",customer:"مشتری شد"};

export default function MarketingPage(){
  const [tab,setTab]=useState<"questions"|"demand"|"content"|"leads">("questions");
  const [groups,setGroups]=useState<QuestionGroup[]>([]);
  const [demand,setDemand]=useState<DemandItem[]>([]);
  const [content,setContent]=useState<ContentItem[]>([]);
  const [leads,setLeads]=useState<LeadItem[]>([]);
  const [leadSources,setLeadSources]=useState<SourceCount[]>([]);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [lastHarvest,setLastHarvest]=useState<Record<string,unknown>|null>(null);
  const [lastDemand,setLastDemand]=useState<Record<string,unknown>|null>(null);
  const [lastDiscover,setLastDiscover]=useState<Record<string,unknown>|null>(null);
  // leads filters + manual form
  const [fSource,setFSource]=useState("");
  const [fCity,setFCity]=useState("");
  const [fQ,setFQ]=useState("");
  const [newLead,setNewLead]=useState({name:"",city:"",phone:"",address:""});
  const [fSpecialty,setFSpecialty]=useState("پوست");

  const loadQuestions=useCallback(()=>{secureApi<{groups:QuestionGroup[]}>("/marketing/questions")
    .then(v=>{setGroups(v.groups||[]);setError("");}).catch(r=>setError(r instanceof Error?r.message:"دریافت سؤالات ناموفق بود."));},[]);
  const loadDemand=useCallback(()=>{secureApi<{items:DemandItem[]}>("/marketing/demand")
    .then(v=>{setDemand(v.items||[]);setError("");}).catch(r=>setError(r instanceof Error?r.message:"دریافت تقاضا ناموفق بود."));},[]);
  const loadContent=useCallback(()=>{secureApi<{items:ContentItem[]}>("/marketing/content")
    .then(v=>{setContent(v.items||[]);setError("");}).catch(r=>setError(r instanceof Error?r.message:"دریافت محتواها ناموفق بود."));},[]);
  const loadLeads=useCallback(()=>{const p=new URLSearchParams();
    if(fSource.trim())p.set("source",fSource.trim());
    if(fCity.trim())p.set("city",fCity.trim());
    if(fQ.trim())p.set("q",fQ.trim());
    secureApi<{items:LeadItem[];source_counts:SourceCount[]}>(`/marketing/leads?${p.toString()}`)
    .then(v=>{setLeads(v.items||[]);setLeadSources(v.source_counts||[]);setError("");})
    .catch(r=>setError(r instanceof Error?r.message:"دریافت لیدها ناموفق بود."));},[fSource,fCity,fQ]);

  useEffect(function(){loadQuestions();loadDemand();loadContent();},[loadQuestions,loadDemand,loadContent]);
  useEffect(function(){if(tab==="leads")loadLeads();},[tab,loadLeads]);

  async function run(url:string,after:(v:Record<string,unknown>)=>void,msg:string,body?:string){
    if(busy)return;setBusy(true);setError("");setNotice("");
    try{const res=await secureApi<Record<string,unknown>>(url,{method:"POST",body});after(res);setNotice(msg);loadQuestions();loadDemand();loadContent();loadLeads();}
    catch(r){setError(r instanceof Error?r.message:"عملیات ناموفق بود.");}
    finally{setBusy(false);}
  }

  async function harvest(){await run("/marketing/harvest-questions",v=>setLastHarvest(v),"برداشت سؤالات کامل شد.");}
  async function refresh(){await run("/marketing/refresh-demand",v=>setLastDemand(v),"بررسی تقاضا کامل شد.");}
  async function generate(){await run("/marketing/generate-content",()=>{},"سه پیش‌نویس محتوا ساخته شد.");}
  async function importLeads(){await run("/marketing/leads/import-files",()=>{},"لیدها از فایل‌های استخراج‌شده وارد شدند (تکراری‌ها رد شدند).");}
  async function discoverLeads(){await run("/marketing/leads/discover",v=>setLastDiscover(v),"لیدیابی زنده کامل شد؛ نتیجه زیر جدول آمده است.",JSON.stringify({specialty_text:fSpecialty.trim()||"پوست"}));}
  async function saveLead(){
    if(!newLead.name.trim()){setError("نام لید الزامی است.");return;}
    if(busy)return;setBusy(true);setError("");setNotice("");
    try{await secureApi("/marketing/leads",{method:"POST",body:JSON.stringify({name:newLead.name.trim(),city:newLead.city.trim()||null,phone:newLead.phone.trim()||null,address:newLead.address.trim()||null})});
      setNotice("لید ثبت شد.");setNewLead({name:"",city:"",phone:"",address:""});loadLeads();}
    catch(r){setError(r instanceof Error?r.message:"ثبت لید ناموفق بود.");}
    finally{setBusy(false);}
  }
  async function deleteLead(id:number){
    if(busy)return;setBusy(true);setError("");setNotice("");
    try{await secureApi(`/marketing/leads/${id}`,{method:"DELETE"});setNotice("لید حذف شد.");loadLeads();}
    catch(r){setError(r instanceof Error?r.message:"حذف لید ناموفق بود.");}
    finally{setBusy(false);}
  }
  async function sendToCalendar(id:number){
    if(busy)return;setBusy(true);setError("");setNotice("");
    try{await secureApi(`/marketing/content/${id}/to-calendar`,{method:"POST"});setNotice("به تقویم محتوا (در انتظار بازبینی) ارسال شد.");loadContent();}
    catch(r){setError(r instanceof Error?r.message:"ارسال به تقویم ناموفق بود.");}
    finally{setBusy(false);}
  }

  const maxPct=Math.max(1,...demand.map(d=>Number(d.kerman_sales_pct)||0));

  return <PortalShell title="مارکتینگ و برندینگ" eyebrow="کمپین و محتوا">
    <div className="mx-auto max-w-6xl space-y-5 p-4 lg:p-6">
      {error&&<p role="alert" className="text-rose-300">{error}</p>}
      {notice&&<p className="text-emerald-300">{notice}</p>}

      <div className="flex flex-wrap gap-2">
        {([["questions","سؤالات پرتکرار"],["demand","تقاضای محصولات"],["content","تولید محتوا"],["leads","لیدها"]] as const).map(([key,label])=>(
          <button key={key} type="button" onClick={()=>setTab(key)}
            className={`rounded-xl border px-4 py-2 text-xs transition ${tab===key?"border-violet-400/40 bg-violet-500/15 text-violet-200":"border-white/10 bg-white/[0.04] text-slate-400 hover:text-white"}`}>{label}</button>
        ))}
        <span className="grow"/>
        {tab==="questions"&&<button type="button" disabled={busy} onClick={harvest} className={primaryButton}>🌐 برداشت سؤالات از وب</button>}
        {tab==="demand"&&<button type="button" disabled={busy} onClick={refresh} className={primaryButton}>📊 بررسی تقاضا</button>}
        {tab==="content"&&<button type="button" disabled={busy} onClick={generate} className={primaryButton}>✨ تولید محتوا با دستیار</button>}
        {tab==="leads"&&<button type="button" disabled={busy} onClick={importLeads} className={primaryButton}>⬇️ واردکردن از فایل‌ها (داروخانه‌ها + پزشکان)</button>}
        {tab==="leads"&&<button type="button" disabled={busy} onClick={discoverLeads} className={primaryButton}>🌐 لیدیابی زنده از پذیرش۲۴</button>}
      </div>

      {tab==="questions"&&<Surface className="space-y-4 p-5">
        {lastHarvest&&<p className="text-[11px] text-slate-400">
          آخرین برداشت: {String(lastHarvest.searched??0)} جست‌وجو، {String(lastHarvest.inserted??0)} سؤال جدید،
          {Number(lastHarvest.ratelimited??0)>0?` ${String(lastHarvest.ratelimited)} جست‌وجو محدودیت نرخ خورد`:""} — فقط نتایج واقعی ذخیره می‌شود.
        </p>}
        {groups.length===0&&<p className="text-xs text-slate-500">هنوز سؤالی ثبت نشده؛ دکمهٔ «برداشت سؤالات از وب» را بزن.</p>}
        {groups.map(g=><div key={g.topic}>
          <h3 className="mb-2 text-xs font-bold text-violet-300">{g.topic} <span className="text-slate-500">({g.count.toLocaleString("fa-IR")})</span></h3>
          <ul className="space-y-1">{g.items.map(q=><li key={q.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-xs text-slate-300">{q.question}</li>)}</ul>
        </div>)}
      </Surface>}

      {tab==="demand"&&<Surface className="space-y-4 p-5">
        {lastDemand&&<p className="text-[11px] text-slate-400">
          منبع درصد فروش: {String(lastDemand.sales_source??"")}
          {!lastDemand.sales_data_available&&<span className="text-amber-300"> — دادهٔ فروش داخلی موجود نبود و درصد صفر ثبت شد.</span>}
          {" "}جست‌وجوی وب: {String(lastDemand.web_searched??0)} از {String(lastDemand.web_budget??0)}
          {Number(lastDemand.ratelimited??0)>0?` (${String(lastDemand.ratelimited)} محدودیت نرخ)`:""}
        </p>}
        {demand.length===0&&<p className="text-xs text-slate-500">هنوز بررسی تقاضا اجرا نشده.</p>}
        <div className="space-y-2">
          {demand.map(d=><div key={d.code} className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <b className="text-xs text-white">{d.product_name}</b>
              <span className={`rounded-full px-2 py-0.5 text-[10px] ${d.tier==="فرصت فروش بیشتر"?"bg-emerald-500/15 text-emerald-300":"bg-slate-500/15 text-slate-400"}`}>{d.tier}</span>
            </div>
            <div className="mt-2 grid gap-1 text-[11px] text-slate-400">
              <div className="flex items-center gap-2"><span className="w-28 shrink-0">درصد فروش منطقه</span>
                <div className="h-2 grow rounded-full bg-white/[0.06]"><div className="h-2 rounded-full bg-gradient-to-l from-violet-400 to-purple-600" style={{width:`${Math.min(100,(Number(d.kerman_sales_pct)||0)/maxPct*100)}%`}}/></div>
                <span className="w-14 shrink-0 text-left">{(Number(d.kerman_sales_pct)||0).toLocaleString("fa-IR",{maximumFractionDigits:1})}٪</span></div>
              <div className="flex items-center gap-2"><span className="w-28 shrink-0">سیگنال وب</span>
                <div className="h-2 grow rounded-full bg-white/[0.06]"><div className="h-2 rounded-full bg-gradient-to-l from-sky-400 to-cyan-600" style={{width:`${Math.min(100,(d.web_signal||0)*10)}%`}}/></div>
                <span className="w-14 shrink-0 text-left">{(d.web_signal||0).toLocaleString("fa-IR")} از ۱۰</span></div>
            </div>
            {d.category&&<p className="mt-1 text-[10px] text-slate-500">دسته: {d.category} — کد: {d.code}</p>}
          </div>)}
        </div>
      </Surface>}

      {tab==="content"&&<Surface className="space-y-3 p-5">
        {content.length===0&&<p className="text-xs text-slate-500">هنوز محتوایی تولید نشده؛ دکمهٔ «تولید محتوا با دستیار» را بزن (نیاز به دسترسی AvalAI دارد).</p>}
        {content.map(c=><div key={c.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-[10px] ${KIND_BADGES[c.kind]||"bg-white/10"}`}>{KIND_LABELS[c.kind]||c.kind}</span>
              <b className="text-xs text-white">{c.title}</b>
            </div>
            <div className="flex items-center gap-2">
              {c.status==="draft"&&c.kind==="post"&&<button type="button" disabled={busy} onClick={()=>sendToCalendar(c.id)}
                className="rounded-xl border border-violet-400/30 bg-violet-500/10 px-3 py-1.5 text-[11px] text-violet-200 hover:bg-violet-500/20">ارسال به تقویم محتوا</button>}
              {c.status==="sent_to_calendar"&&<span className="text-[10px] text-emerald-300">ارسال‌شده به تقویم</span>}
            </div>
          </div>
          <pre className="mt-2 whitespace-pre-wrap font-sans text-[11px] leading-6 text-slate-300">{c.body}</pre>
        </div>)}
      </Surface>}

      {tab==="leads"&&<Surface className="space-y-4 p-5">
        {leadSources.length>0&&<div className="flex flex-wrap gap-1.5">
          {leadSources.map(s=><span key={s.source} className="rounded-full bg-white/[0.07] px-2.5 py-1 text-[10px] text-slate-300">
            {s.source}: {s.count.toLocaleString("fa-IR")}</span>)}
        </div>}
        <div className="grid gap-3 sm:grid-cols-3">
          <input className={fieldClass} value={fSource} onChange={e=>setFSource(e.target.value)} placeholder="فیلتر منبع (مثلاً shops یا physicians:متخصص)"/>
          <input className={fieldClass} value={fCity} onChange={e=>setFCity(e.target.value)} placeholder="فیلتر شهر"/>
          <input className={fieldClass} value={fQ} onChange={e=>setFQ(e.target.value)} placeholder="جست‌وجو (نام/آدرس/تلفن)"/>
          <input className={fieldClass} value={fSpecialty} onChange={e=>setFSpecialty(e.target.value)} placeholder="عبارت تخصص برای لیدیابی زنده (مثل: پوست)"/>
        </div>
        {leads.length===0
          ?<p className="text-xs text-slate-500">لیدی یافت نشد؛ فیلترها را پاک کن یا «واردکردن از فایل‌ها» را بزن.</p>
          :<div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-right text-xs">
              <thead className="text-slate-400">
                <tr className="border-b border-white/10">
                  <th className="p-2 font-medium">نام</th>
                  <th className="p-2 font-medium">شهر</th>
                  <th className="p-2 font-medium">تلفن</th>
                  <th className="p-2 font-medium">آدرس</th>
                  <th className="p-2 font-medium">منبع</th>
                  <th className="p-2 font-medium">وضعیت</th>
                  <th className="p-2"/>
                </tr>
              </thead>
              <tbody>
                {leads.map(l=><tr key={l.id} className="border-b border-white/[0.05] text-slate-200">
                  <td className="p-2 font-medium text-white">{l.name}</td>
                  <td className="p-2">{l.city||"—"}</td>
                  <td className="p-2" dir="ltr">{l.phone||"—"}</td>
                  <td className="max-w-[240px] truncate p-2 text-slate-400" title={l.address||""}>{l.address||"—"}</td>
                  <td className="p-2"><span className="rounded-full bg-white/[0.07] px-2 py-0.5 text-[10px]">{l.source}</span></td>
                  <td className="p-2">{LEAD_STATUS_LABELS[l.status]||l.status}</td>
                  <td className="p-2"><button type="button" disabled={busy} onClick={()=>deleteLead(l.id)}
                    className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200 hover:bg-rose-500/20">حذف</button></td>
                </tr>)}
              </tbody>
            </table>
          </div>}
        {lastDiscover&&<p className="text-[10px] leading-5 text-slate-400">
          نتیجهٔ لیدیابی زنده — یافته: {String(lastDiscover.found??"0")} · ثبت‌شده: {String(lastDiscover.inserted??"0")} · تکراری: {String(lastDiscover.skipped??"0")}
          {Array.isArray(lastDiscover.notes)?` · ${(lastDiscover.notes as string[]).join(" — ")}`:null}
        </p>}
        <div className="rounded-xl border border-white/10 p-4">
          <h3 className="mb-3 text-xs font-bold text-violet-300">ثبت لید دستی</h3>
          <div className="grid gap-3 sm:grid-cols-4">
            <input className={fieldClass} value={newLead.name} onChange={e=>setNewLead({...newLead,name:e.target.value})} placeholder="نام لید *"/>
            <input className={fieldClass} value={newLead.city} onChange={e=>setNewLead({...newLead,city:e.target.value})} placeholder="شهر"/>
            <input className={fieldClass} value={newLead.phone} onChange={e=>setNewLead({...newLead,phone:e.target.value})} placeholder="تلفن" dir="ltr"/>
            <input className={fieldClass} value={newLead.address} onChange={e=>setNewLead({...newLead,address:e.target.value})} placeholder="آدرس"/>
          </div>
          <button type="button" disabled={busy} onClick={saveLead} className={`mt-3 ${primaryButton}`}>ثبت لید</button>
        </div>
      </Surface>}
    </div>
  </PortalShell>;
}
