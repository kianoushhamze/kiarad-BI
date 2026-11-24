/* TAB SWITCHER ADDED */
"use client";

function isCatalogViewer(): boolean {
  try {
    const u = localStorage.getItem("kiarad_session_user");
    if (!u) return false;
    const o = JSON.parse(u);
    return o.role === "salesperson" || o.role === "sales_manager";
  } catch { return false; }
}





import { useCallback, useEffect, useState } from "react";
import { DataEntryLink } from "../../components/data-entry-link";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
import { MediaUploader } from "../../components/media-uploader";
import { CatalogFiles } from "../../components/catalog-files";
import { InventoryIntelligence } from "../../components/inventory-intelligence";
import { matchesSearch } from "../../lib/text-search";

type Product = { id: number; code?: string; name?: string; category?: string; price?: number; price2?: number | null; stock?: number; min_stock?: number; is_active?: number; updated_at?: string; manual_fields?: string[] };
type Channel = { id?: number; channel?: string; external_id?: string; is_active?: number };
const money = (n?: number) => new Intl.NumberFormat("fa-IR").format(n ?? 0) + " ریال";
function isCatalogManager(): boolean { try { const user=JSON.parse(localStorage.getItem("kiarad_session_user")||"null"); return ["ceo","sales_manager","finance"].includes(user?.role); } catch { return false; } }

