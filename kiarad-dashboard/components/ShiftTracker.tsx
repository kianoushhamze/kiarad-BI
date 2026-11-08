"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { secureApi } from "../lib/secure-api";
import { formatIranDateTime } from "../lib/iran-date";
import { acquireBestPosition, LocationAcquisitionError } from "../lib/precise-location";

type ShiftStatus = { is_active: boolean; session_id?: number | null; started_at?: string | null; status: string; duration_hours?: number };

export default function ShiftTracker({ salespersonId }: { salespersonId: number }) {
  const [shift, setShift] = useState<ShiftStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const mounted = useRef(false);
  const submitting = useRef(false);
  const positionAbort = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    try {
      const status = await secureApi<ShiftStatus>(`/api/compensation/attendance/status?salesperson_id=${salespersonId}`);
      if (mounted.current) setShift(status);
      return true;
    } catch (cause: unknown) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "وضعیت شیفت دریافت نشد.");
      return false;
    }
  }, [salespersonId]);

  useEffect(() => {
    mounted.current = true;
    void Promise.resolve().then(() => { if (mounted.current) void refresh(); });
    const onFocus = () => { if (!submitting.current) void refresh(); };
    window.addEventListener("focus", onFocus);
    return () => { mounted.current = false; positionAbort.current?.abort(); window.removeEventListener("focus", onFocus); };
  }, [refresh]);

  const toggleShift = () => {
    if (!shift || submitting.current) return;
    setError(""); setMessage("");
    if (!window.isSecureContext || !navigator.geolocation) {
      setError("برای ثبت شیفت، پنل را با نشانی امن باز کنید و دسترسی موقعیت این سایت را فعال کنید.");
      return;
    }
    submitting.current = true; setLoading(true);
    const stop = shift.is_active;
    positionAbort.current = new AbortController();
    void acquireBestPosition({signal:positionAbort.current.signal}).then(async position => {
      if (!mounted.current) { submitting.current = false; return; }
      try {
        const result = await secureApi<ShiftStatus>(`/api/compensation/attendance/${stop ? "stop" : "start"}`, {
          method: "POST",
          body: JSON.stringify({ salesperson_id: salespersonId, lat: position.coords.latitude, lng: position.coords.longitude, accuracy_m: position.coords.accuracy }),
        });
        if (!mounted.current) return;
        setShift(result);
        setMessage(result.status === "already_active" ? "شیفت شما از قبل باز بوده است؛ همان شیفت نمایش داده شد."
          : result.is_active ? "شروع شیفت و موقعیت فعلی ثبت شد."
          : `شیفت پایان یافت؛ ${Number(result.duration_hours || 0).toLocaleString("fa-IR", { maximumFractionDigits: 2 })} ساعت کارکرد ثبت شد.`);
      } catch (cause: unknown) {
        if (mounted.current) setError(cause instanceof Error ? cause.message : "ثبت شیفت انجام نشد؛ وضعیت را تازه کنید.");
        await refresh();
      } finally {
        submitting.current = false;
        if (mounted.current) setLoading(false);
      }
    }).catch((failure: unknown) => {
      submitting.current = false;
      if (!mounted.current) return;
      setLoading(false);
      const code = failure instanceof LocationAcquisitionError ? failure.code : 2;
      setError(code === 1 ? "اجازهٔ موقعیت داده نشد؛ دسترسی همین سایت را در مرورگر فعال کنید."
        : code === 3 ? "دریافت موقعیت طول کشید؛ موقعیت‌یاب گوشی را روشن کنید و دوباره تلاش کنید."
        : "موقعیت دستگاه دریافت نشد؛ موقعیت‌یاب گوشی و دسترسی مرورگر را بررسی کنید.");
    });
  };

  return <section className="mb-4 rounded-2xl border border-violet-400/20 bg-[#111015] p-4" aria-busy={loading}>
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h2 className="text-sm font-bold text-white">شیفت کاری من</h2>
        <p className="mt-2 text-xs text-slate-400">{shift ? shift.is_active ? "شیفت فعال است" : "شیفت باز ندارید" : "در حال دریافت وضعیت شیفت…"}{shift?.is_active && shift.started_at ? ` · شروع: ${formatIranDateTime(shift.started_at)}` : ""}</p>
        <p className="mt-2 text-[11px] leading-6 text-slate-500">موقعیت هنگام شروع، پایان شیفت و ثبت بازدید ارسال می‌شود. این صفحه ردیابی پیوسته در پس‌زمینه انجام نمی‌دهد.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={loading} onClick={() => { setError(""); void refresh(); }} className="rounded-xl border border-white/10 px-3 py-2.5 text-xs text-slate-300 disabled:opacity-50">تازه‌سازی وضعیت</button>
        <button type="button" onClick={toggleShift} disabled={loading || !shift} className={`rounded-xl px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50 ${shift?.is_active ? "bg-rose-600" : "bg-emerald-600"}`}>{loading ? "در حال دریافت و ثبت موقعیت…" : shift?.is_active ? "پایان شیفت کاری" : "ثبت موقعیت و شروع شیفت"}</button>
      </div>
    </div>
    {error && <p role="alert" className="mt-3 rounded-xl bg-rose-500/10 p-3 text-xs leading-6 text-rose-200">{error}</p>}
    {message && <p role="status" className="mt-3 rounded-xl bg-emerald-500/10 p-3 text-xs leading-6 text-emerald-200">{message}</p>}
  </section>;
}
