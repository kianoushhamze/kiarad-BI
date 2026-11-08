"use client";
import { useRef, useState } from "react";

export type CheckScannerPick = { sayad: string; serial: string };

declare global {
  interface Window { jsQR?: (data: Uint8ClampedArray, w: number, h: number, opts?: { inversionAttempts?: string }) => { data: string } | null }
}

type FoundNumber = { value: string; label: string };

export function extractNumbers(text: string): FoundNumber[] {
  const runs = Array.from(new Set(text.match(/\d{6,}/g) || []));
  return runs.map(value => {
    let label = "عدد یافت‌شده";
    if (/sayad|صیاد/i.test(text)) label = "عدد در QR صیاد";
    if (value.length >= 12) label = "احتمالاً شماره صیاد/شناسه";
    else if (value.length >= 6) label = "احتمالاً سریال/شماره چک";
    return { value, label };
  });
}

/** خواننده QR چک صیادی؛ قابل استفاده در /check-scan و فرم ثبت چک خزانه.
 *  اگر onNumbers داده شود، پس از اسکن موفق بهترین حدس‌ها به‌صورت خودکار برگردانده می‌شود. */
export function CheckScanner({ onNumbers, autoPick = true, showSummary = true }: {
  onNumbers?: (pick: CheckScannerPick) => void;
  autoPick?: boolean;
  showSummary?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [decoded, setDecoded] = useState("");
  const [rawImageName, setImageName] = useState("");
  const [status, setStatus] = useState("");
  const [picked, setPicked] = useState<CheckScannerPick>({ sayad: "", serial: "" });
  const [copied, setCopied] = useState("");

  function loadJsQR(): Promise<boolean> {
    if (window.jsQR) return Promise.resolve(true);
    return new Promise(resolve => {
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js";
      s.onload = () => resolve(Boolean(window.jsQR));
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    });
  }

  function pick(next: CheckScannerPick, notify = true) {
    setPicked(next);
    if (notify && onNumbers && (next.sayad || next.serial)) onNumbers(next);
  }

  async function handleFile(file: File) {
    setStatus("در حال پردازش تصویر…"); setDecoded("");
    const ok = await loadJsQR();
    if (!ok) { setStatus("بارگذاری کتابخانه خواننده QR ناموفق بود؛ اتصال اینترنت را بررسی کن."); return; }
    const img = new Image();
    const url = URL.createObjectURL(file);
    try {
      await new Promise<void>((res, rej) => { img.onload = () => res(); img.onerror = () => rej(new Error("image")); img.src = url; });
      const canvas = canvasRef.current;
      if (!canvas) { setStatus("بوم تصویر آماده نیست."); return; }
      const scale = Math.min(1, 900 / Math.max(img.width, img.height));
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext("2d");
      if (!ctx) { setStatus("رسم تصویر ممکن نشد."); return; }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const result = window.jsQR?.(data.data, canvas.width, canvas.height, { inversionAttempts: "attemptBoth" });
      if (result && result.data) {
        setDecoded(result.data);
        setStatus("QR خوانده شد.");
        if (autoPick) {
          // انتخاب خودکار: بلندترین عدد به‌عنوان شماره صیاد و عدد بعدی به‌عنوان سریال
          const numbers = extractNumbers(result.data).map(n => n.value).sort((a, b) => b.length - a.length);
          pick({ sayad: numbers[0] || "", serial: numbers[1] || "" });
        }
      } else {
        setDecoded("");
        setStatus("QR در تصویر پیدا نشد؛ تصویر واضح‌تری بگیر یا متن چک را دستی ثبت کن.");
      }
    } catch {
      setStatus("خواندن تصویر ناموفق بود؛ تصویر دیگری انتخاب کن.");
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  function onPickFile() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setImageName(file.name);
    void handleFile(file);
  }

  function reset() {
    setDecoded(""); setStatus(""); setImageName(""); setPicked({ sayad: "", serial: "" });
    if (fileRef.current) fileRef.current.value = "";
    const canvas = canvasRef.current;
    if (canvas) { canvas.width = 0; canvas.height = 0; }
  }

  function copy(value: string) {
    void navigator.clipboard?.writeText(value).then(() => setCopied(value)).catch(() => setCopied(""));
  }

  const numbers = decoded ? extractNumbers(decoded) : [];

  return <div className="space-y-4">
    <div className="space-y-3">
      <p className="text-xs text-slate-400">
        از دوربین گوشی عکس QR چک صیادی بگیر یا تصویر آماده را انتخاب کن. متن خوانده‌شده فقط روی همین دستگاه پردازش می‌شود و به سرور ارسال نمی‌شود.
      </p>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" className="text-xs text-slate-300" onChange={onPickFile} />
      {rawImageName && <p className="text-[10px] text-slate-500">تصویر انتخاب‌شده: {rawImageName}</p>}
      <canvas ref={canvasRef} className="max-w-full rounded-xl border border-white/10" />
      {status && <p className="text-xs text-violet-300">{status}</p>}
      <button type="button" className="rounded-lg border border-white/10 px-3 py-1.5 text-xs" onClick={reset}>عکس/تصویر دیگر</button>
    </div>

    {decoded && <div className="space-y-3">
      <p className="text-xs font-bold text-white">متن خوانده‌شده از QR</p>
      <p className="break-all rounded-xl border border-white/10 bg-black/30 p-3 text-xs leading-6 text-slate-200" dir="ltr">{decoded}</p>
      {numbers.length > 0 && <div className="space-y-2">
        <p className="text-xs font-bold text-white">شماره‌های یافت‌شده</p>
        {numbers.map(n => <div key={n.value} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 p-3 text-xs">
          <div><span className="font-mono text-white" dir="ltr">{n.value}</span>
            <span className="mr-3 text-[10px] text-slate-500">{n.label}</span></div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-lg border border-white/10 px-2.5 py-1 text-[10px]" onClick={() => copy(n.value)}>{copied === n.value ? "کپی شد" : "کپی"}</button>
            <button type="button" className="rounded-lg border border-violet-400/30 px-2.5 py-1 text-[10px] text-violet-300"
              onClick={() => pick({ ...picked, sayad: n.value })}>انتخاب به‌عنوان شماره صیاد</button>
            <button type="button" className="rounded-lg border border-white/10 px-2.5 py-1 text-[10px]"
              onClick={() => pick({ ...picked, serial: n.value })}>انتخاب به‌عنوان سریال چک</button>
          </div>
        </div>)}
      </div>}
      {showSummary && <div className="rounded-xl border border-violet-400/20 bg-violet-500/[0.07] p-4 text-xs">
        <b className="text-white">خلاصه انتخاب‌ها</b>
        <div className="mt-2 space-y-1 text-slate-300">
          <p>شماره صیاد انتخابی: <span className="font-mono text-white" dir="ltr">{picked.sayad || "—"}</span></p>
          <p>سریال چک انتخابی: <span className="font-mono text-white" dir="ltr">{picked.serial || "—"}</span></p>
        </div>
      </div>}
    </div>}
  </div>;
}
