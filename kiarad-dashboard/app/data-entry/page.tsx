"use client";
import Link from "next/link";
import { useEffect,useState,type FormEvent } from "react";
import { PortalShell,Surface,fieldClass,primaryButton } from "../../components/portal-shell";
import { authFetch,secureApi } from "../../lib/secure-api";
import { IranDateInput } from "../../components/IranDateInput";

type EntryField={key:string;label:string;type:string;required:boolean};
type Entity={id:string;label:string;fields:EntryField[];holoo:boolean;href:string};
type Preview={id:number;entity:string;status:string;row_count:number;rows:{id:number|null;action:string;values:Record<string,unknown>}[]};
type Refresh={status:string;finished_at?:string|null;sources:{kind:string;count:number;ok:boolean;complete:boolean}[]};

export default function DataEntryPage(){
 const [entities,setEntities]=useState<Entity[]>([]),[entity,setEntity]=useState("products");
 const [mode,setMode]=useState<"manual"|"excel">("manual"),[unit,setUnit]=useState("IRR");
 const [rows,setRows]=useState<Record<string,string>[]>([{}]);
 const [file,setFile]=useState<File|null>(null),[sheet,setSheet]=useState("");
 const [preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
 const [restoreId,setRestoreId]=useState("");
 const [refresh,setRefresh]=useState<Refresh|null>(null);
 useEffect(()=>{
  let active=true;
  secureApi<{entities:Entity[]}>("/data-entry/schema").then(data=>{
   if(!active)return;setEntities(data.entities);
   const params=new URLSearchParams(window.location.search);
   const requested=params.get("entity");
   const allowedEntity=data.entities.find(item=>item.id===requested);
   setEntity(allowedEntity?.id||data.entities[0]?.id||"products");
   const rowCount=params.get("rows");
   if(allowedEntity?.id==="targets"&&rowCount&&/^\d{1,3}$/.test(rowCount)){
    const count=Number(rowCount);
    if(count>=1&&count<=500)setRows(Array.from({length:count},()=>({})));
   }
  }).catch(error=>{if(active)setMessage(error instanceof Error?error.message:"خواندن تنظیمات ورود انجام نشد.");});
  return()=>{active=false;};
 },[]);
 const selected=entities.find(item=>item.id===entity);
 useEffect(()=>{
  if(!selected?.holoo)return;
  let active=true;let timer:number|undefined;
  const poll=async()=>{
   try{const status=await secureApi<Refresh>(`/data-entry/${entity}/holoo-refresh`);if(active){setRefresh(status);timer=window.setTimeout(()=>void poll(),status.status==="running"?5000:15000);}}
   catch{if(active)timer=window.setTimeout(()=>void poll(),15000);}
  };
  void poll();return()=>{active=false;if(timer)window.clearTimeout(timer);};
 },[entity,selected?.holoo]);
 const refreshHoloo=async()=>{
  if(busy)return;setBusy(true);
  try{setRefresh(await secureApi<Refresh>(`/data-entry/${entity}/holoo-refresh`,{method:"POST"}));setMessage("دریافت خواندنی هلو در پس‌زمینه شروع شد؛ ویرایش‌های دستی حفظ می‌شوند.");}
  catch(error){setMessage(error instanceof Error?error.message:"شروع دریافت انجام نشد.");}finally{setBusy(false);}
 };
 const reset=()=>{setPreview(null);setMessage("");};
 const edit=(index:number,key:string,value:string)=>{setRows(current=>current.map((row,i)=>i===index?{...row,[key]:value}:row));reset();};
 const prepare=async(event:FormEvent)=>{
  event.preventDefault();if(!selected||busy)return;setBusy(true);setMessage("");setPreview(null);
  try{
   if(mode==="manual")setPreview(await secureApi<Preview>(`/data-entry/${entity}/manual/preview`,{method:"POST",body:JSON.stringify({unit,rows})}));
   else{
    if(!file)throw new Error("فایل اکسل را انتخاب کنید.");
    const body=new FormData();body.append("file",file);body.append("unit",unit);body.append("sheet_name",sheet);
    const response=await authFetch(`/data-entry/${entity}/excel/preview`,{method:"POST",body});
    const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==="string"?result.detail:"ساختار ورودی معتبر نیست.");setPreview(result);
   }
   setMessage("پیش‌نمایش آماده است؛ ردیف‌ها را بررسی کنید. هنوز روی اطلاعات اصلی اعمال نشده است.");
  }catch(error){setMessage(error instanceof Error?error.message:"پیش‌نمایش انجام نشد.");}finally{setBusy(false);}
 };
 const commit=async()=>{
  if(!preview||preview.status!=="preview"||busy||!window.confirm("همهٔ ردیف‌های پیش‌نمایش بررسی شدند و در پنل ثبت شوند؟ فیلدهای کالایی و مشتریِ تغییرکرده، دستی می‌مانند تا خودتان به هلو بازگردانید. هیچ تغییری به هلو ارسال نمی‌شود."))return;
  setBusy(true);
  try{
   const result=await secureApi<{created:number;updated:number}>(`/data-entry/${entity}/${preview.id}/commit`,{method:"POST",body:JSON.stringify({confirm:true})});
   setPreview({...preview,status:"committed"});setMessage(`${result.created.toLocaleString("fa-IR")} ردیف جدید و ${result.updated.toLocaleString("fa-IR")} ردیف ویرایش‌شده ثبت شد؛ هلو تغییری نکرد.`);
  }catch(error){setMessage(error instanceof Error?error.message:"ثبت انجام نشد.");}finally{setBusy(false);}
 };
 const download=async()=>{
  try{const response=await authFetch(`/data-entry/${entity}/template`);if(!response.ok)throw new Error("دریافت قالب انجام نشد.");
   const url=URL.createObjectURL(await response.blob());const anchor=document.createElement("a");anchor.href=url;anchor.download=`${entity}-entry.xlsx`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(error){setMessage(error instanceof Error?error.message:"قالب دریافت نشد.");}
 };
 const restore=async()=>{
  if(!/^[1-9]\d*$/.test(restoreId)||!window.confirm("نام و فیلدهای موجود در منبع تازهٔ هلو جایگزین شوند و اولویت دستی همان فیلدها برداشته شود؟"))return;
  setBusy(true);try{await secureApi(`/data-entry/${entity}/${restoreId}/restore-holoo`,{method:"POST"});setMessage("فیلدهای موجود در منبع تازه به هلو بازگردانده شدند؛ سایر مشخصات دستی حفظ شدند.");setPreview(null);}catch(error){setMessage(error instanceof Error?error.message:"بازگشت به هلو انجام نشد.");}finally{setBusy(false);}
 };
 return <PortalShell title="ورود و منبع اطلاعات" eyebrow="پیش‌نمایش، بررسی و ثبت">
  <div className="space-y-4">
   <Surface className="p-5 text-xs leading-7 text-slate-300">کد کالا و مشتری باید دقیق باشد؛ بر اساس نام، رکورد یا ویزیتور حدس زده نمی‌شود. ورود دستی و اکسل فقط پس از پیش‌نمایش و تأیید شما روی پنل اعمال می‌شود. فیلدهای واردشدهٔ کالا و مشتری از بازنویسی خودکار هلو محافظت می‌شوند؛ ثبت یا اصلاح سند در هلو انجام نمی‌شود.</Surface>
   {message&&<p role="status" className="rounded-xl border border-amber-300/20 bg-amber-500/10 p-4 text-xs leading-7 text-amber-200">{message}</p>}
   <Surface className="p-5"><form onSubmit={prepare} className="space-y-4">
    <div className="grid gap-4 sm:grid-cols-3">
     <label className="text-xs">بخش<select className={fieldClass} value={entity} disabled={busy} onChange={e=>{setEntity(e.target.value);setRows([{}]);setFile(null);reset();}}>{entities.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
     <label className="text-xs">روش ورود<select className={fieldClass} value={mode} disabled={busy} onChange={e=>{setMode(e.target.value as "manual"|"excel");reset();}}><option value="manual">دستی</option><option value="excel">اکسل</option></select></label>
     <label className="text-xs">واحد همهٔ مبالغ<select className={fieldClass} value={unit} disabled={busy} onChange={e=>{setUnit(e.target.value);reset();}}><option value="IRR">ریال</option><option value="TOMAN">تومان</option></select></label>
    </div>
    {selected&&<p className="text-xs leading-7 text-slate-400">{selected.holoo?"منبع هلو برای این بخش از دریافت خودکار موجود خوانده می‌شود؛ اولویت فیلدهای دستی جداگانه حفظ می‌شود.":"وب‌سرویس فعلی برای این بخش منبع مستقیم تأییدشده ندارد؛ اطلاعات باید دستی یا از اکسل وارد شوند."} <Link className="text-violet-300 underline" href={selected.href}>باز کردن بخش مرتبط</Link></p>}
    {selected?.holoo&&<div className="rounded-xl border border-white/10 p-3 text-xs leading-7 text-slate-300"><button type="button" onClick={()=>void refreshHoloo()} disabled={busy||refresh?.status==="running"} className={primaryButton}>{refresh?.status==="running"?"دریافت هلو در حال اجراست…":"دریافت تازه از هلو"}</button><p className="mt-2">{refresh?.status==="completed"?"دریافت و تطبیق منابع کامل شد.":refresh?.status==="failed"||refresh?.status==="partial"?"دریافت یا تطبیق کامل نشده است؛ وضعیت سرویس هلو را بررسی کنید.":refresh?.status==="running"?"بستن صفحه دریافت سمت سرور را قطع نمی‌کند.":"دریافت خودکار طبق برنامهٔ میزبان انجام می‌شود؛ این دکمه درخواست دریافت تازه است."}</p>{refresh?.sources.map(source=><p key={source.kind}>{source.count.toLocaleString("fa-IR")} ردیف؛ {source.ok&&source.complete?"پاسخ منبع کامل":"پاسخ منبع ناقص"}</p>)}</div>}
    {mode==="manual"?<>
     {rows.map((row,index)=><fieldset key={index} disabled={busy} className="rounded-xl border border-white/10 p-4"><legend className="px-2 text-xs">ردیف {(index+1).toLocaleString("fa-IR")}</legend><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{selected?.fields.map(field=><label key={field.key} className="text-[11px] text-slate-300">{field.label}{field.required?" *":""}{field.type==="date"?<IranDateInput required={field.required} value={row[field.key]||""} onChange={value=>edit(index,field.key,value)} className={fieldClass}/>:<input required={field.required} value={row[field.key]||""} maxLength={field.key==="note"?1000:150} onChange={e=>edit(index,field.key,e.target.value)} className={fieldClass} inputMode={["text","date"].includes(field.type)?"text":"decimal"}/>}</label>)}</div>{rows.length>1&&<button type="button" onClick={()=>{setRows(rows.filter((_,i)=>i!==index));reset();}} className="mt-3 text-xs text-rose-300">حذف ردیف از پیش‌نویس</button>}</fieldset>)}
     <button type="button" disabled={rows.length>=500||busy} onClick={()=>{setRows([...rows,{}]);reset();}} className="text-xs text-violet-300">افزودن ردیف دستی</button>
    </>:<div className="space-y-3"><button type="button" onClick={download} className="text-xs text-violet-300 underline">دریافت قالب همین بخش</button><p className="text-xs leading-6 text-slate-400">فایل با مقادیر ساده، بدون فرمول و با حداکثر پانصد ردیف باشد. کدها را متن نگه دارید. سلول خالی اختیاری، مقدار قبلی را پاک نمی‌کند.</p><input type="file" accept=".xlsx" required onChange={e=>{setFile(e.target.files?.[0]||null);reset();}} className={fieldClass}/><label className="block text-xs">نام شیت ـ خالی برای اولین شیت<input value={sheet} onChange={e=>{setSheet(e.target.value);reset();}} className={fieldClass}/></label></div>}
    <button disabled={busy||!selected} className={primaryButton}>{busy?"در حال بررسی…":"اعتبارسنجی و پیش‌نمایش"}</button>
   </form></Surface>
   {preview&&<Surface className="p-5"><div className="mb-4 flex flex-wrap items-center justify-between gap-3"><h2 className="text-sm font-bold">پیش‌نمایش {preview.row_count.toLocaleString("fa-IR")} ردیف</h2><button disabled={busy||preview.status!=="preview"} onClick={commit} className={primaryButton}>{preview.status==="committed"?"قبلاً ثبت شده":"تأیید و ثبت همهٔ ردیف‌ها"}</button></div><div className="overflow-x-auto"><table className="w-full min-w-[600px] text-right text-xs"><thead><tr><th className="p-2">عملیات و شناسه</th>{selected?.fields.map(field=><th className="p-2" key={field.key}>{field.label}</th>)}</tr></thead><tbody>{preview.rows.map((row,index)=><tr key={index} className="border-t border-white/10"><td className="p-2">{row.action==="create"?"ایجاد":"ویرایش"} {row.id??""}</td>{selected?.fields.map(field=><td className="p-2" key={field.key}>{String(row.values[field.key]??"—")}</td>)}</tr>)}</tbody></table></div><p className="mt-4 text-xs text-amber-200">مبالغ پیش‌نمایش به ریال هستند. تغییر دیتا پس از پیش‌نمایش، ثبت را متوقف می‌کند؛ دوباره پیش‌نمایش بگیرید.</p></Surface>}
   {selected?.holoo&&<Surface className="p-5"><h2 className="text-sm font-bold">بازگشت یک رکورد به منبع هلو</h2><p className="my-3 text-xs leading-6 text-slate-400">شناسهٔ داخلی رکورد را از پیش‌نمایش بخوانید. نام و فیلدهای عرضه‌شده در نسخهٔ تازهٔ هلو بازگردانده می‌شوند؛ تلفن، شهر و سایر مشخصات محلی حفظ می‌شوند.</p><div className="flex flex-wrap gap-3"><input aria-label="شناسه داخلی برای بازگشت منبع" value={restoreId} onChange={e=>setRestoreId(e.target.value)} className={fieldClass+" max-w-52"} placeholder="شناسه داخلی"/><button disabled={busy||!restoreId} onClick={restore} className={primaryButton}>بررسی و بازگشت به هلو</button></div></Surface>}
   <Surface className="p-5 text-xs leading-8 text-slate-300"><h2 className="text-sm font-bold">سایر اطلاعات</h2><p><Link href="/treasury" className="text-violet-300 underline">خزانه: ورود دستی و اکسل حساب‌ها، چک‌ها، خرید، فروش، برگشت و گزارش ماهانه</Link></p><p><Link href="/personnel" className="text-violet-300 underline">پرسنل و حساب ورود</Link> · <Link href="/compensation" className="text-violet-300 underline">قرارداد و فرمول</Link> · <Link href="/payroll" className="text-violet-300 underline">بازبینی کارکرد و حقوق</Link></p><p>دادهٔ حقوق و حضور از هلو حدس زده نمی‌شود؛ قرارداد، انتساب فروش و تأیید کارکرد مسیر مستقل دارند.</p></Surface>
  </div>
 </PortalShell>;
}
