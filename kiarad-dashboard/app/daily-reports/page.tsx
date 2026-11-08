"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { getSavedUser, secureApi } from "../../lib/secure-api";
import { formatIranDate, iranTodayIso } from "../../lib/iran-date";
import { IranDateInput } from "../../components/IranDateInput";

type Report = { id: number; salesperson_name: string; report_date: string; visits_count: number; new_customers_count: number; orders_count: number; lost_orders_count: number; reported_sales_amount: number; reported_collections_amount: number; loss_reasons?: string; competitor_notes?: string; demand_notes?: string; issues?: string; tomorrow_plan?: string; notes?: string; };
const money = (v: number) => `${new Intl.NumberFormat("fa-IR", { notation: "compact", maximumFractionDigits: 1 }).format(v || 0)} ریال`;
const today = iranTodayIso;

export default function DailyReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const session = getSavedUser();
  const salesperson = session?.role === "salesperson";

  const load = useCallback(async () => {
    try { setReports((await secureApi<{ reports: Report[] }>("/daily-reports")).reports); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "دریافت گزارش‌ها انجام نشد."); }
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); setError("");
    const numberValue = (name: string) => Number(form.get(name) || 0);
    try {
      await secureApi("/daily-reports", { method: "POST", body: JSON.stringify({ report_date: form.get("report_date"), visits_count: numberValue("visits_count"), new_customers_count: numberValue("new_customers_count"), orders_count: numberValue("orders_count"), lost_orders_count: numberValue("lost_orders_count"), reported_sales_amount: numberValue("reported_sales_amount"), reported_collections_amount: numberValue("reported_collections_amount"), loss_reasons: form.get("loss_reasons") || null, competitor_notes: form.get("competitor_notes") || null, demand_notes: form.get("demand_notes") || null, issues: form.get("issues") || null, tomorrow_plan: form.get("tomorrow_plan") || null, notes: form.get("notes") || null }) });
      event.currentTarget.reset(); setMessage("گزارش شبانه ثبت شد و از این پس در تحلیل‌های مدیریتی قابل استفاده است."); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "ثبت گزارش انجام نشد."); }
  };

  const latest = reports[0];
  return <PortalShell title={salesperson ? "ثبت گزارش شبانه" : "گزارش‌های شبانه تیم فروش"} eyebrow="داده عملیاتی ویزیتورها">
    {(error || message) && <div className={`mb-4 rounded-xl border p-3 text-xs ${error ? "border-rose-500/20 bg-rose-500/10 text-rose-300" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"}`}>{error || message}</div>}
    <div className="grid gap-4 xl:grid-cols-[.85fr_1.15fr]">
      {salesperson ? <Surface className="p-5"><h2 className="text-sm font-bold text-white">فرم پایان روز</h2><p className="mt-2 text-[10px] leading-5 text-slate-500">اعداد واقعی روز و نکات بازار را ثبت کنید. این داده مستقیماً وارد تحلیل و پیش‌بینی می‌شود.</p><form onSubmit={submit} className="mt-5 space-y-3"><IranDateInput aria-label="تاریخ گزارش شمسی" name="report_date" defaultValue={today()} max={today()} required className={fieldClass} /><div className="grid grid-cols-2 gap-3"><Numeric name="visits_count" label="تعداد ویزیت" /><Numeric name="new_customers_count" label="مشتری جدید" /><Numeric name="orders_count" label="سفارش موفق" /><Numeric name="lost_orders_count" label="سفارش ازدست‌رفته" /></div><div className="grid grid-cols-2 gap-3"><Numeric name="reported_sales_amount" label="فروش روزانه (ریال)" /><Numeric name="reported_collections_amount" label="وصول روزانه (ریال)" /></div><textarea name="loss_reasons" rows={2} placeholder="دلایل فروش ازدست‌رفته" className={fieldClass} /><textarea name="competitor_notes" rows={2} placeholder="قیمت و فعالیت رقبا" className={fieldClass} /><textarea name="demand_notes" rows={2} placeholder="محصولات مورد تقاضای بازار" className={fieldClass} /><textarea name="issues" rows={2} placeholder="موانع و مشکلات امروز" className={fieldClass} /><textarea name="tomorrow_plan" rows={2} placeholder="برنامه فردا" className={fieldClass} /><button className={`${primaryButton} w-full`}>ثبت گزارش شبانه</button></form></Surface> : <Surface className="p-5"><h2 className="text-sm font-bold text-white">خلاصه آخرین گزارش</h2>{latest ? <div className="mt-5"><div className="text-lg font-black text-white">{latest.salesperson_name}</div><div className="mt-1 text-[10px] text-slate-500">{formatIranDate(latest.report_date)}</div><div className="mt-5 grid grid-cols-2 gap-3"><Summary label="ویزیت" value={latest.visits_count} /><Summary label="سفارش" value={latest.orders_count} /><Summary label="فروش اعلامی" value={money(latest.reported_sales_amount)} /><Summary label="وصول اعلامی" value={money(latest.reported_collections_amount)} /></div><p className="mt-4 rounded-xl bg-white/[0.03] p-3 text-[10px] leading-6 text-slate-400">{latest.tomorrow_plan || latest.notes || "یادداشت تکمیلی ثبت نشده است."}</p></div> : <p className="mt-8 text-xs text-slate-600">هنوز گزارشی ثبت نشده است.</p>}</Surface>}
      <Surface className="overflow-hidden"><div className="border-b border-white/[0.06] p-5"><h2 className="text-sm font-bold text-white">سوابق گزارش‌ها</h2><p className="mt-1 text-[10px] text-slate-500">آخرین گزارش‌های ثبت‌شده و شاخص‌های کلیدی روز</p></div><div className="divide-y divide-white/[0.05]">{reports.slice(0,20).map(report => <article key={report.id} className="p-4"><div className="flex items-start justify-between"><div><h3 className="text-xs font-bold text-white">{report.salesperson_name}</h3><p className="mt-1 text-[9px] text-slate-600">{formatIranDate(report.report_date)}</p></div><span className="rounded-lg bg-violet-500/10 px-2 py-1 text-[9px] text-violet-300">{report.orders_count} سفارش از {report.visits_count} ویزیت</span></div><div className="mt-3 grid grid-cols-2 gap-2 text-[9px] sm:grid-cols-4"><Summary label="فروش" value={money(report.reported_sales_amount)} /><Summary label="وصول" value={money(report.reported_collections_amount)} /><Summary label="مشتری جدید" value={report.new_customers_count} /><Summary label="فروش ازدست‌رفته" value={report.lost_orders_count} /></div>{(report.competitor_notes || report.issues) && <p className="mt-3 text-[9px] leading-5 text-slate-500">{report.competitor_notes || report.issues}</p>}</article>)}{!reports.length && <div className="p-10 text-center text-xs text-slate-600">گزارشی وجود ندارد.</div>}</div></Surface>
    </div>
  </PortalShell>;
}

function Numeric({ name, label }: { name: string; label: string }) { return <label className="text-[9px] text-slate-500">{label}<input name={name} type="number" min="0" defaultValue="0" className={`${fieldClass} mt-1`} /></label>; }
function Summary({ label, value }: { label: string; value: string | number }) { return <div className="rounded-xl bg-white/[0.035] p-3"><div className="text-[9px] text-slate-600">{label}</div><div className="mt-1 truncate text-[10px] font-bold text-slate-300">{typeof value === "number" ? new Intl.NumberFormat("fa-IR").format(value) : value}</div></div>; }
