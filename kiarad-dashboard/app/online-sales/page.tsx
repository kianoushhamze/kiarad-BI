"use client";
import { useCallback, useEffect, useState } from "react";
import { PortalShell, Surface } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
import { formatIranDateTime } from "../../lib/iran-date";
import { MARKETPLACES, modelLabel, statusLabel } from "../../lib/marketplaces";

type Channel = { id: string; label: string; kind: string; account_label: string; notes: string; last_sync_at: string | null; last_attempt_at: string | null; last_attempt_status: string | null; mapped_products: number; connected: boolean; sync_enabled: boolean; stock_push_enabled: boolean; price_push_enabled: boolean; connection_check_status?:string;connection_checked_at?:string|null;connection_check_fresh?:boolean;connection_http_status?:number|null };
const connectionText:Record<string,string>={not_checked:"هنوز بررسی نشده",verified:"خواندن حساب فروشنده تأیید شد",credentials_missing:"اطلاعات ورود سرویس روی میزبان موجود نیست",authentication_failed:"اجازهٔ حساب فروشنده تأیید نشد؛ ورود سرویس باید تازه شود",endpoint_error:"مسیر سرویس پاسخ موفق نداد",unverified_response:"پاسخ سرویس برای تأیید حساب کافی نیست",network_error:"ارتباط شبکه با دیجی‌کالا برقرار نشد",credentials_or_response_invalid:"اطلاعات ورود یا پاسخ سرویس معتبر نیست"};
const steps: Record<string, string> = {
  digikala: "دسترسی رسمی فروشنده، نگاشت شناسهٔ کالا و آزمون سفارش، قیمت و موجودی",
  basalam: "مجوز فروشگاه و رابط رسمی، نگاشت کالا و آزمون سفارش و موجودی",
  divar: "دسترسی تجاری و مجوز مسیر رسمی آگهی و پیام",
  emalls: "تأیید فروشگاه و روش رسمی دریافت فهرست کالا و قیمت",
  torob: "تأیید فروشگاه و روش رسمی دریافت فهرست کالا و قیمت",
  instagram: "حساب حرفه‌ای و مجوزهای رسمی متا برای صفحهٔ مرتبط",
  youtube: "مالکیت کانال، پروژهٔ گوگل و اجازهٔ دسترسی به آمار",
  tiktok: "حساب مجاز و تأیید روش رسمی انتشار و دریافت آمار",
  linkedin: "مدیریت صفحهٔ سازمانی و مجوز رسمی انتشار و آمار",
  telegram: "بات یا کانال تحت مدیریت و مجوز دسترسی مشخص",
  bale: "بات یا کانال تحت مدیریت و تأیید روش رسمی اتصال",
  rubika: "کانال یا حساب تجاری و تأیید روش رسمی اتصال",
  whatsapp: "حساب تجاری و مجوز رسمی پیام‌رسانی و الگوی پیام",
};
const shown = (v: string | null) => v ? formatIranDateTime(v) : "ثبت نشده";