export default function CatalogPage() {
  const [items, setItems] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channel, setChannel] = useState("digikala");
  const [externalId, setExternalId] = useState("");
  const [loading, setLoading] = useState(true);
  const [catalogManager,setCatalogManager]=useState(false),[catalogViewer,setCatalogViewer]=useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [extra, setExtra] = useState<"files" | "intelligence" | null>(null);
  const [stockFilter, setStockFilter] = useState<"all" | "low" | "empty">("all");
  const [edit, setEdit] = useState({ price: "", price2: "", stock: "", min_stock: "" });
  const load = useCallback(async () => { setLoading(true); try { const r = await secureApi<{items: Product[]}>("/catalog/products"); setItems(r.items ?? []); setMessage(""); } catch (e) { setMessage(e instanceof Error ? e.message : "خطا در دریافت کالاها"); } finally { setLoading(false); } }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) { const manager=isCatalogManager();setCatalogManager(manager);setCatalogViewer(isCatalogViewer());if(window.location.hash==="#intelligence"&&manager)setExtra("intelligence"); void load(); } });
    return () => { active = false; };
  }, [load]);
  const select = async (p: Product) => { setSelected(p); setEdit({price:String(p.price??0),price2:p.price2==null?"":String(p.price2),stock:String(p.stock??0),min_stock:String(p.min_stock??0)}); setMessage(""); try { const channelResult = await secureApi<{items: Channel[]}>(`/catalog/products/${p.id}/channels`); setChannels(channelResult.items ?? []); } catch (e) { setMessage(e instanceof Error ? e.message : "دریافت اطلاعات کالا انجام نشد"); } };
  const saveProduct = async () => {
    if(!selected)return;
    const values:Record<string,number>={};
    for(const key of ["price","price2","stock","min_stock"] as const){
      if(key==="price2"&&!edit[key].trim())continue;
      const value=Number(edit[key]);
      if(!Number.isFinite(value)||value<0){setMessage("قیمت و تعداد باید عدد معتبر و نامنفی باشند.");return;}
      if(value!==Number(selected[key]))values[key]=value;
    }
    if(!Object.keys(values).length){setMessage("مقداری تغییر نکرده است.");return;}
    try {
      await secureApi(`/catalog/products/${selected.id}`,{method:"PATCH",body:JSON.stringify(values)});
      await load();
      setSelected({...selected,...values,manual_fields:[...new Set([...(selected.manual_fields||[]),...Object.keys(values)])]});
      setMessage("ویرایش دستی ذخیره شد و دریافت بعدی هلو آن را بازنویسی نمی‌کند.");
    } catch(error){setMessage(error instanceof Error?error.message:"ذخیره انجام نشد.");}
  };
  const restoreHoloo = async () => {
    if(!selected||!window.confirm("قیمت‌ها، موجودی و نام این کالا از آخرین نسخهٔ تازهٔ هلو جایگزین شوند؟ مشخصات محلی حفظ می‌شوند."))return;
    try {
      await secureApi(`/catalog/products/${selected.id}/restore-holoo`,{method:"POST"});
      await load();setSelected(null);setMessage("فیلدهای منبع به هلو بازگردانده شدند؛ ثبت مالی در هلو انجام نشد.");
    } catch(error){setMessage(error instanceof Error?error.message:"بازگشت منبع انجام نشد.");}
  };
  const addChannel = async () => { if (!selected || !externalId.trim()) return; try { await secureApi(`/catalog/products/${selected.id}/channels`, { method: "POST", body: JSON.stringify({ channel, external_id: externalId.trim() }) }); setExternalId(""); await select(selected); setMessage("اتصال کانال ذخیره شد."); } catch (e) { setMessage(e instanceof Error ? e.message : "ذخیره انجام نشد"); } };
  const isLow = (product: Product) => Boolean(product.is_active && product.stock != null && (product.min_stock ?? 0) > 0 && product.stock <= product.min_stock!);
  const low = items.filter(isLow);
  const visibleItems = items.filter(p => matchesSearch(query, p.name, p.code, p.category) &&
    (stockFilter === "all" || (stockFilter === "low" ? isLow(p) : Boolean(p.is_active && p.stock === 0))));
  return <PortalShell title="کالا و موجودی" eyebrow="جست‌وجو، قیمت و موجودی">
    {catalogManager && <div className="mb-4"><DataEntryLink entity="products"/></div>}
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <select aria-label="فیلتر موجودی" className={`${fieldClass} w-auto`} value={stockFilter} onChange={e => setStockFilter(e.target.value as typeof stockFilter)}>
        <option value="all">همهٔ کالاها</option>
        <option value="low">زیر حد سفارش</option>
        <option value="empty">ناموجود</option>
      </select>
      <button onClick={load} className={primaryButton}>به‌روزرسانی</button>
      <button onClick={() => setExtra(value => value === "files" ? null : "files")} aria-expanded={extra === "files"} className="px-3 py-2 text-sm text-violet-300">فایل‌های عمومی کاتالوگ</button>
      {catalogManager && <button onClick={() => setExtra(value => value === "intelligence" ? null : "intelligence")} aria-expanded={extra === "intelligence"} className="px-3 py-2 text-sm text-violet-300">تحلیل انبار</button>}
    </div>
    {extra === "files" && <div className="mb-4"><CatalogFiles /></div>}
    {extra === "intelligence" && catalogManager && <div className="mb-4"><InventoryIntelligence /></div>}
    {message && <div className="mb-4 rounded-xl border border-violet-400/20 bg-violet-500/10 p-3 text-xs text-violet-200">{message}</div>}
    {!catalogViewer && (<div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4"><Surface className="p-4"><div className="text-[10px] text-slate-500">کل کالاها</div><div className="mt-2 text-xl font-black text-white">{items.length}</div></Surface><Surface className="p-4"><div className="text-[10px] text-slate-500">فعال</div><div className="mt-2 text-xl font-black text-emerald-300">{items.filter(p=>p.is_active).length}</div></Surface><Surface className="p-4"><div className="text-[10px] text-slate-500">زیر حد سفارشِ ثبت‌شده</div><div className="mt-2 text-xl font-black text-amber-300">{low.length}</div></Surface><Surface className="p-4"><div className="text-[10px] text-slate-500">ارزش تقریبی</div><div className="mt-2 text-sm font-black text-cyan-300">{money(items.reduce((s,p)=>s+(p.price??0)*(p.stock??0),0))}</div></Surface></div>)}
    <label className="mb-4 block text-xs text-slate-400">جست‌وجو با بخشی از نام، کد یا دستهٔ کالا<input aria-label="جست‌وجوی کاتالوگ" value={query} onChange={e=>setQuery(e.target.value)} className={`${fieldClass} mt-2`} placeholder="مثلاً ضد آفتاب یا بخشی از کد"/></label>
    <div className="grid gap-4 xl:grid-cols-[1.4fr_.8fr]"><Surface className="overflow-hidden"><div className="border-b border-white/[0.06] p-4 text-sm font-bold text-white">فهرست کالاها · {visibleItems.length.toLocaleString("fa-IR")} نتیجه</div>{loading ? <div className="p-8 text-center text-xs text-slate-500">در حال دریافت…</div> : <div className="divide-y divide-white/[0.05]">{visibleItems.map(p => <button key={p.id} onClick={()=>select(p)} className={`grid w-full grid-cols-[1fr_90px_100px] items-center gap-3 px-4 py-4 text-right text-xs hover:bg-white/[0.04] ${selected?.id===p.id?"bg-violet-500/[0.08]":""}`}><div><div className="font-bold text-white">{p.name || "بدون نام"}</div><div className="mt-1 text-[10px] text-slate-600">{p.code} · {p.category || "بدون دسته"}</div></div><div><div className="text-[10px] text-slate-500">موجودی</div><div className={`mt-1 font-bold ${((p.stock??0)<=0 || ((p.min_stock??0)>0 && (p.stock??0)<=p.min_stock!))?"text-amber-300":"text-emerald-300"}`}>{new Intl.NumberFormat("fa-IR").format(p.stock??0)}</div></div><div className="text-left"><div className="font-bold text-slate-200">{money(p.price)}</div><span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[9px] ${p.is_active?"bg-emerald-500/10 text-emerald-300":"bg-slate-500/10 text-slate-400"}`}>{p.is_active?"فعال":"غیرفعال"}</span></div></button>)}{!visibleItems.length&&<div className="p-8 text-center text-xs text-slate-600">{items.length ? "کالایی مطابق جست‌وجو پیدا نشد." : "کالایی ثبت نشده است."}</div>}</div>}</Surface>
    <Surface className="p-5"><div className="text-[10px] text-violet-400">مدیریت کالا</div><h3 className="mt-1 text-sm font-bold text-white">{selected ? selected.name : "یک کالا انتخاب کنید"}</h3>{selected ? <><div className="mt-4 grid grid-cols-3 gap-2"><input value={edit.price} onChange={e=>setEdit({...edit,price:e.target.value})} className={fieldClass} placeholder="قیمت ۱ ـ ریال" aria-label="قیمت ۱ ـ ریال"/><input value={edit.price2} onChange={e=>setEdit({...edit,price2:e.target.value})} className={fieldClass} placeholder="قیمت ۲ ـ ریال" aria-label="قیمت ۲ ـ ریال"/><input value={edit.stock} onChange={e=>setEdit({...edit,stock:e.target.value})} className={fieldClass} placeholder="موجودی"/><input value={edit.min_stock} onChange={e=>setEdit({...edit,min_stock:e.target.value})} className={fieldClass} placeholder="حداقل موجودی"/></div><button onClick={saveProduct} className={`${primaryButton} mt-3 w-full`}>ذخیره قیمت و موجودی</button><p className="mt-3 text-[10px] leading-6 text-amber-200">ویرایش دستی: {selected.manual_fields?.length?selected.manual_fields.map(key=>({price:"قیمت ۱",price2:"قیمت ۲",stock:"موجودی",min_stock:"حد سفارش",name:"نام",category:"دسته",is_active:"فعال بودن"}[key]||key)).join("، "):"ندارد؛ دریافت هلو مبناست"}. این ویرایش‌ها فقط پنل را تغییر می‌دهند؛ تحلیل مالیِ منبع، نسخهٔ هلو را می‌خواند.</p>{!!selected.manual_fields?.some(key=>["price","price2","stock","name","is_active"].includes(key))&&<button onClick={restoreHoloo} className="mt-2 text-xs text-violet-300 underline">بازگشت نام، قیمت و موجودی به منبع هلو</button>}
      <div className="my-5 border-t border-white/[0.06] pt-4 text-[10px] text-violet-400">اتصال فروشگاه</div><p className="text-[10px] leading-5 text-slate-500">شناسه کالا در هر کانال را ثبت کنید تا همگام‌سازی قابل اجرا باشد.</p><div className="mt-3 space-y-3"><select value={channel} onChange={e=>setChannel(e.target.value)} className={fieldClass}><option value="digikala">دیجی‌کالا</option><option value="website">سایت</option><option value="holo">هلو</option></select><input value={externalId} onChange={e=>setExternalId(e.target.value)} placeholder="شناسه کالا در کانال" className={fieldClass}/><button onClick={addChannel} className={`${primaryButton} w-full`}>ذخیره اتصال</button></div><div className="mt-5 space-y-2">{channels.map(c=><div key={c.id ?? c.external_id} className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-black/15 p-3 text-[10px]"><span className="text-slate-300">{c.channel}</span><span className="text-violet-300">{c.external_id}</span></div>)}{!channels.length&&<div className="text-[10px] text-slate-600">هنوز کانالی متصل نیست.</div>}</div><div className="mt-5"><MediaUploader key={selected.id} productId={selected.id} productName={selected.name} /></div></> : <div className="mt-8 text-center text-xs text-slate-600">برای مشاهده و ویرایش، یک کالا را انتخاب کنید.</div>}</Surface></div>
  </PortalShell>;
}
