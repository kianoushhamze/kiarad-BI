"use client";


import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
import { formatIranDate, iranTodayIso } from "../../lib/iran-date";
import { IranDateInput } from "../../components/IranDateInput";
import { CheckScanner } from "../../components/check-scanner";
import { TreasuryStrategy } from "../../components/treasury-strategy";

type Account = { id: number; name: string; account_type: string; current_balance: number; minimum_reserve: number };
type Document = { id: number; document_type: "receivable" | "payable" | "receivable_check" | "payable_check"; counterparty: string; amount: number; due_date: string; status: string; collection_probability: number; reference_number?: string };
type FixedExpense = { id: number; title: string; amount: number; due_day: number };
type Debtor = { id: number; counterparty: string; balance: number; share_percent?: number | null; customer_id?: number | null };
type DebtorSnapshot = { id: number; source_file: string; report_from_text?: string; report_to_text?: string; snapshot_date: string; total_amount: number; row_count: number; top_debtors: Debtor[] };
type Overview = {
  summary: { cash_balance: number; minimum_reserve: number; open_receivables: number; open_payables: number };
  accounts: Account[];
  documents: Document[];
  fixed_expenses: FixedExpense[];
  debtor_snapshot?: DebtorSnapshot | null;
};
type ForecastEvent = { type: string; title: string; amount: number; is_overdue?: boolean; reference_number?: string };
type Recommendation = { type: "collection" | "cash_sale" | "reschedule"; priority: string; title: string; target_amount: number; available_balance?: number; customer_id?: number | null; reason: string; executed_task_id?: number | null };
type Forecast = {
  period: { start: string; end: string; days: number };
  opening_balance: number;
  minimum_reserve: number;
  summary: { receivables_7_days: number; payables_7_days: number; receivables_30_days: number; payables_30_days: number; expected_inflow: number; planned_outflow: number; closing_expected_balance: number; peak_shortage: number };
  warnings: { date: string; start_date: string; end_date: string; shortage: number; max_shortage: number; message: string }[];
  recommendations: Recommendation[];
  timeline: { date: string; expected_balance: number; available_after_reserve: number; events: ForecastEvent[] }[];
};
type ModalKind = "account" | "account-edit" | "document" | "expense" | null;

const money = (value: number) => `${new Intl.NumberFormat("fa-IR", { notation: "compact", maximumFractionDigits: 1 }).format(value || 0)} ریال`;
const fullMoney = (value: number) => `${new Intl.NumberFormat("fa-IR").format(Math.round(value || 0))} ریال`;
const persianDate = formatIranDate;
const reportPeriodDate = (value?: string) => {
  if (!value?.trim()) return "نامشخص";
  // Imported reports can already contain Persian dates or descriptive periods.
  return /^(19|20)\d{2}-\d{2}-\d{2}$/.test(value.trim())
    ? formatIranDate(value.trim()) : value;
};
const today = iranTodayIso;