export default function OnlineSalesPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selected, setSelected] = useState("digikala");
  const [account, setAccount] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => {
    try { setChannels(await secureApi<Channel[]>("/integrations")); setMessage(""); }
    catch (e) { setMessage(e instanceof Error ? e.message : "وضعیت اتصال دریافت نشد"); }
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    const timer=window.setInterval(()=>{void load();},60_000);
    return () => { active = false;window.clearInterval(timer); };
  }, [load]);
  const active = channels.find(c => c.id === selected);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setAccount(active?.account_label ?? "");
      setNotes(active?.notes ?? "");
    });
    return () => { cancelled = true; };
  }, [active?.id, active?.account_label, active?.notes]);
  async function save() {
    if (!active) return;
    setBusy(true);
    try {
      await secureApi(`/integrations/${active.id}/draft`, { method: "PUT", body: JSON.stringify({ account_label: account, notes }) });
      await load(); setMessage("مشخصات اولیه ذخیره شد؛ ذخیرهٔ این فرم به‌تنهایی اتصال یا همگام‌سازی را فعال نمی‌کند.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "ذخیره انجام نشد"); }
    finally { setBusy(false); }
  }
  async function checkConnection(){
    setBusy(true);setMessage("");
    try{const result=await secureApi<{status:string;http_status:number|null}>("/integrations/digikala/check",{method:"POST"});await load();setMessage((connectionText[result.status]||"بررسی انجام شد")+(result.http_status?` ـ پاسخ ${result.http_status}`:"")+". قیمت، موجودی و سفارش تغییر نکردند.");}
    catch(error){setMessage(error instanceof Error?error.message:"بررسی اتصال انجام نشد.");}finally{setBusy(false);}
  }
  return <PortalShell title="مرکز اتصال کانال‌ها" eyebrow="فروش آنلاین و شبکه‌های اجتماعی">
    <div className="kskin space-y-5" dir="rtl">
      <Surface className="p-5 text-sm leading-8 text-slate-300">این بخش برای آماده‌سازی اتصال است. تا مجوز پلتفرم، نگاشت کالا و آزمون موفق ثبت نشود، قیمت و موجودی به هیچ کانالی ارسال نمی‌شود.</Surface>
      {message && <p role="status" className="rounded-xl border border-violet-400/30 bg-violet-500/10 p-3 text-sm text-violet-200">{message}</p>}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="کانال‌ها">{channels.map(c => <button key={c.id} type="button" role="tab" aria-selected={selected === c.id} onClick={() => setSelected(c.id)} className={`rounded-xl border px-4 py-2 text-sm ${selected === c.id ? "border-violet-400 bg-violet-500/20 text-white" : "border-white/10 bg-white/[0.04] text-slate-300"}`}>{c.label}</button>)}</div>
      {active && <Surface className="space-y-5 p-6">
        <div><h2 className="text-xl font-bold text-white">{active.label}</h2><p className="mt-2 text-sm text-slate-400">{active.kind} · {steps[active.id]}</p></div>
        <div className="grid gap-3 text-sm md:grid-cols-2">
          <p>وضعیت اتصال: <strong className="text-amber-300">{active.connected ? "تأییدشده" : "تأیید نشده"}</strong></p>
          <p>همگام‌سازی خودکار: <strong className="text-amber-300">{active.sync_enabled ? "فعال" : "غیرفعال"}</strong></p>
          <p>آخرین همگام‌سازی موفق: {shown(active.last_sync_at)}</p>
          <p>آخرین تلاش: {shown(active.last_attempt_at)}{active.last_attempt_status ? ` (${active.last_attempt_status})` : ""}</p>
          <p>کالای نگاشت‌شده: {active.mapped_products.toLocaleString("fa-IR")}</p>
          <p>ارسال قیمت و موجودی: {active.price_push_enabled || active.stock_push_enabled ? "فعال" : "غیرفعال"}</p>
        </div>
        {active.id==="digikala"&&<div className="rounded-xl border border-white/10 p-4 text-xs leading-7 text-slate-300"><p>آخرین بررسی خواندنی: {active.connection_checked_at?formatIranDateTime(active.connection_checked_at):"ثبت نشده"}</p><p>{connectionText[active.connection_check_status||"not_checked"]||"وضعیت نامشخص"}{active.connection_checked_at&&!active.connection_check_fresh?"؛ نتیجهٔ بررسی قدیمی است، دوباره بررسی کنید.":""}</p><button type="button" disabled={busy} onClick={()=>void checkConnection()} className="mt-3 rounded-lg bg-violet-600 px-4 py-2 text-white disabled:opacity-50">{busy?"در حال بررسی…":"بررسی خواندنی حساب دیجی‌کالا"}</button></div>}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-300">شناسه یا نام حساب فروشنده<input value={account} onChange={e => setAccount(e.target.value)} maxLength={160} placeholder="مثلاً نام فروشگاه یا کانال" className="mt-2 w-full rounded-xl border border-white/15 bg-white/[0.05] p-3 text-white" /></label>
          <label className="text-sm text-slate-300">یادداشت اتصال<textarea value={notes} onChange={e => setNotes(e.target.value)} maxLength={1000} rows={2} placeholder="مالک حساب، وضعیت مجوز و نیازهای اتصال" className="mt-2 w-full rounded-xl border border-white/15 bg-white/[0.05] p-3 text-white" /></label>
        </div>
        <div className="flex flex-wrap items-center gap-3"><button type="button" disabled={busy} onClick={save} className="rounded-xl bg-violet-600 px-5 py-2 text-sm text-white disabled:opacity-50">ذخیرهٔ آماده‌سازی</button><button type="button" onClick={() => void load()} className="rounded-xl border border-white/15 px-5 py-2 text-sm text-slate-200">بازخوانی وضعیت</button><span className="text-xs text-amber-300">رمز یا کلید دسترسی را در این فرم وارد نکنید.</span></div>
      </Surface>}
      <Surface className="space-y-4 p-6">
        <div>
          <h2 className="text-lg font-bold text-white">نقشهٔ بازارگاه‌ها و مقایسه‌گرهای ایران</h2>
          <p className="mt-2 text-xs leading-7 text-slate-400">دو دستهٔ اصلی با هم فرق دارند: در بازارگاه سفارش داخل خود پلتفرم ثبت می‌شود و پنل فروشنده می‌خواهد؛ در ترب و ایمالز فقط قیمت نمایش داده می‌شود و خریدار به سایت ما می‌آید. فهرست بر پایهٔ منابع عمومی است و پذیرش نهایی هر مورد با خود سرویس است.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-right text-xs">
            <thead><tr className="text-slate-400"><th className="pb-2">سرویس</th><th className="pb-2">نوع</th><th className="pb-2">سفارش کجا ثبت می‌شود</th><th className="pb-2">پیش‌نیاز</th><th className="pb-2">سمت ما</th><th className="pb-2">وضعیت</th></tr></thead>
            <tbody>{MARKETPLACES.slice().sort((a, b) => a.priority - b.priority).map(m => <tr key={m.id} className="border-t border-white/[0.06] align-top">
              <td className="py-3 font-bold text-white">{m.name}</td>
              <td className="py-3 text-slate-300">{modelLabel[m.model]}</td>
              <td className="py-3 text-slate-300">{m.orderPlace}</td>
              <td className="py-3 text-slate-400">{m.need}</td>
              <td className="py-3 text-slate-400">{m.ourSide}</td>
              <td className="py-3"><span className={`rounded-full px-2 py-1 text-[10px] ${m.status === "connected" ? "bg-emerald-500/15 text-emerald-300" : m.status === "feed_ready" ? "bg-violet-500/15 text-violet-200" : "bg-amber-500/15 text-amber-200"}`}>{statusLabel[m.status]}</span></td>
            </tr>)}</tbody>
          </table>
        </div>
      </Surface>
    </div>
  </PortalShell>;
}
