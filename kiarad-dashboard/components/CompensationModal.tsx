"use client";

import Link from "next/link";
import { useEffect, useId, useRef } from "react";
import type { Salesperson } from "../lib/compensation-types";

export default function CompensationModal({ salesperson, onClose }: { salesperson: Salesperson; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const personName = salesperson.full_name?.trim() || salesperson.name?.trim() || "پرسنل انتخاب‌شده";
  const hasValidId = Number.isSafeInteger(salesperson.id) && salesperson.id > 0;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => { dialog.close(); };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      dir="rtl"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="m-auto w-[calc(100%-2rem)] max-w-xl rounded-2xl border border-purple-500/40 bg-slate-900 p-6 text-right text-white shadow-2xl backdrop:bg-black/70"
    >
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-4 border-b border-slate-800 pb-3">
          <h3 id={titleId} className="font-bold">حقوق و پورسانت {personName}</h3>
          <button type="button" onClick={onClose} aria-label="بستن" className="rounded px-2 py-1 text-slate-300 hover:bg-slate-800">✕</button>
        </div>
        <dl className="grid grid-cols-2 gap-3 rounded-xl bg-slate-800 p-4 text-sm">
          <dt className="text-slate-300">نام پرسنل</dt>
          <dd>{personName}</dd>
          <dt className="text-slate-300">شناسهٔ پرسنل</dt>
          <dd>{hasValidId ? salesperson.id.toLocaleString("fa-IR") : "نامشخص"}</dd>
        </dl>
        <p id={descriptionId} className="text-sm leading-7 text-slate-300">
          قواعد حقوق و پورسانت هر نفر برای ماه شمسی مشخص تنظیم و تأیید می‌شود. برای مشاهدهٔ نسخهٔ مربوط به ماه و تنظیم قواعد، صفحهٔ حقوق و پورسانت را باز کنید.
        </p>
        {!hasValidId && <p role="alert" className="text-sm text-red-300">شناسهٔ معتبر پرسنل دریافت نشده است. این پنجره را ببندید و فرد را دوباره انتخاب کنید.</p>}
        <div className="flex flex-wrap justify-end gap-3 border-t border-slate-800 pt-4">
          <button type="button" onClick={onClose} className="rounded bg-slate-800 px-4 py-2 text-sm">بستن</button>
          {hasValidId && (
            <Link href={`/compensation?salesperson_id=${salesperson.id}`} onClick={onClose} className="rounded bg-purple-600 px-4 py-2 text-sm font-bold hover:bg-purple-500">
              تنظیم قواعد ماهانه
            </Link>
          )}
        </div>
      </div>
    </dialog>
  );
}
