"use client";

import { useEffect, useRef, useState } from "react";
import { formatIranDateTime } from "../lib/iran-date";
import { secureApi } from "../lib/secure-api";
import { MAX_AUTOMATIC_ACCURACY_M } from "../lib/location-policy";
import { acquireBestPosition, LocationAcquisitionError } from "../lib/precise-location";

type PositionCheck = {
  ok: true;
  accuracy_m: number;
  observed_at: string;
  received_at: string;
};
type CheckResult = Pick<PositionCheck, "accuracy_m" | "observed_at" | "received_at">;
type Stage = "idle" | "position" | "server";

function locationErrorMessage(code: number): string {
  if (code === 1) {
    return "دسترسی موقعیت توسط مرورگر یا تنظیمات دستگاه رد شد. اجازهٔ موقعیت همین سایت و تنظیمات مکان دستگاه را بررسی کنید. اگر در مرورگر داخلی برنامه هستید، نشانی همین صفحه را در کروم یا اج باز کنید.";
  }
  if (code === 2) {
    return "دستگاه نتوانست موقعیت فعلی را پیدا کند؛ سرویس مکان دستگاه، اتصال اینترنت و دسترسی موقعیت مرورگر را بررسی کنید و دوباره در کروم یا اج تلاش کنید.";
  }
  if (code === 3) {
    return "دریافت موقعیت در ۲۵ ثانیه انجام نشد. سرویس مکان را روشن کنید، پاسخ پنجرهٔ اجازه را بررسی کنید و در کروم یا اج دوباره تلاش کنید.";
  }
  return "دریافت موقعیت ممکن نشد؛ سرویس مکان و دسترسی همین سایت را در کروم یا اج بررسی کنید.";
}

export default function LocationDiagnostic() {
  const [stage, setStage] = useState<Stage>("idle");
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState("");
  const mounted = useRef(false);
  const running = useRef(false);
  const attempt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controller = useRef<AbortController | null>(null);
  const positionAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      attempt.current += 1;
      if (timer.current) clearTimeout(timer.current);
      controller.current?.abort();
      positionAbort.current?.abort();
    };
  }, []);

  const checkPosition = () => {
    if (running.current) return;
    setError("");
    setResult(null);
    if (!window.isSecureContext) {
      setError("آزمون موقعیت به نشانی امن داشبورد نیاز دارد؛ نشانی امن همین صفحه را در کروم یا اج باز کنید.");
      return;
    }
    if (!navigator.geolocation) {
      setError("مرورگر فعلی امکان دریافت موقعیت را ندارد. نشانی همین صفحه را در کروم یا اج مستقل باز کنید؛ بعضی مرورگرهای داخلی این امکان را نمی‌دهند.");
      return;
    }

    running.current = true;
    setStage("position");
    const current = ++attempt.current;
    const active = () => mounted.current && current === attempt.current;
    const finish = () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      controller.current = null;
      running.current = false;
      attempt.current += 1;
      if (mounted.current) setStage("idle");
    };
    const failPosition = (code: number) => {
      if (!active()) return;
      setError(locationErrorMessage(code));
      finish();
    };
    timer.current = setTimeout(() => failPosition(3), 25000);

    try {
      positionAbort.current = new AbortController();
      void acquireBestPosition({ signal: positionAbort.current.signal, timeoutMs: 20_000 }).then(async position => {
      if (!active()) return;
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      const { latitude, longitude, accuracy } = position.coords;
      if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90
          || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
          || !Number.isFinite(accuracy) || accuracy < 0
          || !Number.isFinite(position.timestamp) || !Number.isFinite(new Date(position.timestamp).getTime())) {
        setError("موقعیت دریافت‌شده از دستگاه معتبر نبود؛ سرویس مکان را بررسی کنید و دوباره تلاش کنید.");
        finish();
        return;
      }

      setStage("server");
      const request = new AbortController();
      controller.current = request;
      timer.current = setTimeout(() => request.abort(), 15000);
      try {
        const response = await secureApi<PositionCheck>("/api/compensation/position-check", {
          method: "POST",
          signal: request.signal,
          body: JSON.stringify({
            lat: latitude,
            lng: longitude,
            accuracy_m: accuracy,
            observed_at: new Date(position.timestamp).toISOString(),
          }),
        });
        if (!active()) return;
        if (response.ok !== true || !Number.isFinite(response.accuracy_m) || response.accuracy_m < 0
            || !Number.isFinite(new Date(response.observed_at).getTime())
            || !Number.isFinite(new Date(response.received_at).getTime())) {
          setError("موقعیت دریافت شد، اما پاسخ آزمون سرور معتبر نبود؛ دوباره تلاش کنید.");
          return;
        }
        setResult({
          accuracy_m: response.accuracy_m,
          observed_at: response.observed_at,
          received_at: response.received_at,
        });
      } catch {
        if (!active()) return;
        setError(request.signal.aborted
          ? "موقعیت دستگاه دریافت شد، اما پاسخ سرور در زمان لازم نرسید؛ اتصال اینترنت و شبکهٔ خصوصی را بررسی کنید."
          : "موقعیت دستگاه دریافت شد، اما سرور آزمون را تأیید نکرد؛ اتصال شبکه و ورود حساب را بررسی کنید و دوباره تلاش کنید.");
      } finally {
        if (active()) finish();
      }
      }).catch(failure => failPosition(failure instanceof LocationAcquisitionError ? failure.code : 2));
    } catch (cause) {
      failPosition(cause instanceof DOMException && ["SecurityError", "NotAllowedError"].includes(cause.name) ? 1 : 2);
    }
  };

  return <section className="mb-4 rounded-2xl border border-white/10 bg-[#111015] p-4" aria-busy={stage !== "idle"}>
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 className="text-sm font-bold text-white">آزمون موقعیت همین دستگاه</h2>
        <p className="mt-2 max-w-2xl text-xs leading-6 text-slate-400">پس از زدن دکمه، موقعیت فعلی یک بار برای بررسی ارتباط به سرور فرستاده می‌شود؛ نتیجه فقط دقت و زمان را نشان می‌دهد. این آزمون شیفت یا ویزیت ثبت نمی‌کند.</p>
      </div>
      <button type="button" onClick={checkPosition} disabled={stage !== "idle"} className="rounded-xl bg-violet-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">
        {stage === "position" ? "در حال دریافت موقعیت…" : stage === "server" ? "در حال تأیید ارتباط سرور…" : "آزمون موقعیت این دستگاه"}
      </button>
    </div>
    {error && <p role="alert" className="mt-3 rounded-xl bg-rose-500/10 p-3 text-xs leading-6 text-rose-200">{error}</p>}
    {result && <div role="status" className="mt-3 rounded-xl bg-emerald-500/10 p-3 text-xs leading-7 text-emerald-200">
      <p>دریافت موقعیت و ارتباط با سرور موفق بود.</p>
      <p>دقت اعلام‌شدهٔ دستگاه: حدود {result.accuracy_m.toLocaleString("fa-IR", { maximumSignificantDigits: 21 })} متر</p>
      <p>زمان دریافت موقعیت: {formatIranDateTime(result.observed_at)}</p>
      <p>زمان تأیید سرور: {formatIranDateTime(result.received_at)}</p>
      {result.accuracy_m > MAX_AUTOMATIC_ACCURACY_M && <p className="text-amber-200">تأیید خودکار حضور به دقت حداکثر {MAX_AUTOMATIC_ACCURACY_M.toLocaleString("fa-IR")} متر نیاز دارد؛ دقت واقعی دستگاه همان مقدار بالا است.</p>}
    </div>}
  </section>;
}
