"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { IranDateInput } from "../../components/IranDateInput";
import { formatIranDate, iranTodayIso } from "../../lib/iran-date";
import { secureApi } from "../../lib/secure-api";
import { checkStatusLabel } from "./check-fields";

type Category = { id: number; name: string; kind: "income" | "expense"; total: number };
type Report = {
  start: string; end: string; income: number; expense: number; profit: number; basis: string;
  categories: Category[];
  checks_by_due_date: { document_type: string; status: string; sayad_registration: string; count: number; total: number }[];
  entry_count: number;
  spent_checks_by_destination: { destination: string; count: number; total: number }[];
  entries: { id: number; name: string; recognized_on: string; description: string; amount: number; check_id: number | null }[];
};

const irr = (value: number) => value.toLocaleString("fa-IR") + " ریال";

export function TreasuryAccounting({ checks, refreshKey }: { checks: { id: number; counterparty: string; amount: number }[]; refreshKey: number }) {
  const [report, setReport] = useState<Report | null>(null);
  const [range, setRange] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    secureApi<Report>("/treasury/accounting" + range).then(value => {
      if (active) setReport(value);
    }).catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [range, refreshKey]);

  async function submit(event: FormEvent<HTMLFormElement>, kind: "categories" | "entries") {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const body = kind === "categories"
      ? { name: data.get("name"), kind: data.get("kind") }
      : { category_id: Number(data.get("category_id")), amount: Number(data.get("amount")),
          recognized_on: data.get("recognized_on"), description: data.get("description"),
          check_id: data.get("check_id") ? Number(data.get("check_id")) : null };
    setError("");
    setBusy(true);
    try {
      await secureApi("/treasury/accounting/" + kind, { method: "POST", body: JSON.stringify(body) });
      if (kind === "categories") (form.elements.namedItem("name") as HTMLInputElement).value = "";
      else {
        (form.elements.namedItem("amount") as HTMLInputElement).value = "";
        (form.elements.namedItem("description") as HTMLInputElement).value = "";
        (form.elements.namedItem("check_id") as HTMLSelectElement).value = "";
      }
      setReport(await secureApi<Report>("/treasury/accounting" + range));
    } catch (err) { setError(err instanceof Error ? err.message : "ثبت انجام نشد."); }
    finally { setBusy(false); }
  }

  return <div className="space-y-4">
    {error && <p role="alert" className="text-rose-300">{error}</p>}
    <Surface className="space-y-3 p-4">
      <h3 className="font-bold">سود و زیان ثبت‌شده</h3>
      <form className="grid gap-2 sm:grid-cols-3" onSubmit={event => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setError("");
        setRange("?" + new URLSearchParams({ start: String(form.get("start")), end: String(form.get("end")) }));
      }}>
        <label className="text-xs">از تاریخ<IranDateInput required name="start" className={fieldClass} /></label>
        <label className="text-xs">تا تاریخ<IranDateInput required name="end" className={fieldClass} /></label>
        <button disabled={busy} className={primaryButton}>نمایش بازه</button>
      </form>
      {report && <>
        <p className="text-xs">{formatIranDate(report.start)} تا {formatIranDate(report.end)}</p>
        {report.entry_count === 0 && <p className="text-sm text-amber-200">در این بازه درآمد یا هزینه‌ای ثبت نشده است.</p>}
        <dl className="grid gap-2 sm:grid-cols-3">
          <div><dt>درآمد</dt><dd>{irr(report.income)}</dd></div>
          <div><dt>هزینه</dt><dd>{irr(report.expense)}</dd></div>
          <div><dt>سود یا زیان</dt><dd>{irr(report.profit)}</dd></div>
        </dl>
        <p className="text-xs text-slate-400">{report.basis}</p>
        {report.categories.map(item => <p className="text-sm" key={item.id}>{item.kind === "income" ? "درآمد" : "هزینه"} · {item.name} · {irr(item.total)}</p>)}
        {report.checks_by_due_date.length > 0 && <h4 className="text-sm font-bold">چک‌ها بر اساس سررسید و ثبت صیاد</h4>}
        {report.checks_by_due_date.map(item => <p className="text-sm" key={`${item.document_type}-${item.status}-${item.sayad_registration}`}>
          {item.document_type.startsWith("receivable") ? "دریافتنی" : "پرداختنی"} · {checkStatusLabel(item.status)} · {item.sayad_registration === "registered" ? "ثبت‌شده" : item.sayad_registration === "unregistered" ? "ثبت‌نشده" : "نامشخص"} · {item.count.toLocaleString("fa-IR")} فقره · {irr(item.total)}
        </p>)}
        {report.spent_checks_by_destination.length > 0 && <h4 className="text-sm font-bold">محل مصرف چک‌های خرج‌شده</h4>}
        {report.spent_checks_by_destination.map(item => <p className="text-sm" key={item.destination}>
          {item.destination} · {item.count.toLocaleString("fa-IR")} فقره · {irr(item.total)}
        </p>)}
      </>}
    </Surface>
    <Surface className="space-y-3 p-4">
      <h3 className="font-bold">تعریف سرفصل</h3>
      <form className="grid gap-2 sm:grid-cols-3" onSubmit={event => void submit(event, "categories")}>
        <input name="name" required minLength={2} maxLength={120} aria-label="عنوان سرفصل" placeholder="عنوان سرفصل" className={fieldClass} />
        <select name="kind" aria-label="نوع سرفصل" className={fieldClass}><option value="expense">هزینه</option><option value="income">درآمد</option></select>
        <button disabled={busy} className={primaryButton}>ثبت سرفصل</button>
      </form>
    </Surface>
    <Surface className="space-y-3 p-4">
      <h3 className="font-bold">ثبت درآمد یا هزینه</h3>
      <form className="grid gap-2 sm:grid-cols-2" onSubmit={event => void submit(event, "entries")}>
        <label className="text-xs">سرفصل<select name="category_id" required className={fieldClass} defaultValue="">
          <option value="" disabled>انتخاب سرفصل</option>
          {report?.categories.map(item => <option key={item.id} value={item.id}>{item.kind === "income" ? "درآمد" : "هزینه"} · {item.name}</option>)}
        </select></label>
        <label className="text-xs">مبلغ (ریال)<input name="amount" required type="number" min="1" max="100000000000000" className={fieldClass} /></label>
        <label className="text-xs">تاریخ شناسایی<IranDateInput name="recognized_on" required defaultValue={iranTodayIso()} className={fieldClass} /></label>
        <label className="text-xs">شرح<input name="description" required minLength={2} maxLength={300} className={fieldClass} /></label>
        <label className="text-xs">چک مرتبط (اختیاری)<select name="check_id" className={fieldClass}>
          <option value="">بدون چک</option>{checks.map(item => <option key={item.id} value={item.id}>#{item.id} · {item.counterparty} · {irr(item.amount)}</option>)}
        </select></label>
        <button disabled={busy || !report?.categories.length} className={primaryButton}>ثبت رویداد مالی</button>
      </form>
      {report?.entries.map(entry => <p className="text-sm" key={entry.id}>{formatIranDate(entry.recognized_on)} · {entry.name} · {entry.description} · {irr(entry.amount)}</p>)}
    </Surface>
  </div>;
}
