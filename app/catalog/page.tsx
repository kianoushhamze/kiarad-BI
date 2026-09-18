"use client";

import { useCallback, useEffect, useState } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";

type Product = { id: number; code?: string; name?: string; category?: string; price?: number; stock?: number; min_stock?: number; is_active?: number; updated_at?: string };
type Channel = { id?: number; channel?: string; external_id?: string; is_active?: number };
const money = (n?: number) => new Intl.NumberFormat("fa-IR").format(n ?? 0) + " ریال";

export default function CatalogPage() {
  const [items, setItems] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [channel, setChannel] = useState("digikala");
  const [externalId, setExternalId] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => { setLoading(true); try { const r = await secureApi<{items: Product[]}>("/catalog/products"); setItems(r.items ?? []); } catch (e) { setMessage(e instanceof Error ? e.message : "خطا در دریافت کالاها"); } finally { setLoading(false); } }, []);
  useEffect(() => { load(); }, [load]);
  const select = async (p: Product) => { setSelected(p); setMessage(""); try { const r = await secureApi<{items: Channel[]}>(`/catalog/products/${p.id}/channels`); setChannels(r.items ?? []); } catch (e) { setMessage(e instanceof Error ? e.message : "خطا در دریافت کانال‌ها"); } };
  const addChannel = async () => { if (!selected || !externalId.trim()) return; try { await secureApi(`/catalog/products/${selected.id}/channels`, { method: "POST", body: JSON.stringify({ channel, external_id: externalId.trim() }) }); setExternalId(""); await select(selected); setMessage("اتصال کانال ذخیره شد."); } catch (e) { setMessage(e instanceof Error ? e.message : "ذخیره انجام نشد"); } };
  const low = items.filter(p => (p.stock ?? 0) <= (p.min_stock ?? 0));
  return <PortalShell title="مدیریت کالا و کانال‌ها" eyebrow="کاتالوگ و همگام‌سازی">
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs text-slate-500">مرکز کنترل کالا، قیمت، موجودی و اتصال به فروشگاه‌ها</p><h2 className="mt-1 text-xl font-black text-white">کاتالوگ محصولات</h2></div><button onClick={load} className={primaryButton}>به‌روزرسانی</button></div>
    {message && <div className="mb-4 rounded-xl border border-violet-400/20 bg-violet-500/10 p-3 text-xs text-violet-200">{message}</div>}
    <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4"><Surface className="p-4"><div className="text-[10px] text-slate-500">کل کالاها</div><div className="mt-2 text-xl font-black text-white">{items.length}</div></Surface><Surface className="p-4"><div className="text-[10px] text-slate-500">فعال</div><div className="mt-2 text-xl font-black text-emerald-300">{items.filter(p=>p.is_active).length}</div></Surface><Surface className="p-4"><div className="text-[10px] text-slate-500">کم‌موجود</div><div className="mt-2 text-xl font-black text-amber-300">{low.length}</div></Surface><Surface className="p-4"><div className="text-[10px] text-slate-500">ارزش تقریبی</div><div className="mt-2 text-sm font-black text-cyan-300">{money(items.reduce((s,p)=>s+(p.price??0)*(p.stock??0),0))}</div></Surface></div>
    <div className="grid gap-4 xl:grid-cols-[1.4fr_.8fr]"><Surface className="overflow-hidden"><div className="border-b border-white/[0.06] p-4 text-sm font-bold text-white">فهرست کالاها</div>{loading ? <div className="p-8 text-center text-xs text-slate-500">در حال دریافت…</div> : <div className="divide-y divide-white/[0.05]">{items.map(p => <button key={p.id} onClick={()=>select(p)} className={`grid w-full grid-cols-[1fr_90px_100px] items-center gap-3 px-4 py-4 text-right text-xs hover:bg-white/[0.04] ${selected?.id===p.id?"bg-violet-500/[0.08]":""}`}><div><div className="font-bold text-white">{p.name || "بدون نام"}</div><div className="mt-1 text-[10px] text-slate-600">{p.code} · {p.category || "بدون دسته"}</div></div><div><div className="text-[10px] text-slate-500">موجودی</div><div className={`mt-1 font-bold ${(p.stock??0)<=(p.min_stock??0)?"text-amber-300":"text-emerald-300"}`}>{new Intl.NumberFormat("fa-IR").format(p.stock??0)}</div></div><div className="text-left"><div className="font-bold text-slate-200">{money(p.price)}</div><span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[9px] ${p.is_active?"bg-emerald-500/10 text-emerald-300":"bg-slate-500/10 text-slate-400"}`}>{p.is_active?"فعال":"غیرفعال"}</span></div></button>)}{!items.length&&<div className="p-8 text-center text-xs text-slate-600">کالایی ثبت نشده است.</div>}</div>}</Surface>
    <Surface className="p-5"><div className="text-[10px] text-violet-400">اتصال فروشگاه</div><h3 className="mt-1 text-sm font-bold text-white">{selected ? selected.name : "یک کالا انتخاب کنید"}</h3>{selected ? <><p className="mt-2 text-[10px] leading-5 text-slate-500">شناسه کالا در هر کانال را ثبت کنید تا در فاز اتصال، همگام‌سازی قیمت و موجودی قابل اجرا باشد.</p><div className="mt-5 space-y-3"><select value={channel} onChange={e=>setChannel(e.target.value)} className={fieldClass}><option value="digikala">دیجی‌کالا</option><option value="website">سایت</option><option value="holo">هلو</option></select><input value={externalId} onChange={e=>setExternalId(e.target.value)} placeholder="شناسه کالا در کانال" className={fieldClass}/><button onClick={addChannel} className={`${primaryButton} w-full`}>ذخیره اتصال</button></div><div className="mt-5 space-y-2">{channels.map(c=><div key={c.id ?? c.external_id} className="flex items-center justify-between rounded-xl border border-white/[0.06] bg-black/15 p-3 text-[10px]"><span className="text-slate-300">{c.channel}</span><span className="text-violet-300">{c.external_id}</span></div>)}{!channels.length&&<div className="text-[10px] text-slate-600">هنوز کانالی متصل نیست.</div>}</div></> : <div className="mt-8 text-center text-xs text-slate-600">برای مشاهده و افزودن اتصال، یک کالا را انتخاب کنید.</div>}</Surface></div>
  </PortalShell>;
}
