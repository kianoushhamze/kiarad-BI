"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { secureApi, type SessionUser } from "../lib/secure-api";
import { Surface, fieldClass, primaryButton } from "./portal-shell";
import { VisitCheckinHistory } from "./visit-checkin-history";
import { MAX_AUTOMATIC_ACCURACY_M } from "../lib/location-policy";
import { matchesSearch } from "../lib/text-search";
import { acquireBestPosition, LocationAcquisitionError } from "../lib/precise-location";
import { PendingSubmission } from "../lib/pending-submission";

type BaseRow = {
  source: string; id: number; name: string; city?: string; address?: string;
  latitude?: number | null; longitude?: number | null; visit_radius_m?: number;
  location_configured?: boolean;
};

type CheckinResult = { status: string; base_name?: string; distance_m?: number };
type CheckinPayload={source:string;base_id:number;lat:number;lng:number;accuracy_m:number;note:string};

const managerRoles = new Set(["ceo", "sales_manager", "cfo", "finance", "accountant", "hr"]);

export function BaseCheckIn() {
  const [items, setItems] = useState<BaseRow[]>([]);
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [user,setUser] = useState<SessionUser | null>(null);
  const [note,setNote] = useState("");
  const [reloadKey,setReloadKey] = useState(0);
  const locationController=useRef<AbortController|null>(null);
  const pendingCheckin=useRef(new PendingSubmission<CheckinPayload>());
  const postingCheckin=useRef(false);
  const isManager = managerRoles.has(String(user?.role || ""));

  const load = async () => {
    try {
      const data = await secureApi<{ items?: BaseRow[] }>("/api/compensation/bases");
      setItems(data.items || []);
      setMessage(previous => previous.startsWith("دریافت پایگاه‌ها ناموفق بود") ? "" : previous);
    } catch (err: unknown) { setMessage("دریافت پایگاه‌ها ناموفق بود: " + (err instanceof Error ? err.message : "خطا")); }
  };

  useEffect(() => {
    let active=true;
    void Promise.resolve().then(()=>{
      if(!active)return;
      void load();
      secureApi<SessionUser>("/auth/me").then(value=>{if(active)setUser(value);}).catch(()=>{if(active)setMessage("اطلاعات حساب دریافت نشد؛ دوباره وارد شوید.");});
      const params=new URLSearchParams(window.location.search);
      if(params.get("base_source") && params.get("base_id")) setSelected(`${params.get("base_source")}:${params.get("base_id")}`);
    });
    return ()=>{active=false;locationController.current?.abort();};
  }, []);
  const filtered = useMemo(() => {
    return items.filter(item => matchesSearch(query,item.name,item.city,item.address));
  }, [items, query]);
  const base = items.find(x => `${x.source}:${x.id}` === selected);
  const visibleBases=filtered.slice(0,500);
  if(base && !visibleBases.some(item=>item.source===base.source && item.id===base.id)) visibleBases.unshift(base);

  const locate = async (callback: (lat: number, lng: number, accuracy: number) => Promise<void>) => {
    if (busy || locationController.current || postingCheckin.current) return;
    if (!window.isSecureContext) { setMessage("ثبت موقعیت روی گوشی به نشانی امن با گواهی معتبر نیاز دارد. نشانی معمولی شبکهٔ داخلی این قابلیت را فعال نمی‌کند."); return; }
    if (!navigator.geolocation) { setMessage("مرورگر به موقعیت مکانی دسترسی ندارد."); return; }
    setBusy(true); setMessage("در حال دریافت بهترین موقعیت تازه؛ تا ۳۰ ثانیه در فضای باز منتظر بمانید…");
    const controller=new AbortController();locationController.current=controller;
    try {const pos=await acquireBestPosition({signal:controller.signal,targetAccuracyM:MAX_AUTOMATIC_ACCURACY_M});await callback(pos.coords.latitude,pos.coords.longitude,pos.coords.accuracy);}
    catch(reason){if(reason instanceof DOMException&&reason.name==="AbortError")return;setMessage(reason instanceof LocationAcquisitionError?reason.message:"موقعیت دستگاه قابل دریافت نیست؛ موقعیت‌یاب گوشی را بررسی کنید.");}
    finally{if(locationController.current===controller)locationController.current=null;setBusy(false);}
  };

  const checkIn = () => {
    if(busy||postingCheckin.current||locationController.current)return;
    if (!base) { setMessage("ابتدا پایگاه را انتخاب کنید."); return; }
    if (!note.trim()) { setMessage("نتیجهٔ بازدید یا علت مراجعه را بنویسید."); return; }
    const signature=JSON.stringify([base.source,base.id,note.trim()]);
    const submit=async(request:ReturnType<PendingSubmission<CheckinPayload>["prepare"]>)=>{
      postingCheckin.current=true;setBusy(true);
      try {
        const result = await secureApi<CheckinResult>("/api/compensation/base-checkins", {
          method: "POST", body: JSON.stringify({...request.payload,submission_key:request.key})
        });
        setMessage(result.status === "verified"
          ? `✓ حضور در «${result.base_name}» تأیید شد؛ فاصله ${result.distance_m} متر.`
          : result.status === "outside_radius"
            ? `موقعیت ثبت شد اما خارج از شعاع مجاز است؛ فاصله ${result.distance_m} متر.`
            : request.payload.accuracy_m > MAX_AUTOMATIC_ACCURACY_M
              ? `موقعیت و گزارش ثبت شد؛ دقت اعلام‌شدهٔ دستگاه ${request.payload.accuracy_m.toLocaleString("fa-IR", { maximumSignificantDigits: 21 })} متر است. تأیید خودکار به دقت حداکثر ${MAX_AUTOMATIC_ACCURACY_M.toLocaleString("fa-IR")} متر نیاز دارد؛ حضور باید توسط مدیر بررسی شود.`
              : "موقعیت و گزارش ثبت شد؛ مختصات مرجع یا دقت موقعیت نیازمند بررسی مدیر است.");
        pendingCheckin.current.clear(request.key);setNote(""); setReloadKey(value=>value+1);
      } catch (err: unknown) { setMessage("پاسخ ثبت حضور دریافت نشد یا سرویس آن را نپذیرفت: " + (err instanceof Error ? err.message : "خطا")+". اگر پاسخ شبکه قطع شده، با همین پایگاه و گزارش دوباره بزنید تا همان درخواست بررسی شود؛ پیش از تازه‌کردن صفحه، سابقه را کنترل کنید."); }
      finally{postingCheckin.current=false;setBusy(false);}
    };
    const previous=pendingCheckin.current.get(signature);
    if(previous){void submit(previous);return;}
    locate(async (lat,lng,accuracy)=>{
      await submit(pendingCheckin.current.prepare(signature,{source:base.source,base_id:base.id,lat,lng,accuracy_m:accuracy,note:note.trim()}));
    });
  };

  const saveBaseLocation = () => {
    if (!base) { setMessage("ابتدا پایگاه را انتخاب کنید."); return; }
    locate(async (lat, lng, accuracy) => {
      if(accuracy>100){setMessage("دقت موقعیت برای ثبت مرجع کافی نیست؛ در فضای باز دوباره تلاش کنید.");return;}
      try {
        await secureApi(`/api/compensation/bases/${base.source}/${base.id}/location`, {
          method: "PUT", body: JSON.stringify({ lat, lng, accuracy_m: accuracy, visit_radius_m: base.visit_radius_m || 150 })
        });
        setMessage("✓ موقعیت مرجع پایگاه با شعاع فعلی ذخیره شد.");
        await load();
      } catch (err: unknown) { setMessage("ثبت مختصات پایگاه ناموفق بود: " + (err instanceof Error ? err.message : "خطا")); }
    });
  };

  return <><Surface className="mb-5 p-5">
    <div className="text-[10px] text-violet-400">حضور میدانی ویزیتور</div>
    <h2 className="mt-1 text-base font-bold text-white">تیک حضور در پایگاه</h2>
    <p className="mt-2 text-xs leading-6 text-slate-400">نتیجهٔ بازدید را بنویسید و موقعیت فعلی را ثبت کنید. تأیید خودکار به دقت حداکثر {MAX_AUTOMATIC_ACCURACY_M.toLocaleString("fa-IR")} متر و قرارداشتن در شعاع مجاز پایگاه نیاز دارد. حضور با فاصله یا دقت نامطمئن برای بررسی مدیر نگهداری می‌شود؛ حضور تأییدشده در محاسبهٔ کارکرد داخلی لحاظ می‌شود.</p>
    <div className="mt-4 grid gap-3 md:grid-cols-[1fr_2fr]">
      <input aria-label="جست‌وجوی پایگاه بازدید" value={query} onChange={e => setQuery(e.target.value)} placeholder="جست‌وجوی بخشی از نام، شهر یا آدرس" className={fieldClass} />
      <select aria-label="پایگاه بازدید" disabled={busy} value={selected} onChange={e => setSelected(e.target.value)} className={fieldClass}>
        <option value="">— انتخاب پایگاه —</option>
        {visibleBases.map(item => <option key={`${item.source}:${item.id}`} value={`${item.source}:${item.id}`}>{item.location_configured ? "●" : "○"} {item.name} — {item.city || "بدون شهر"}</option>)}
      </select>
    </div>
    <p role="status" className="mt-2 text-xs text-slate-400">{filtered.length.toLocaleString("fa-IR")} نتیجه؛ شهر، نوع یا مختصات نامشخص به معنی تأییدشده‌بودن پایگاه نیست.</p>
    {base ? <div className="mt-3 rounded-xl border border-white/[0.06] bg-black/15 p-3 text-[11px] text-slate-300"><b className="text-white">{base.name}</b><div className="mt-1">{base.address || "آدرس ثبت نشده"}</div><div className="mt-1 text-slate-500">مختصات مرجع: {base.location_configured ? `ثبت شده · شعاع ${base.visit_radius_m || 150} متر` : "هنوز ثبت نشده"}</div></div> : null}
    <label className="mt-4 block text-sm text-slate-300">گزارش بازدید<textarea disabled={busy} maxLength={2000} rows={3} value={note} onChange={e=>setNote(e.target.value)} className={`${fieldClass} mt-2`} placeholder="نتیجهٔ ملاقات، نیاز مشتری یا علت انجام‌نشدن بازدید"/></label>
    {user && !user.salesperson_id && <p className="mt-3 text-xs text-amber-200">برای ثبت حضور، حساب باید به پروفایل پرسنل متصل باشد؛ ابزار تعیین مختصات مرجع برای مدیر در دسترس است.</p>}
    <div className="mt-4 flex flex-wrap gap-2">
      <button type="button" onClick={checkIn} disabled={busy || !base || !user?.salesperson_id} className={primaryButton}>{busy ? "در حال ثبت موقعیت..." : "✓ ثبت حضور و گزارش بازدید"}</button>
      {isManager ? <button type="button" onClick={saveBaseLocation} disabled={busy || !base} className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-2.5 text-xs font-bold text-amber-200 disabled:opacity-50">ثبت موقعیت فعلی به‌عنوان مرجع پایگاه</button> : null}
    </div>
    {message ? <div role="status" className="mt-3 rounded-xl border border-white/[0.06] bg-black/20 p-3 text-xs text-slate-200">{message}</div> : null}
  </Surface>{user && <VisitCheckinHistory manager={["ceo","sales_manager"].includes(user.role)} salespersonId={user.salesperson_id} reloadKey={reloadKey}/>}</>;
}
