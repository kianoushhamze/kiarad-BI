"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi, getSavedUser } from "../../lib/secure-api";
import { formatIranDateTime } from "../../lib/iran-date";

type Listing={
  id:number;platform:string;code:string;external_id:string|null;
  price_mode:"auto"|"manual";manual_price_irr:number|null;price_factor:number|null;
  active:boolean;last_push_at:string|null;holoo_stock:number|null;
  product_name:string|null;available:number|null;
};
type Product={code:string;name:string};
type UnlistedProduct={code:string;name:string;price:number|null;stock:number|null};
type CreateProposal={
  id:number;platform:string;code:string;product_name:string;suggested_title:string;
  category_id:number|null;price_irr:number|null;stock:number;image_url:string|null;
  gtin:string|null;status:string;receipt:{receipt?:unknown;errors?:string[]}|null;
  created_at:string|null;confirmed_at:string|null;
};
type PlatformOrder={
  platform:string;order_ref:string;order_status:string|null;fetched_at:string|null;
  proforma_id:number|null;proforma_status:string|null;holoo_registered:boolean|null;
  total_amount:number|null;reserved_lines:number|null;
};
const PLATFORM_LABELS:Record<string,string>={digikala:"دیجی‌کالا",site:"سایت کیاراد"};

export default function PlatformsPage(){
  const user=getSavedUser();
  const allowed=user?.role==="ceo";
  const [items,setItems]=useState<Listing[]>([]);
  const [orders,setOrders]=useState<PlatformOrder[]>([]);
  const [products,setProducts]=useState<Product[]>([]);
  const [unlisted,setUnlisted]=useState<UnlistedProduct[]>([]);
  const [proposals,setProposals]=useState<CreateProposal[]>([]);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [pushResult,setPushResult]=useState<{applied:number;failed:number;lines:string[]} | null>(null);
  const [importResult,setImportResult]=useState<{applied:number;skipped:number} | null>(null);
  const fileRef=useRef<HTMLInputElement>(null);
  const [form,setForm]=useState({code:"",platform:"digikala",price_mode:"auto" as "auto"|"manual",
    manual_price_irr:0,price_factor:1,active:true});

  const load=useCallback(function(){
    secureApi<{items:Listing[]}>("/platforms/overview")
      .then(v=>{setItems(v.items);setError("");})
      .catch(r=>setError(r instanceof Error?r.message:"دریافت سکوها ناموفق بود."));
    secureApi<{items:PlatformOrder[]}>("/platforms/orders")
      .then(v=>setOrders(v.items))
      .catch(()=>{});
    secureApi<{items:CreateProposal[]}>("/platforms/create-product-proposals")
      .then(v=>setProposals(v.items))
      .catch(()=>{});
    secureApi<{items:UnlistedProduct[]}>("/platforms/create-product-proposals/unlisted")
      .then(v=>setUnlisted(v.items))
      .catch(()=>{});
  },[]);

  useEffect(function(){
    if(!allowed)return;
    load();
    secureApi<{items:Product[]}>("/catalog/products")
      .then(v=>setProducts(v.items))
      .catch(()=>{});
  },[allowed,load]);

  async function addListing(){
    if(busy)return;setBusy(true);setError("");setNotice("");
    try{
      await secureApi("/platforms/listing",{method:"POST",body:JSON.stringify({
        code:form.code,platform:form.platform.trim()||"digikala",price_mode:form.price_mode,
        manual_price_irr:form.price_mode==="manual"?form.manual_price_irr:null,
        price_factor:form.price_factor,active:form.active})});
      setNotice("لیستینگ ثبت شد.");
      setForm({...form,code:""});load();
    }catch(r){setError(r instanceof Error?r.message:"ثبت لیستینگ ناموفق بود.");}
    finally{setBusy(false);}
  }

  async function toggleActive(item:Listing){
    setBusy(true);setError("");
    try{await secureApi("/platforms/listing/"+item.id,{method:"PATCH",body:JSON.stringify({active:!item.active})});load();}
    catch(r){setError(r instanceof Error?r.message:"تغییر وضعیت ناموفق بود.");}
    finally{setBusy(false);}
  }

  async function importPrices(){
    const file=fileRef.current?.files?.[0];
    if(!file){setError("ابتدا یک فایل اکسل یا CSV انتخاب کن.");return;}
    setBusy(true);setError("");setImportResult(null);
    try{
      const fd=new FormData();
      fd.append("file",file);
      const res=await secureApi<{applied:number;skipped:number}>("/platforms/prices/import",{method:"POST",body:fd});
      setImportResult({applied:res.applied??0,skipped:res.skipped??0});
      load();
    }catch(r){setError(r instanceof Error?r.message:"درون‌ریزی قیمت‌ها ناموفق بود.");}
    finally{setBusy(false);if(fileRef.current)fileRef.current.value="";}
  }

  async function tickHolooRegistered(order:PlatformOrder){
    if(busy)return;setBusy(true);setError("");
    try{
      await secureApi("/platforms/orders/"+encodeURIComponent(order.order_ref)+"/holoo-registered",{method:"POST"});
      setNotice("وضعیت «ثبت شد در هلو» به‌روزرسانی شد.");
      load();
    }catch(r){setError(r instanceof Error?r.message:"به‌روزرسانی وضعیت ناموفق بود.");}
    finally{setBusy(false);}
  }

  async function pushStock(){
    if(busy)return;setBusy(true);setError("");setPushResult(null);
    try{
      const res=await secureApi<{applied:number;failed:number;results?:Array<{platform?:string;code?:string;ok?:boolean;error?:string}>}>("/platforms/push-stock",{method:"POST"});
      const lines=(res.results||[]).map(x=>`${x.platform||"?"} / ${x.code||"?"}: ${x.ok?"موجودی اعمال شد":(x.error||"خطا")}`);
      setPushResult({applied:res.applied??0,failed:res.failed??0,lines});
      load();
    }catch(r){setError(r instanceof Error?r.message:"اعمال موجودی ناموفق بود.");}
    finally{setBusy(false);}
  }

  async function proposeListing(p:UnlistedProduct){
    if(busy)return;setBusy(true);setError("");setNotice("");
    try{
      await secureApi("/platforms/create-product-proposals",{method:"POST",body:JSON.stringify({
        code:p.code,suggested_title:p.name,price_irr:p.price??undefined,stock:p.stock??0})});
      setNotice("پیشنهاد ثبت در دیجی‌کالا ایجاد شد و منتظر تایید شماست.");
      load();
    }catch(r){setError(r instanceof Error?r.message:"ایجاد پیشنهاد ناموفق بود.");}
    finally{setBusy(false);}
  }


  async function rejectProposal(pr:CreateProposal){
    if(busy)return;setBusy(true);setError("");
    try{await secureApi("/platforms/create-product-proposals/"+pr.id+"/reject",{method:"POST"});load();}
    catch(r){setError(r instanceof Error?r.message:"رد پیشنهاد ناموفق بود.");}
    finally{setBusy(false);}
  }

  if(!allowed)return <PortalShell title="مدیریت سکوهای فروش" eyebrow="فروش آنلاین">
    <div className="mx-auto max-w-3xl p-6"><Surface className="p-6 text-center">
      <p className="text-sm text-amber-300">دسترسی مدیریتی لازم است</p>
      <p className="mt-2 text-xs text-slate-400">این صفحه فقط برای نقش مدیرعامل (ceo) فعال است.</p>
    </Surface></div>
  </PortalShell>;

  return <PortalShell title="مدیریت سکوهای فروش" eyebrow="فروش آنلاین">
    <div className="mx-auto max-w-6xl space-y-5 p-4 lg:p-6">
      {error&&<p role="alert" className="text-rose-300">{error}</p>}
      {notice&&<p className="text-emerald-300">{notice}</p>}

      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">لیستینگ جدید در سکو</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label className="space-y-1 text-xs text-slate-400">کالا
            <select className={fieldClass} value={form.code} onChange={e=>setForm({...form,code:e.target.value})}>
              <option value="">— انتخاب کالا —</option>
              {products.map(p=><option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
            </select></label>
          <label className="space-y-1 text-xs text-slate-400">سکو
            <select className={fieldClass} value={form.platform} onChange={e=>setForm({...form,platform:e.target.value})}>
              <option value="digikala">دیجی‌کالا</option>
              <option value="site">سایت کیاراد</option>
            </select></label>
          <div className="space-y-1 text-xs text-slate-400">حالت قیمت
            <div className="flex items-center gap-4 pt-1.5 text-xs text-white">
              <label className="flex items-center gap-1.5"><input type="radio" checked={form.price_mode==="auto"} onChange={()=>setForm({...form,price_mode:"auto"})}/>خودکار</label>
              <label className="flex items-center gap-1.5"><input type="radio" checked={form.price_mode==="manual"} onChange={()=>setForm({...form,price_mode:"manual"})}/>دستی</label>
            </div></div>
          <label className="space-y-1 text-xs text-slate-400">قیمت دستی (ریال)
            <input type="number" min={0} className={fieldClass} disabled={form.price_mode!=="manual"}
              value={form.manual_price_irr} onChange={e=>setForm({...form,manual_price_irr:Number(e.target.value)||0})}/></label>
          <label className="space-y-1 text-xs text-slate-400">ضریب قیمت
            <input type="number" step="0.01" min={0} className={fieldClass}
              value={form.price_factor} onChange={e=>setForm({...form,price_factor:Number(e.target.value)||0})}/></label>
          <label className="flex items-center gap-2 self-end text-xs text-white">
            <input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/>فعال</label>
        </div>
        <button className={primaryButton} disabled={busy||!form.code} onClick={()=>void addListing()}>
          {busy?"در حال ثبت…":"ثبت لیستینگ"}</button>
      </Surface>

      <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">درون‌ریزی قیمت از فایل</h2>
        <p className="text-xs text-slate-400">فایل اکسل یا CSV شامل کد کالا و قیمت را انتخاب کن؛ ستون‌های اضافه نادیده گرفته می‌شوند.</p>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="text-xs text-slate-300" />
          <button className={primaryButton} disabled={busy} onClick={()=>void importPrices()}>درون‌ریزی قیمت‌ها</button>
        </div>
        {importResult&&<p className="text-xs text-emerald-300">نتیجه: {importResult.applied.toLocaleString("fa-IR")} ردیف اعمال شد، {importResult.skipped.toLocaleString("fa-IR")} ردیف رد شد.</p>}
      </Surface>

      <Surface className="space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-bold">لیستینگ‌های سکوها</h2>
          <button className={primaryButton} disabled={busy} onClick={()=>void pushStock()}>
            {busy?"در حال اعمال…":"اعمال موجودی به همه سکوها"}</button>
        </div>
        {pushResult&&<div className="rounded-xl border border-white/10 p-3 text-xs">
          <p className={pushResult.failed>0?"text-amber-300":"text-emerald-300"}>
            {pushResult.applied.toLocaleString("fa-IR")} مورد موفق، {pushResult.failed.toLocaleString("fa-IR")} مورد ناموفق.</p>
          {pushResult.lines.length>0&&<ul className="mt-2 space-y-1 text-slate-300">{pushResult.lines.map((l,i)=><li key={i}>{l}</li>)}</ul>}
        </div>}
        {items.length===0?<p className="text-sm text-slate-400">هنوز لیستینگی ثبت نشده است.</p>
          :<div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-right text-xs">
              <thead className="text-slate-400">
                <tr className="border-b border-white/10">
                  <th className="p-2 font-medium">کالا</th>
                  <th className="p-2 font-medium">سکو</th>
                  <th className="p-2 font-medium">موجودی مجازی</th>
                  <th className="p-2 font-medium">موجودی هلو</th>
                  <th className="p-2 font-medium">حالت قیمت</th>
                  <th className="p-2 font-medium">قیمت دستی</th>
                  <th className="p-2 font-medium">ضریب</th>
                  <th className="p-2 font-medium">فعال</th>
                  <th className="p-2 font-medium">آخرین push</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item=><tr key={item.id} className="border-b border-white/[0.05] text-slate-200">
                  <td className="p-2"><b className="text-white">{item.product_name||"—"}</b><br/><span className="text-[10px] text-slate-500">{item.code}</span></td>
                  <td className="p-2">{item.platform}</td>
                  <td className={`p-2 font-bold${(item.available??0)<=3?" text-rose-400":" text-emerald-300"}`}>
                    {item.available===null?"—":item.available.toLocaleString("fa-IR")}
                    {(item.available??0)<=3&&item.available!==null&&<span className="mr-1 text-[10px]">کم!</span>}</td>
                  <td className="p-2">{item.holoo_stock===null?"—":item.holoo_stock.toLocaleString("fa-IR")}</td>
                  <td className="p-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${item.price_mode==="auto"?"bg-sky-500/15 text-sky-300":"bg-amber-500/15 text-amber-300"}`}>
                      {item.price_mode==="auto"?"خودکار":"دستی"}</span></td>
                  <td className="p-2">{item.manual_price_irr===null?"—":item.manual_price_irr.toLocaleString("fa-IR")}</td>
                  <td className="p-2">{item.price_factor===null?"—":item.price_factor}</td>
                  <td className="p-2"><button className={`rounded-full px-2 py-1 text-[10px] ${item.active?"bg-emerald-500/15 text-emerald-300":"bg-white/5 text-slate-500"}`} disabled={busy} onClick={()=>void toggleActive(item)}>{item.active?"فعال":"غیرفعال"}</button></td>
                  <td className="p-2 text-[10px] text-slate-400">{item.last_push_at?formatIranDateTime(item.last_push_at):"—"}</td>
                </tr>)}
              </tbody>
            </table>
          </div>}
      </Surface>

      <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">سفارش‌های سکوها</h2>
        <p className="text-xs text-amber-200">هلو از این مسیر تغییر نمی‌کند؛ فاکتور رسمی فردا از داشبورد در هلو زده می‌شود.</p>
        {orders.length===0?<p className="text-sm text-slate-400">هنوز سفارشی از سکوها ثبت نشده است.</p>
          :<div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-right text-xs">
              <thead className="text-slate-400">
                <tr className="border-b border-white/10">
                  <th className="p-2 font-medium">سکو</th>
                  <th className="p-2 font-medium">شماره سفارش</th>
                  <th className="p-2 font-medium">مبلغ (ریال)</th>
                  <th className="p-2 font-medium">پیش‌فاکتور داخلی</th>
                  <th className="p-2 font-medium">ثبت شد در هلو</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o=><tr key={o.platform+"/"+o.order_ref} className="border-b border-white/[0.05] text-slate-200">
                  <td className="p-2">{PLATFORM_LABELS[o.platform]||o.platform}</td>
                  <td className="p-2 font-bold text-white">{o.order_ref}</td>
                  <td className="p-2">{o.total_amount===null||o.total_amount===undefined?"—":Number(o.total_amount).toLocaleString("fa-IR")}</td>
                  <td className="p-2">{o.proforma_id
                    ?<a href="/proformas" className="text-violet-300 underline">پیش‌فاکتور #{o.proforma_id.toLocaleString("fa-IR")}</a>
                    :<span className="text-slate-500">—</span>}</td>
                  <td className="p-2">
                    {o.holoo_registered
                      ?<span className="rounded-full bg-emerald-500/15 px-2 py-1 text-[10px] text-emerald-300">ثبت شد در هلو ✓</span>
                      :<button className="rounded-full bg-white/5 px-3 py-1 text-[10px] text-slate-300 hover:bg-white/10" disabled={busy||!o.proforma_id} onClick={()=>void tickHolooRegistered(o)}>ثبت شد در هلو</button>}
                  </td>
                </tr>)}
              </tbody>
            </table>
          </div>}
      </Surface>

      <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">کالاهای ثبت‌نشده در دیجی‌کالا</h2>
        <p className="text-xs text-slate-400">این کالاها در هلو هستند اما در دیجی‌کالا لیست نشده‌اند. با دکمه زیر پیشنهاد ثبت ساخته می‌شود؛ ارسال به دیجی‌کالا فقط بعد از تایید شما انجام می‌گیرد.</p>
        {unlisted.length===0?<p className="text-sm text-slate-400">همه کالاهای فعال در دیجی‌کالا ثبت شده‌اند.</p>
          :<div className="max-h-72 space-y-1 overflow-y-auto">
            {unlisted.map(p=><div key={p.code} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 px-3 py-2 text-xs">
              <span className="text-slate-200"><b className="text-white">{p.name}</b> <span className="text-[10px] text-slate-500">{p.code}</span></span>
              <span className="text-slate-400">{p.price===null?"":"قیمت: "+p.price.toLocaleString("fa-IR")+" ریال"}</span>
              <button className={primaryButton} disabled={busy} onClick={()=>void proposeListing(p)}>پیشنهاد ثبت در دیجی‌کالا</button>
            </div>)}
          </div>}
      </Surface>

      <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">پیشنهادهای ثبت در دیجی‌کالا</h2>
        <p className="text-xs text-amber-200">API رسمی فروشندهٔ دیجی‌کالا فعلاً مسیر تأییدشده‌ای برای ساخت کالای جدید ندارد. این بخش فقط پیش‌نویس پیشنهاد را نگه می‌دارد؛ کالا را دستی در پنل فروشنده ثبت کنید و سپس از صفحهٔ «نگاشت کالاهای دیجی‌کالا» متغیر آن را به کالای هلو وصل کنید. هیچ درخواست ناموفق یا ارسال ساختگی به API انجام نمی‌شود.</p>
        {proposals.length===0?<p className="text-sm text-slate-400">پیشنهادی ثبت نشده است.</p>
          :<div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-right text-xs">
              <thead className="text-slate-400">
                <tr className="border-b border-white/10">
                  <th className="p-2 font-medium">کالا</th>
                  <th className="p-2 font-medium">عنوان پیشنهادی</th>
                  <th className="p-2 font-medium">قیمت (ریال)</th>
                  <th className="p-2 font-medium">موجودی</th>
                  <th className="p-2 font-medium">وضعیت</th>
                  <th className="p-2 font-medium">اقدام</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map(pr=><tr key={pr.id} className="border-b border-white/[0.05] text-slate-200">
                  <td className="p-2"><b className="text-white">{pr.product_name}</b><br/><span className="text-[10px] text-slate-500">{pr.code}</span></td>
                  <td className="p-2">{pr.suggested_title}</td>
                  <td className="p-2">{pr.price_irr===null?"—":pr.price_irr.toLocaleString("fa-IR")}</td>
                  <td className="p-2">{pr.stock.toLocaleString("fa-IR")}</td>
                  <td className="p-2">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${pr.status==="pending"?"bg-amber-500/15 text-amber-300":pr.status==="submitted"?"bg-emerald-500/15 text-emerald-300":"bg-rose-500/15 text-rose-300"}`}>
                      {pr.status==="pending"?"پیش‌نویس؛ ثبت دستی لازم":pr.status==="submitted"?"ارسال شد":pr.status==="rejected"?"رد شد":"ناموفق"}</span>
                  </td>
                  <td className="p-2 space-x-1">
                    {pr.status==="pending"&&<>
                      <span className="text-[10px] text-amber-200">ارسال خودکار پشتیبانی نمی‌شود</span>
                      <button className="rounded-full bg-white/5 px-3 py-1 text-[10px] text-slate-300 hover:bg-white/10" disabled={busy} onClick={()=>void rejectProposal(pr)}>حذف پیشنهاد</button>
                    </>}
                    {pr.status!=="pending"&&pr.receipt?.errors?.length?<span className="text-[10px] text-rose-300">{pr.receipt.errors.join("، ")}</span>:null}
                  </td>
                </tr>)}
              </tbody>
            </table>
          </div>}
      </Surface>

      <a href="/online-sales" className="block text-violet-300">بازگشت به کانال‌های آنلاین</a>
    </div>
  </PortalShell>;
}