export default function TreasuryPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [forecastDays, setForecastDays] = useState<30 | 60>(60);
  const [modal, setModal] = useState<ModalKind>(null);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [importing, setImporting] = useState(false);
  const [executing, setExecuting] = useState<string | null>(null);
  const [scannedCheck, setScannedCheck] = useState<{ sayad: string; serial: string } | null>(null);
  const docRefInputRef = useRef<HTMLInputElement | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setError("");
    try {
      const [overviewData, forecastData] = await Promise.all([
        secureApi<Overview>("/treasury/overview"),
        secureApi<Forecast>(`/treasury/forecast?days=${forecastDays}`),
      ]);
      setOverview(overviewData);
      setForecast(forecastData);
      setRefreshKey(value => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "دریافت اطلاعات خزانه انجام نشد.");
    }
  }, [forecastDays]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  const submit = async (event: FormEvent<HTMLFormElement>, kind: Exclude<ModalKind, null>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      if (kind === "account") {
        await secureApi("/treasury/accounts", { method: "POST", body: JSON.stringify({ name: form.get("name"), account_type: form.get("account_type"), current_balance: Number(form.get("current_balance")), minimum_reserve: Number(form.get("minimum_reserve")) }) });
      } else if (kind === "account-edit" && editingAccount) {
        await secureApi(`/treasury/accounts/${editingAccount.id}`, { method: "PATCH", body: JSON.stringify({ current_balance: Number(form.get("current_balance")), minimum_reserve: Number(form.get("minimum_reserve")) }) });
      } else if (kind === "document") {
        await secureApi("/treasury/documents", { method: "POST", body: JSON.stringify({ document_type: form.get("document_type"), counterparty: form.get("counterparty"), amount: Number(form.get("amount")), due_date: form.get("due_date"), collection_probability: Number(form.get("collection_probability") || 1), reference_number: form.get("reference_number") || null, notes: form.get("notes") || null, fixed_expense_id: form.get("fixed_expense_id") ? Number(form.get("fixed_expense_id")) : null }) });
      } else if (kind === "expense") {
        await secureApi("/treasury/fixed-expenses", { method: "POST", body: JSON.stringify({ title: form.get("title"), amount: Number(form.get("amount")), due_day: Number(form.get("due_day")), notes: form.get("notes") || null }) });
      }
      setModal(null);
      setEditingAccount(null);
      setMessage("اطلاعات ثبت شد و پیش‌بینی نقدینگی دوباره محاسبه شد.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ثبت اطلاعات انجام نشد.");
    }
  };

  const changeDocumentStatus = async (document: Document, status: "settled" | "cancelled") => {
    try {
      await secureApi(`/treasury/documents/${document.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setMessage(status === "settled" ? "سند تسویه شد." : "سند لغو شد.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "تغییر وضعیت انجام نشد."); }
  };

  const deactivate = async (kind: "accounts" | "fixed-expenses", id: number, label: string) => {
    if (!window.confirm(`«${label}» غیرفعال شود؟ اطلاعات قبلی حذف نخواهد شد.`)) return;
    try {
      await secureApi(`/treasury/${kind}/${id}`, { method: "DELETE" });
      setMessage("مورد انتخاب‌شده غیرفعال شد.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "عملیات انجام نشد."); }
  };

  const executeRecommendation = async (recommendation: Recommendation) => {
    if (!window.confirm(`اقدام «${recommendation.title}» با هدف ${fullMoney(recommendation.target_amount)} تأیید و به تسک تبدیل شود؟`)) return;
    setExecuting(recommendation.title);
    try {
      const result = await secureApi<{ task_id: number }>("/treasury/actions/execute", { method: "POST", body: JSON.stringify({ action_type: recommendation.type, title: recommendation.title, target_amount: recommendation.target_amount, reason: recommendation.reason, customer_id: recommendation.customer_id || null }) });
      setMessage(`اقدام تأیید شد و تسک شماره ${result.task_id.toLocaleString("fa-IR")} ایجاد شد.`);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "اجرای پیشنهاد انجام نشد."); }
    finally { setExecuting(null); }
  };

  const importDebtors = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setImporting(true); setError(""); setMessage("");
    try {
      const result = await secureApi<{ row_count: number; total_amount: number; matched_customers: number; unmatched_customers: number }>("/treasury/import/debtors", { method: "POST", body: await file.arrayBuffer(), headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "X-File-Name": encodeURIComponent(file.name) } });
      setMessage(`${result.row_count.toLocaleString("fa-IR")} بدهکار با جمع ${money(result.total_amount)} وارد شد؛ ${result.matched_customers.toLocaleString("fa-IR")} مورد تطبیق یافت.`);
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "ورود فایل انجام نشد."); }
    finally { setImporting(false); }
  };

  const deleteSnapshot = async (snapshot: DebtorSnapshot) => {
    if (!window.confirm(`گزارش «${snapshot.source_file}» و تمام ردیف‌های آن حذف شود؟`)) return;
    try {
      await secureApi(`/treasury/import/debtors/${snapshot.id}`, { method: "DELETE" });
      setMessage("گزارش واردشده حذف شد.");
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "حذف گزارش انجام نشد."); }
  };

  const [showStrategy, setShowStrategy] = useState(false);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("check") !== "new") return;
    void Promise.resolve().then(() => setModal("document"));
  }, []);
  const summary = overview?.summary;
  const hasFinancialData = !!overview && (overview.accounts.length > 0 || overview.documents.length > 0 || overview.fixed_expenses.length > 0 || !!overview.debtor_snapshot);
  const liquidity = forecast?.summary;
  const firstWarning = [...(forecast?.warnings ?? [])].sort((a, b) => b.max_shortage - a.max_shortage)[0];
  const chart = (forecast?.timeline ?? []).filter((_, index) => index % (forecastDays === 60 ? 5 : 2) === 0);
  const maxAbs = Math.max(...chart.map(point => Math.abs(point.available_after_reserve)), 1);

  return <PortalShell title="خزانه‌داری و پایش نقدینگی" eyebrow="مدیریت مالی" actions={<div className="flex flex-wrap gap-2"><label className="cursor-pointer rounded-xl border border-white/10 px-3 py-2 text-[10px] text-slate-300 hover:bg-white/5">{importing ? "در حال ورود…" : "ورود اکسل بدهکاران"}<input type="file" accept=".xlsx" disabled={importing} onChange={importDebtors} className="hidden" /></label><button onClick={() => setModal("account")} className="rounded-xl border border-white/10 px-3 py-2 text-[10px] text-slate-300">حساب بانکی/نقدی</button><button onClick={() => { setScannedCheck(null); setModal("document"); }} className={primaryButton}>ثبت چک یا سند</button></div>}>
    {(error || message) && <div className={`mb-4 rounded-xl border p-3 text-xs ${error ? "border-rose-500/20 bg-rose-500/10 text-rose-300" : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"}`}>{error || message}</div>}

    <h2 className="mb-4 text-base font-bold text-white">ثبت و عملیات روزانهٔ خزانه</h2>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="موجودی نقد" value={summary ? money(summary.cash_balance) : "—"} tone="text-emerald-300" />
      <Metric label="مانده بدهکاران" value={overview?.debtor_snapshot ? money(overview.debtor_snapshot.total_amount) : summary ? money(summary.open_receivables) : "—"} tone="text-cyan-300" />
      <Metric label="پرداختنی باز" value={summary ? money(summary.open_payables) : "—"} tone="text-rose-300" />
      <Metric label="ذخیره حداقلی" value={summary ? money(summary.minimum_reserve) : "—"} tone="text-violet-300" />
    </div>

    <Surface className="mt-4 grid gap-px overflow-hidden bg-white/[0.05] sm:grid-cols-2 xl:grid-cols-4">
      <MiniMetric label="دریافتنی تا ۷ روز" value={money(liquidity?.receivables_7_days ?? 0)} tone="text-emerald-300" />
      <MiniMetric label="پرداختنی تا ۷ روز" value={money(liquidity?.payables_7_days ?? 0)} tone="text-rose-300" />
      <MiniMetric label="ورودی مورد انتظار دوره" value={money(liquidity?.expected_inflow ?? 0)} tone="text-cyan-300" />
      <MiniMetric label="خروجی برنامه‌ریزی‌شده" value={money(liquidity?.planned_outflow ?? 0)} tone="text-amber-300" />
    </Surface>

    <div className="mt-4 grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
      <Surface className="p-5">
        <div className="flex items-start justify-between gap-4"><div><h2 className="text-sm font-bold text-white">پیش‌بینی موجودی قابل‌استفاده</h2><p className="mt-1 text-[10px] text-slate-500">پس از ذخیره حداقلی، چک‌ها، هزینه‌های ثابت و احتمال وصول</p></div><div className="flex rounded-xl border border-white/10 p-1 text-[9px]"><button onClick={() => setForecastDays(30)} className={`rounded-lg px-3 py-1.5 ${forecastDays === 30 ? "bg-violet-600 text-white" : "text-slate-500"}`}>۳۰ روز</button><button onClick={() => setForecastDays(60)} className={`rounded-lg px-3 py-1.5 ${forecastDays === 60 ? "bg-violet-600 text-white" : "text-slate-500"}`}>۶۰ روز</button></div></div>
        <div className="relative mt-6 flex h-52 gap-2 px-2"><div className="pointer-events-none absolute inset-x-0 top-1/2 border-t border-slate-500/50" />{chart.map(point => { const negative = point.available_after_reserve < 0; const height = Math.abs(point.available_after_reserve) / maxAbs * 95; return <div key={point.date} tabIndex={0} aria-label={`${persianDate(point.date)}: ${fullMoney(point.available_after_reserve)}`} title={`${persianDate(point.date)}: ${fullMoney(point.available_after_reserve)}`} className="relative flex-1"><div className={`absolute w-full ${negative ? "top-1/2 rounded-b-md bg-rose-500/75" : "bottom-1/2 rounded-t-md bg-gradient-to-t from-violet-700 to-cyan-400"}`} style={{ height }} /></div>; })}</div>
        <div className="mt-3 flex justify-between text-[9px] text-slate-600"><span>امروز</span><span>{(forecastDays / 2).toLocaleString("fa-IR")} روز آینده</span><span>{forecastDays.toLocaleString("fa-IR")} روز آینده</span></div>
      </Surface>

      <Surface className="p-5"><h2 className="text-sm font-bold text-white">هشدار تأمین وجه</h2>{firstWarning ? <div className="mt-5 rounded-2xl border border-rose-500/20 bg-rose-500/10 p-4"><div className="text-[10px] text-rose-300">بیشترین کسری دوره</div><div className="mt-2 text-xl font-black text-white">{money(firstWarning.max_shortage)}</div><div className="mt-2 text-[10px] text-slate-400">از {persianDate(firstWarning.start_date)} تا {persianDate(firstWarning.end_date)}</div><p className="mt-4 text-[10px] leading-5 text-rose-200">قبل از این بازه باید وصول مطالبات، فروش نقدی یا جابه‌جایی سررسید برنامه‌ریزی شود.</p></div> : <div className="mt-5 rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.07] p-4 text-[11px] leading-6 text-emerald-300">{hasFinancialData ? "با رکوردهای ثبت‌شده کسری پیش‌بینی نشده؛ کامل‌بودن حساب‌ها و سررسیدها باید بررسی شود." : "دادهٔ مالی کافی ثبت نشده؛ نبود هشدار به معنی کافی‌بودن وجه نیست."}</div>}<button onClick={() => setModal("expense")} className="mt-4 w-full rounded-xl border border-white/10 py-2.5 text-[10px] text-slate-300">ثبت هزینه ثابت ماهانه</button></Surface>
    </div>

    <Surface className="mt-4 overflow-hidden"><Header title="برنامه پیشنهادی تأمین نقدینگی" subtitle="هر پیشنهاد فقط پس از تأیید شما به تسک عملیاتی تبدیل می‌شود" /><div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-px bg-white/[0.04]">{forecast?.recommendations.slice(0, 6).map(item => <div key={`${item.type}-${item.title}`} className="bg-[#0c0e18] p-5"><div className="flex items-center justify-between"><span className={`rounded-full px-2 py-1 text-[8px] ${item.priority === "high" ? "bg-rose-500/10 text-rose-300" : "bg-amber-500/10 text-amber-300"}`}>{item.priority === "high" ? "اولویت بالا" : "اولویت متوسط"}</span><span className="text-[9px] text-slate-600">{item.type === "collection" ? "وصول" : item.type === "cash_sale" ? "فروش نقدی" : "مذاکره سررسید"}</span></div><h3 className="mt-4 text-xs font-bold text-white">{item.title}</h3><div className="mt-2 text-lg font-black text-cyan-300">{money(item.target_amount)}</div><p className="mt-3 min-h-10 text-[9px] leading-5 text-slate-500">{item.reason}</p><button disabled={Boolean(item.executed_task_id) || executing === item.title} onClick={() => executeRecommendation(item)} className="mt-4 w-full rounded-xl border border-violet-500/25 bg-violet-500/10 py-2 text-[9px] font-bold text-violet-200 hover:bg-violet-500/20 disabled:cursor-not-allowed disabled:opacity-50">{item.executed_task_id ? `تسک شماره ${item.executed_task_id.toLocaleString("fa-IR")} ایجاد شده` : executing === item.title ? "در حال اجرا…" : "تأیید و ایجاد تسک"}</button></div>)}{!forecast?.recommendations.length && <div className="col-span-full"><Empty text={hasFinancialData ? "با دادهٔ ثبت‌شده پیشنهاد اضطراری تولید نشد؛ این نتیجه تضمین کفایت وجه نیست." : "ابتدا حساب‌ها، چک‌ها و هزینه‌ها را تکمیل کنید؛ ارزیابی نقدینگی هنوز ممکن نیست."} /></div>}</div></Surface>

    {overview?.debtor_snapshot && <Surface className="mt-4 overflow-hidden"><div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/[0.06] p-5"><div><h2 className="text-sm font-bold text-white">آخرین تصویر مانده بدهکاران</h2><p className="mt-1 text-[10px] text-slate-500">{overview.debtor_snapshot.source_file} · دوره {reportPeriodDate(overview.debtor_snapshot.report_from_text)} تا {reportPeriodDate(overview.debtor_snapshot.report_to_text)} · {overview.debtor_snapshot.row_count.toLocaleString("fa-IR")} ردیف</p></div><button onClick={() => deleteSnapshot(overview.debtor_snapshot!)} className="rounded-lg border border-rose-500/20 px-3 py-2 text-[9px] text-rose-300">حذف این گزارش</button></div><div className="grid gap-px bg-white/[0.04] sm:grid-cols-2 xl:grid-cols-4">{overview.debtor_snapshot.top_debtors.slice(0, 8).map((debtor, index) => <div key={debtor.id} className="bg-[#0c0e18] p-4"><div className="flex items-center gap-2"><span className="grid h-6 w-6 place-items-center rounded-lg bg-violet-500/10 text-[9px] text-violet-300">{(index + 1).toLocaleString("fa-IR")}</span><div className="min-w-0 flex-1 truncate text-[10px] font-bold text-white">{debtor.counterparty}</div></div><div className="mt-3 flex items-end justify-between"><span className="text-xs font-black text-cyan-300">{money(debtor.balance)}</span><span className="text-[9px] text-slate-600">{debtor.share_percent?.toLocaleString("fa-IR", { maximumFractionDigits: 2 }) ?? "—"}٪</span></div></div>)}</div></Surface>}

    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <Surface className="overflow-hidden"><Header title="چک‌ها و اسناد دریافتنی/پرداختنی" subtitle="سررسیدگذشته‌ها با هشدار مشخص شده‌اند" /><div className="divide-y divide-white/[0.05]">{overview?.documents.slice(0, 20).map(document => { const overdue = ["open", "overdue", "bounced"].includes(document.status) && document.due_date < today(); return <div key={document.id} className="grid grid-cols-[1fr_auto] gap-3 p-4 text-[10px]"><div><div className="flex items-center gap-2"><b className="text-white">{document.counterparty}</b>{overdue && <span className="rounded-full bg-rose-500/10 px-2 py-0.5 text-[8px] text-rose-300">سررسیدگذشته</span>}</div><div className="mt-1 text-[9px] text-slate-600">{["receivable", "receivable_check"].includes(document.document_type) ? "دریافتنی" : "پرداختنی"} · {persianDate(document.due_date)}{document.reference_number ? ` · شماره ${document.reference_number}` : ""}</div></div><div className="text-left"><div className={["receivable", "receivable_check"].includes(document.document_type) ? "text-emerald-300" : "text-rose-300"}>{money(document.amount)}</div>{["open", "overdue", "bounced"].includes(document.status) ? <div className="mt-2 flex gap-2"><button onClick={() => changeDocumentStatus(document, "settled")} className="rounded-lg border border-emerald-500/20 px-2 py-1 text-[8px] text-emerald-300">تسویه</button><button onClick={() => changeDocumentStatus(document, "cancelled")} className="rounded-lg border border-white/10 px-2 py-1 text-[8px] text-slate-500">لغو</button></div> : <span className="mt-2 block text-[8px] text-slate-600">{["settled", "cleared"].includes(document.status) ? "تسویه‌شده" : document.status === "bounced" ? "برگشتی" : "لغوشده"}</span>}</div></div>; })}{!overview?.documents.length && <Empty />}</div></Surface>

      <Surface className="overflow-hidden"><Header title="حساب‌ها و هزینه‌های ثابت" subtitle="مبنای ذخیره نقدی و خروجی‌های دوره‌ای" /><div className="p-4"><div className="space-y-2">{overview?.accounts.map(account => <div key={account.id} className="rounded-xl bg-white/[0.035] p-3"><div className="flex justify-between gap-3 text-[10px]"><div><b className="text-white">{account.name}</b><div className="mt-1 text-[9px] text-slate-600">ذخیره: {money(account.minimum_reserve)}</div></div><div className="text-left"><span className="text-emerald-300">{money(account.current_balance)}</span><div className="mt-2 flex gap-2"><button onClick={() => { setEditingAccount(account); setModal("account-edit"); }} className="text-[8px] text-violet-300">اصلاح موجودی</button><button onClick={() => deactivate("accounts", account.id, account.name)} className="text-[8px] text-rose-400">غیرفعال</button></div></div></div></div>)}</div><div className="mt-5 border-t border-white/[0.06] pt-4"><div className="mb-3 text-[10px] font-bold text-slate-300">هزینه‌های ثابت</div>{overview?.fixed_expenses.map(expense => <div key={expense.id} className="mb-2 flex justify-between gap-3 rounded-xl bg-black/15 p-3 text-[10px]"><span className="text-slate-300">{expense.title} · روز {expense.due_day.toLocaleString("fa-IR")} ماه</span><div className="text-left"><span className="text-amber-300">{money(expense.amount)}</span><button onClick={() => deactivate("fixed-expenses", expense.id, expense.title)} className="mt-1 block text-[8px] text-rose-400">غیرفعال</button></div></div>)}{!overview?.accounts.length && !overview?.fixed_expenses.length && <Empty />}</div></div></Surface>
    </div>

    <Surface className="mt-4 p-4">
      <button type="button" aria-expanded={showStrategy} onClick={() => setShowStrategy(value => !value)}
        className="text-sm text-violet-300">تحلیل نقدینگی و برنامهٔ مالی</button>
      {showStrategy && <div className="mt-3"><TreasuryStrategy refreshKey={refreshKey} /></div>}
    </Surface>
    {modal && <Modal title={modal === "account" ? "ثبت حساب بانکی یا نقدی" : modal === "account-edit" ? `اصلاح موجودی ${editingAccount?.name || "حساب"}` : modal === "document" ? "ثبت چک یا سند مالی" : "ثبت هزینه ثابت"} close={() => { setModal(null); setEditingAccount(null); }}><form onSubmit={event => submit(event, modal)} className="space-y-3">{modal === "account" && <><input name="name" required placeholder="نام حساب یا بانک" className={fieldClass} /><select name="account_type" className={fieldClass}><option value="bank">حساب بانکی</option><option value="cash">صندوق</option><option value="other">سایر</option></select><input name="current_balance" type="number" min="0" required placeholder="موجودی فعلی (ریال)" className={fieldClass} /><input name="minimum_reserve" type="number" min="0" defaultValue="0" placeholder="حداقل ذخیره (ریال)" className={fieldClass} /></>}{modal === "account-edit" && <><label className="block text-[9px] text-slate-500">موجودی فعلی<input name="current_balance" type="number" min="0" required defaultValue={editingAccount?.current_balance} className={`${fieldClass} mt-1`} /></label><label className="block text-[9px] text-slate-500">حداقل ذخیره<input name="minimum_reserve" type="number" min="0" required defaultValue={editingAccount?.minimum_reserve} className={`${fieldClass} mt-1`} /></label></>}{modal === "document" && <><select name="document_type" className={fieldClass}><option value="receivable">چک/سند دریافتنی</option><option value="payable">چک/سند پرداختنی</option></select><input name="counterparty" required placeholder="طرف حساب" className={fieldClass} /><input name="amount" type="number" min="1" required placeholder="مبلغ (ریال)" className={fieldClass} /><label className="block text-[9px] text-slate-500">تاریخ سررسید<IranDateInput name="due_date" required className={`${fieldClass} mt-1`} /></label><input ref={docRefInputRef} name="reference_number" placeholder="شماره چک/سند" className={fieldClass} /><label className="block text-[10px] text-slate-400">ارتباط با هزینهٔ ثابت؛ فقط سند پرداختنی<select name="fixed_expense_id" className={fieldClass}><option value="">هزینهٔ مستقلی است</option>{overview?.fixed_expenses.map(expense => <option key={expense.id} value={expense.id}>{expense.title}</option>)}</select></label><label className="block text-[9px] text-slate-500">احتمال وصول دریافتنی (از صفر تا یک)<input name="collection_probability" type="number" min="0" max="1" step="0.05" defaultValue="1" className={`${fieldClass} mt-1`} /></label><div className="rounded-xl border border-white/10 p-3"><p className="mb-2 text-[10px] text-slate-400">اسکن QR چک صیادی — پس از اسکن موفق، سریال خودکار در «شماره چک/سند» پر می‌شود و متن QR فقط روی همین دستگاه پردازش می‌شود.</p><CheckScanner onNumbers={pick => { setScannedCheck(pick); if (pick.serial && docRefInputRef.current) docRefInputRef.current.value = pick.serial; }} />{scannedCheck && <p className="mt-2 text-[10px] text-emerald-300">خوانده شد — صیاد: {scannedCheck.sayad || "—"} · سریال: {scannedCheck.serial || "—"}</p>}</div><textarea name="notes" rows={2} placeholder="بانک، شعبه یا توضیحات" className={fieldClass} /></>}{modal === "expense" && <><input name="title" required placeholder="عنوان هزینه ثابت" className={fieldClass} /><input name="amount" type="number" min="1" required placeholder="مبلغ ماهانه (ریال)" className={fieldClass} /><input name="due_day" type="number" min="1" max="31" required placeholder="روز سررسید در ماه" className={fieldClass} /><textarea name="notes" rows={2} placeholder="توضیحات" className={fieldClass} /></>}<button className={`${primaryButton} w-full`}>ثبت و محاسبه مجدد</button></form></Modal>}
  </PortalShell>;
}

function Metric({ label, value, tone }: { label: string; value: string; tone: string }) { return <Surface className="p-4"><div className="text-[10px] text-slate-500">{label}</div><div className={`mt-3 text-xl font-black ${tone}`}>{value}</div></Surface>; }
function MiniMetric({ label, value, tone }: { label: string; value: string; tone: string }) { return <div className="bg-[#0c0e18] p-4"><div className="text-[9px] text-slate-600">{label}</div><div className={`mt-2 text-sm font-black ${tone}`}>{value}</div></div>; }
function Header({ title, subtitle }: { title: string; subtitle: string }) { return <div className="border-b border-white/[0.06] p-5"><h2 className="text-sm font-bold text-white">{title}</h2><p className="mt-1 text-[10px] text-slate-500">{subtitle}</p></div>; }
function Empty({ text = "اطلاعاتی ثبت نشده است." }: { text?: string }) { return <div className="p-8 text-center text-[10px] text-slate-600">{text}</div>; }
function Modal({ title, close, children }: { title: string; close: () => void; children: ReactNode }) { return <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"><div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-3xl border border-white/10 bg-[#0c0e19] p-5"><div className="mb-5 flex items-center justify-between"><h2 className="text-sm font-bold text-white">{title}</h2><button type="button" onClick={close} className="text-xl text-slate-500">×</button></div>{children}</div></div>; }
