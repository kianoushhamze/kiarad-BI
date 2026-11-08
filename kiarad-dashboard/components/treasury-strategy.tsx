"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Surface, fieldClass, primaryButton } from "./portal-shell";
import { secureApi, getSavedUser, ApiError } from "../lib/secure-api";
import { formatIranDate, formatIranDateTime } from "../lib/iran-date";
import styles from "./treasury-strategy.module.css";
import { matchesSearch } from "../lib/text-search";
import { TreasuryOperatingPlan, type OperatingPlan, type OperatingProjection, type PurchaseEstimate, type RefreshStatus } from "./treasury-operating-plan";
import { TreasuryExcel, type ExcelEstimate } from "./treasury-excel";

type Statement = {
  net_sales: number; gross_profit: number; contribution: number; operating_profit: number; net_profit: number;
  gross_margin_percent: number | null; net_margin_percent: number | null; contribution_margin_percent: number | null;
  break_even_sales: number | null; dso: number | null; dio: number | null; dpo: number | null;
  cash_conversion_days: number | null; current_ratio: number | null;
};
type Report = { id: number; scope: string; revision: number; approved_by: number | null; created_at: string; payload: Record<string, string | number | boolean | null>; statement: Statement };
type GrowthRow = { month: string; target: number; actual: number | null; gap: number | null; attainment_percent: number | null };
type Week = { start: string; end: string; base: number; no_inflows: number; scenario: number; base_minimum: number; scenario_minimum: number };
type CashSummary = { closing: number; minimum: number; shortage: number; first_shortage: string | null; inflow: number; outflow: number };
type Projection = { start: string; end: string; opening: number; reserve: number; weeks: Week[]; cash_accounts_available: boolean; scenarios: { base: CashSummary; no_inflows: CashSummary; scenario: CashSummary } };
type QueueRow = { id: number; counterparty: string; direction: string; amount: number; due_date: string; overdue_days: number; status: string; customer_id: number | null; bounced: boolean };
type Strategy = {
  operating_plan: OperatingPlan; operating_plan_revision: number; operating_projection: OperatingProjection; purchase_estimate: PurchaseEstimate | null; holoo_refresh: RefreshStatus;
  excel_estimate: ExcelEstimate | null;
  as_of: string; current_month: string; settings_revision: number;
  settings: { baseline_month: string | null; baseline_profit: string | number | null; monthly_growth_percent: string | number; end_month: string; source_note: string };
  reports: Report[]; approved_actuals: Report[]; growth: { status: string; rows: GrowthRow[] }; projection: Projection;
  accounts: { id: number; name: string; current_balance: number; updated_at: string | null }[];
  collections: { aging: { id: string; label: string; receivable: number; payable: number; count: number }[]; queue: QueueRow[]; concentration: { counterparty: string; balance: number; overdue: number; share_percent: number }[]; top_five_share_percent: number | null; duplicate_references: number[][] };
  coverage: { id: string; label: string; available: boolean; detail: string }[]; warnings: string[];
  snapshot: { snapshot_date: string; total_amount: number; row_count: number } | null;
  actions: { id: string; priority: string; title: string; amount: number; reason: string; href: string }[];
  history: { id: number; scope: string; revision: number; created_by: number; approved_by: number | null; created_at: string; source_note: string }[];
  definitions: Record<string, string>; method_sources: { title: string; url: string }[];
  holoo_snapshot: null | { id: number; captured_at: string; from_date: string; to_date: string; currency_label: string; currency_verified: boolean; finished_at: string; net_profit_available: boolean; limitations: string[]; balances: { source: string; code: string; name: string; balance: number }[]; sources: { kind: string; ok: boolean; complete: boolean; count: number; total_irr: number | null; detail_count: number; duplicate_or_missing_keys: number; valid_amounts: number; warning: string | null }[] };
};
type ProfitResult = { net_sales: number; net_profit: number; profit_change: number; net_margin_percent: number | null; required_sales_at_current_margin: number | null; target_profit: number | null; assumptions: string };
type Tab = "decisions" | "plan" | "excel" | "holoo" | "cash" | "profit" | "growth" | "controls";
const TABS: [Tab, string][] = [["decisions", "تصمیم‌های امروز"], ["plan", "برنامهٔ شرکت"], ["excel", "ورود اکسل"], ["holoo", "دیتای هلو"], ["cash", "نقدینگی و وصول"], ["profit", "سود و بودجه"], ["growth", "رشد و سناریو"], ["controls", "کنترل و سابقه"]];
const AMOUNT_FIELDS = [
  ["revenue", "فروش ناخالص"], ["returns", "برگشت فروش"], ["discounts", "تخفیف فروش"],
  ["cogs", "بهای کالای فروش‌رفته"], ["variable_costs", "هزینهٔ متغیر؛ حمل، پورسانت و مانند آن"],
  ["fixed_costs", "هزینهٔ ثابت؛ حقوق، اجاره و مانند آن"], ["finance_costs", "هزینهٔ مالی"], ["taxes", "مالیات دوره"], ["other_income", "سایر درآمدها"],
] as const;
const RATIO_FIELDS = [["credit_sales", "فروش نسیهٔ ماه"], ["average_receivables", "متوسط مطالبات ماه"], ["average_inventory", "متوسط بهای موجودی ماه"], ["credit_purchases", "خرید نسیهٔ ماه"], ["average_payables", "متوسط بدهی تأمین‌کنندگان ماه"], ["current_assets", "دارایی جاری پایان ماه"], ["current_liabilities", "بدهی جاری پایان ماه"]] as const;
const fa = (value: number, digits = 1) => value.toLocaleString("fa-IR", { maximumFractionDigits: digits });
const cash = (value: number | null | undefined) => value == null ? "دیتا تکمیل نشده" : `${fa(value / 10, 0)} تومان`;
const percent = (value: number | null | undefined) => value == null ? "—" : `${fa(value)}٪`;
const normalized = (text: string) => text.replace(/[۰-۹٠-٩]/g, d => String("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩".indexOf(d) % 10));
const monthLabel = (month: string) => normalized(month).replace("-", "/").replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
function toRials(value: string, optional = false): string | null {
  const text = normalized(value).replace(/[,٬\s]/g, "");
  if (!text && optional) return null;
  if (!/^\d+(?:\.\d)?$/.test(text)) throw new Error("مبلغ تومان باید نامنفی و دارای حداکثر یک رقم اعشار باشد.");
  const [whole, fraction] = text.split(".");
  const amount = BigInt(whole) * BigInt(10) + BigInt(fraction ?? "0");
  if (amount > BigInt("10000000000000000")) throw new Error("مبلغ از سقف ورودی بیشتر است.");
  return amount.toString();
}
const fromRials = (value: unknown) => value == null ? "" : String(Number(value) / 10);
const err = (reason: unknown) => reason instanceof Error ? reason.message : "عملیات انجام نشد.";
function downloadCsv(filename: string, columns: string[], rows: (string | number | null)[][]) {
  const cell = (value: string | number | null) => {
    let text = String(value ?? "");
    if (typeof value === "string" && /^[\s]*[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const blob = new Blob(["\ufeff" + [columns, ...rows].map(row => row.map(cell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob), anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function TreasuryStrategy({ refreshKey = 0 }: { refreshKey?: number }) {
  const [data, setData] = useState<Strategy | null>(null);
  const [tab, setTab] = useState<Tab>("decisions");
  const [error, setError] = useState("");
  const [liveError, setLiveError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [isCeo, setIsCeo] = useState(false);
  const [projection, setProjection] = useState<Projection | null>(null);
  const [cashAssumptions, setCashAssumptions] = useState({ collection_percent: "100", collection_delay_days: "0", extra_outflow: "0", include_recurring: true });
  const [queueFilter, setQueueFilter] = useState("receivable");
  const [queueSearch, setQueueSearch] = useState("");
  const [month, setMonth] = useState("");
  const [kind, setKind] = useState<"actual" | "budget">("actual");
  const [form, setForm] = useState<Record<string, string>>({});
  const [coverageConfirmed, setCoverageConfirmed] = useState(false);
  const [settings, setSettings] = useState({ baseline_month: "", baseline_profit: "", monthly_growth_percent: "20", end_month: "", source_note: "" });
  const [profitMonth, setProfitMonth] = useState("");
  const [profitAssumptions, setProfitAssumptions] = useState({ volume_change_percent: "0", price_change_percent: "0", unit_cost_change_percent: "0", fixed_cost_change_percent: "0" });
  const [profitResult, setProfitResult] = useState<ProfitResult | null>(null);
  const [reconciliation, setReconciliation] = useState<{ difference: number; matched: boolean; recorded_balance: number; statement_balance: number } | null>(null);
  const [bankAccount, setBankAccount] = useState("");
  const [bankBalance, setBankBalance] = useState("");

  const load = useCallback(async () => {
    setError("");
    setLiveError("");
    try {
      const result = await secureApi<Strategy>("/treasury/strategy/overview");
      setData(result); setProjection(null); setProfitResult(null); setReconciliation(null);
      setIsCeo(getSavedUser()?.role === "ceo");
      setSettings({ baseline_month: result.settings.baseline_month ?? "", baseline_profit: fromRials(result.settings.baseline_profit), monthly_growth_percent: String(result.settings.monthly_growth_percent), end_month: result.settings.end_month, source_note: result.settings.source_note });
      setMonth(result.current_month); setKind("actual");
      const report = result.reports.find(r => r.scope === `actual:${result.current_month}`);
      setForm(report ? Object.fromEntries([...AMOUNT_FIELDS, ...RATIO_FIELDS].map(([key]) => [key, fromRials(report.payload[key])]).concat([["source_note", String(report.payload.source_note ?? "")]])) : {});
      setCoverageConfirmed(false);
      const latest = [...result.approved_actuals].sort((a, b) => String(b.payload.month).localeCompare(String(a.payload.month)))[0];
      setProfitMonth(latest ? String(latest.payload.month) : "");
    } catch (reason) { setData(null); setError(err(reason)); }
  }, []);
  useEffect(() => { let active = true; void Promise.resolve().then(() => { if (active) void load(); }); return () => { active = false; }; }, [load, refreshKey]);

  const reloadLive = useCallback(async () => {
    try {
      const result = await secureApi<Strategy>("/treasury/strategy/overview");
      setData(result);
      setLiveError("");
    } catch (reason) {
      setLiveError(reason instanceof ApiError && reason.status === 401
        ? reason.message : "تازه‌سازی خودکار صفحه انجام نشد؛ زمان آخرین دریافت را بررسی کنید.");
    }
  }, []);
  useEffect(() => {
    const timer=setInterval(() => { if(document.visibilityState==="visible"&&!busy)void reloadLive(); },30000);
    return () => clearInterval(timer);
  }, [reloadLive,busy]);

  function selectReport(selectedMonth: string, selectedKind: "actual" | "budget") {
    setMonth(selectedMonth); setKind(selectedKind); setCoverageConfirmed(false);
    const report = data?.reports.find(r => r.scope === `${selectedKind}:${selectedMonth}`);
    setForm(report ? Object.fromEntries([...AMOUNT_FIELDS, ...RATIO_FIELDS].map(([key]) => [key, fromRials(report.payload[key])]).concat([["source_note", String(report.payload.source_note ?? "")]])) : {});
  }
  async function saveMonthly(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const approve = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "approve";
    if (approve && !window.confirm("کامل‌بودن فروش، بهای کالا و همهٔ هزینه‌های این ماه بررسی شده و این نسخه به‌عنوان گزارش واقعی تأیید شود؟")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const normalizedMonth = normalized(month).replace("/", "-");
      const previous = data?.reports.find(r => r.scope === `${kind}:${normalizedMonth}`);
      const amounts = Object.fromEntries(AMOUNT_FIELDS.map(([key]) => [key, toRials(form[key] ?? "")]));
      const optional = Object.fromEntries(RATIO_FIELDS.map(([key]) => [key, toRials(form[key] ?? "", true)]));
      await secureApi("/treasury/strategy/monthly", { method: "POST", body: JSON.stringify({ ...amounts, ...optional, month: normalizedMonth, kind, expected_revision: previous?.revision ?? 0, source_note: form.source_note, coverage_confirmed: coverageConfirmed, approve }) });
      await load(); setMessage(approve ? "نسخهٔ واقعی تأیید شد و در مقایسه با هدف استفاده می‌شود." : "نسخهٔ پیش‌نویس ذخیره شد؛ در سود واقعی تأییدشده منظور نمی‌شود.");
    } catch (reason) { setError(err(reason)); } finally { setBusy(false); }
  }
  async function saveSettings(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await secureApi("/treasury/strategy/settings", { method: "POST", body: JSON.stringify({ ...settings, baseline_month: settings.baseline_month ? normalized(settings.baseline_month).replace("/", "-") : null, baseline_profit: toRials(settings.baseline_profit, true), end_month: normalized(settings.end_month).replace("/", "-"), monthly_growth_percent: Number(normalized(settings.monthly_growth_percent)), expected_revision: data?.settings_revision ?? 0 }) });
      await load(); setMessage("مسیر هدف ذخیره شد؛ این تنظیم هیچ فروش یا پرداختی ثبت نمی‌کند.");
    } catch (reason) { setError(err(reason)); } finally { setBusy(false); }
  }
  async function previewCash(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await secureApi<{ projection: Projection }>("/treasury/strategy/cash-scenario", { method: "POST", body: JSON.stringify({ collection_percent: Number(normalized(cashAssumptions.collection_percent)), collection_delay_days: Number(normalized(cashAssumptions.collection_delay_days)), extra_outflow: toRials(cashAssumptions.extra_outflow), include_recurring: cashAssumptions.include_recurring }) });
      setProjection(result.projection); setMessage("سناریوی فرضی محاسبه شد؛ ماندهٔ حساب‌ها و اسناد تغییر نکردند.");
    } catch (reason) { setError(err(reason)); } finally { setBusy(false); }
  }
  async function previewProfit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await secureApi<{ result: ProfitResult }>("/treasury/strategy/profit-scenario", { method: "POST", body: JSON.stringify({ month: profitMonth, ...Object.fromEntries(Object.entries(profitAssumptions).map(([key, value]) => [key, Number(normalized(value))])) }) });
      setProfitResult(result.result);
    } catch (reason) { setError(err(reason)); } finally { setBusy(false); }
  }
  async function followCollection(row: QueueRow) {
    if (!window.confirm(`برای وصول سند شمارهٔ ${fa(row.id, 0)} به مبلغ ${cash(row.amount)} وظیفه ایجاد شود؟`)) return;
    setBusy(true); setError("");
    try {
      const result = await secureApi<{ task_id: number }>("/treasury/actions/execute", { method: "POST", body: JSON.stringify({ action_type: "collection", title: `وصول سند خزانه ${row.id}: ${row.counterparty}`.slice(0, 200), target_amount: row.amount, customer_id: row.customer_id, reason: `سند خزانه شماره ${row.id} با سررسید ${formatIranDate(row.due_date)}؛ تأخیر ${fa(row.overdue_days, 0)} روز. مبلغ و مسئول پیش از پیگیری بررسی شود.` }) });
      setMessage(`وظیفهٔ شمارهٔ ${fa(result.task_id, 0)} ثبت شد؛ هیچ پیام یا درخواست پرداختی ارسال نشده است.`);
    } catch (reason) { setError(err(reason)); } finally { setBusy(false); }
  }
  async function reconcile(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const signed = normalized(bankBalance).trim();
      const amount = toRials(signed.startsWith("-") ? signed.slice(1) : signed);
      const result = await secureApi<{ difference: number; matched: boolean; recorded_balance: number; statement_balance: number }>("/treasury/strategy/reconciliation-preview", { method: "POST", body: JSON.stringify({ account_id: Number(bankAccount), statement_balance: signed.startsWith("-") ? "-" + amount : amount }) });
      setReconciliation(result);
    } catch (reason) { setError(err(reason)); } finally { setBusy(false); }
  }

  if (!data) return <Surface className="mb-5 p-5"><h2 className="font-bold text-white">مدیریت مالی و رشد</h2><p role="status" className="mt-3 text-sm text-slate-400">{error || "در حال دریافت دیتای خزانه…"}</p>{error && <button onClick={() => void load()} className={`${primaryButton} mt-3`}>تلاش دوباره</button>}</Surface>;
  const currentProjection = projection ?? data.projection;
  const latestActual = [...data.approved_actuals].sort((a, b) => String(b.payload.month).localeCompare(String(a.payload.month)))[0];
  const filteredQueue = data.collections.queue.filter(row => (queueFilter === "all" || row.direction === queueFilter) && matchesSearch(queueSearch,row.counterparty));
  const selectedReport = data.reports.find(r => r.scope === `${kind}:${normalized(month).replace("/", "-")}`);
  const selectedActual = data.approved_actuals.find(r => r.payload.month === normalized(month).replace("/", "-"));
  const selectedBudget = data.reports.find(r => r.scope === `budget:${normalized(month).replace("/", "-")}`);
  const goAction = (href: string) => setTab(href.endsWith("cash") ? "cash" : href.endsWith("profit") ? "profit" : "growth");

  return <section className={styles.root} aria-label="مدیریت مالی و رشد">
    <div className={styles.heading}><div><h2>مدیریت مالی و رشد شرکت</h2><p>مبنای بررسی: {formatIranDate(data.as_of)} · مبالغ این بخش به تومان</p></div><button type="button" onClick={() => void load()} className={styles.secondary}>تازه‌سازی</button></div>
    <p className={styles.help}>دریافت خودکار هلو: {data.holoo_refresh.automatic?.running?`فعال؛ هر ${fa(data.holoo_refresh.automatic.interval_seconds/60,0)} دقیقه`:"فعال نیست"} · آخرین نسخهٔ ذخیره‌شده: {data.holoo_snapshot?formatIranDateTime(data.holoo_snapshot.captured_at):"موجود نیست"} · صفحه هر ۳۰ ثانیه تازه می‌شود. {data.holoo_refresh.status==="running"?"دریافت جدید در حال اجراست.":data.holoo_refresh.status==="failed"||data.holoo_refresh.status==="partial"?"آخرین تلاش کامل نشده؛ اطلاعات قبلی را تازه فرض نکنید.":"دریافت دوره‌ای، نمایش لحظه‌ای تغییرات نیست."}</p>
    <div className={styles.tabs} role="tablist" aria-label="بخش‌های مدیریت مالی">{TABS.map(([key, label]) => <button key={key} id={`financial-tab-${key}`} role="tab" aria-controls={`financial-panel-${key}`} aria-selected={tab === key} onClick={() => setTab(key)} className={tab === key ? styles.active : ""}>{label}</button>)}</div>
    {liveError && <p role="alert" className={styles.error}>{liveError}</p>}
    {(error || message) && <p role={error ? "alert" : "status"} className={error ? styles.error : styles.message}>{error || message}</p>}

    <div role="tabpanel" id={`financial-panel-${tab}`} aria-labelledby={`financial-tab-${tab}`}>
    {tab === "plan" && <TreasuryOperatingPlan key={data.operating_plan_revision} plan={data.operating_plan} revision={data.operating_plan_revision} projection={data.operating_projection} estimate={data.purchase_estimate} initialRefresh={data.holoo_refresh} isCeo={isCeo} reload={reloadLive} />}
    {tab === "excel" && <TreasuryExcel reload={load} estimate={data.excel_estimate} />}
    {tab === "decisions" && <>
      <p className={styles.warning}>ماندهٔ بانک و صندوق، پرداختنی‌ها و چک‌های خرج‌شده هنوز نیازمند به‌روزرسانی و تطبیق‌اند. <button className={styles.secondary} onClick={() => setTab("plan")}>برنامهٔ شرکت با بودجهٔ ماهی ۳۰۰ میلیون تومان</button></p>
      <div className={styles.metrics}>
        <Metric label="وجه پس از ذخیرهٔ حساب‌ها" value={data.projection.cash_accounts_available ? cash(data.projection.opening - data.projection.reserve) : "موجودی ثبت نشده"} />
        <Metric label="بیشترین کسری در ۱۳ هفته" value={data.projection.cash_accounts_available ? cash(data.projection.scenarios.base.shortage) : "نیازمند ماندهٔ حساب"} danger={data.projection.scenarios.base.shortage > 0} />
        <Metric label={latestActual ? `سود خالص تأییدشدهٔ ${monthLabel(String(latestActual.payload.month))}` : "سود خالص تأییدشده"} value={cash(latestActual?.statement.net_profit)} danger={(latestActual?.statement.net_profit ?? 0) < 0} />
        <Metric label="هدف رشد ماهانهٔ سود" value={percent(Number(data.settings.monthly_growth_percent))} note={data.growth.status === "ready" ? "مسیر مرکب با مبنای ثابت" : "ماه و سود مبنا تعیین نشده"} />
      </div>
      <Panel title="اولویت اقدام">{data.actions.length ? <div className={styles.actionGrid}>{data.actions.map(action => <article key={action.id}><span className={action.priority === "high" ? styles.urgent : styles.tag}>{action.priority === "high" ? "اولویت بالا" : "نیازمند بررسی"}</span><h4>{action.title}</h4><strong>{cash(action.amount)}</strong><p>{action.reason}</p><button className={styles.secondary} onClick={() => goAction(action.href)}>بررسی جزئیات و اقدام</button></article>)}</div> : <p className={styles.empty}>با دیتای فعلی اقدامی استخراج نشد. وضعیت منابع پایین را بررسی کنید؛ نبود پیشنهاد نشانهٔ سلامت قطعی مالی نیست.</p>}</Panel>
      <Panel title="کفایت دیتای تصمیم‌گیری"><div className={styles.coverage}>{data.coverage.map(item => <article key={item.id}><b>{item.available ? "● موجود" : "○ نیازمند تکمیل"}</b><h4>{item.label}</h4><p>{item.detail}</p></article>)}</div>{data.warnings.map(warning => <p key={warning} className={styles.warning}>{warning}</p>)}</Panel>
    </>}

    {tab === "holoo" && <>
      <Panel title="دیتای مالی دریافت‌شده از هلو">{data.holoo_snapshot ? <>
        <p className={styles.help}>زمان پایان دریافت: {formatIranDateTime(data.holoo_snapshot.finished_at)} · بازهٔ فاکتورها: {formatIranDate(data.holoo_snapshot.from_date)} تا {formatIranDate(data.holoo_snapshot.to_date)} · واحد منبع: {data.holoo_snapshot.currency_label}{data.holoo_snapshot.currency_verified ? "؛ تأییدشده از تنظیمات هلو" : "؛ تبدیل مبلغ تأیید نشده"}</p>
        <Table headers={["منبع هلو", "تعداد رکورد", "ردیف فاکتور", "جمع مبلغ ثبت‌شده", "وضعیت دریافت"]}>{data.holoo_snapshot.sources.map(source => <tr key={source.kind}><td>{({settings:"تنظیم واحد پول",cash:"صندوق",banks:"ماندهٔ بانک",customers:"اشخاص و مانده‌ها",products:"کالا و قیمت خرید فعلی",purchases:"فاکتور خرید",sales:"فاکتور فروش",purchase_returns:"برگشت از خرید",sales_returns:"برگشت از فروش"} as Record<string,string>)[source.kind] ?? "منبع هلو"}</td><td>{fa(source.count,0)}</td><td>{source.detail_count ? fa(source.detail_count,0) : "—"}</td><td>{source.total_irr == null ? "قابل محاسبه نیست" : cash(source.total_irr)}</td><td>{source.ok && source.complete && !source.duplicate_or_missing_keys ? "دریافت شد" : "نیازمند بررسی"}{source.warning && <small>{source.warning}</small>}</td></tr>)}</Table>
        <p className={styles.warning}>جمع مبالغ فاکتورها، سود خالص نیست. قیمت خرید فعلی، بهای تاریخی فروش نیست و هزینه‌های کامل دوره هنوز متصل نشده‌اند؛ گزارش سود خودکار تأییدشده ساخته نشده است.</p>
      </> : <p className={styles.empty}>هنوز نسخهٔ مالی هلو دریافت نشده است.</p>}</Panel>
      {data.holoo_snapshot && <><Panel title="ماندهٔ بانک و صندوق از هلو"><p className={styles.help}>این مانده‌ها جدا از حساب‌های دستی نمایش داده می‌شوند و با آن‌ها جمع نشده‌اند. مبنای پیش‌بینی ۱۳ هفته‌ای هنوز حساب‌ها و اسناد ثبت‌شدهٔ خزانه است.</p><Table headers={["نوع", "نام سرفصل", "کد سرفصل", "ماندهٔ هلو؛ تومان"]}>{data.holoo_snapshot.balances.map((account,index) => <tr key={`${account.source}-${account.code}-${index}`}><td>{account.source === "banks" ? "بانک" : "صندوق"}</td><td>{account.name}</td><td>{account.code}</td><td>{cash(account.balance)}</td></tr>)}</Table></Panel><Panel title="محدودیت منابع مالی هلو">{data.holoo_snapshot.limitations.map(note => <p className={styles.warning} key={note}>{note}</p>)}</Panel></>}
    </>}

    {tab === "cash" && <div id="treasury-cash">
      <Panel title="برنامهٔ ۱۳ هفته‌ای وجه" action={<button className={styles.secondary} onClick={() => downloadCsv("cash-plan.csv", ["شروع هفته", "پایان هفته", "مانده موردانتظار؛ ریال", "بدون وصول؛ ریال", "سناریو؛ ریال", "کمترین مانده سناریو؛ ریال"], currentProjection.weeks.map(w => [w.start, w.end, w.base, w.no_inflows, w.scenario, w.scenario_minimum]))}>خروجی جدول</button>}>
        <p className={styles.help}>{data.definitions.forecast}</p>
        {!currentProjection.cash_accounts_available && <p className={styles.warning}>ماندهٔ حساب ثبت نشده؛ نمودار فقط اثر اسناد ثبت‌شده را از مبنای صفر نشان می‌دهد و ارزیابی کفایت وجه نیست.</p>}
        <CashChart projection={currentProjection} />
        <div className={styles.metrics}>{([ ["base", "برآورد با احتمال وصول"], ["no_inflows", "بدون دریافت جدید"], ["scenario", "سناریوی انتخابی"] ] as const).map(([key, title]) => <Metric key={key} label={title} value={cash(currentProjection.scenarios[key].closing)} danger={currentProjection.scenarios[key].closing < currentProjection.reserve} note={`کمترین وجه: ${cash(currentProjection.scenarios[key].minimum)}؛ اولین افت از ذخیره: ${currentProjection.scenarios[key].first_shortage ? formatIranDate(currentProjection.scenarios[key].first_shortage!) : "در رکوردهای ثبت‌شده دیده نشد"}`} />)}</div>
        <form onSubmit={previewCash} className={styles.formGrid}>
          <NumberField label="تحقق وصول نسبت به برآورد پایه؛ درصد" value={cashAssumptions.collection_percent} min={0} max={100} onChange={v => { setCashAssumptions({ ...cashAssumptions, collection_percent: v }); setProjection(null); }} />
          <NumberField label="تأخیر وصول؛ روز" value={cashAssumptions.collection_delay_days} min={0} max={90} onChange={v => { setCashAssumptions({ ...cashAssumptions, collection_delay_days: v }); setProjection(null); }} />
          <TextField label="خروج وجه اضافی امروز؛ تومان" value={cashAssumptions.extra_outflow} onChange={v => { setCashAssumptions({ ...cashAssumptions, extra_outflow: v }); setProjection(null); }} numeric />
          <label className={styles.check}><input type="checkbox" checked={cashAssumptions.include_recurring} onChange={e => { setCashAssumptions({ ...cashAssumptions, include_recurring: e.target.checked }); setProjection(null); }} />منظورکردن هزینه‌های ثابت در سناریوی انتخابی</label>
          <div className={styles.buttons}><button disabled={busy} className={primaryButton}>محاسبهٔ سناریو</button><button type="button" onClick={() => { setProjection(null); setCashAssumptions({ collection_percent: "100", collection_delay_days: "0", extra_outflow: "0", include_recurring: true }); }} className={styles.secondary}>بازگشت به مبنا</button></div>
        </form>
        <details><summary>جدول ماندهٔ پایان هفته و کف وجه</summary><Table headers={["هفته", "پایه", "بدون وصول", "سناریو", "کف وجه سناریو"]}>{currentProjection.weeks.map(w => <tr key={w.start}><td>{formatIranDate(w.start)}</td><td>{cash(w.base)}</td><td>{cash(w.no_inflows)}</td><td>{cash(w.scenario)}</td><td>{cash(w.scenario_minimum)}</td></tr>)}</Table></details>
      </Panel>
      <Panel title="سن مطالبات و تعهدات ثبت‌شده"><Table headers={["وضعیت سررسید", "دریافتنی", "پرداختنی", "تعداد سند"]}>{data.collections.aging.map(b => <tr key={b.id}><td>{b.label}</td><td>{cash(b.receivable)}</td><td>{cash(b.payable)}</td><td>{fa(b.count, 0)}</td></tr>)}</Table></Panel>
      <Panel title="صف وصول و پرداخت" action={<button className={styles.secondary} onClick={() => downloadCsv("treasury-queue.csv", ["شماره سند", "طرف حساب", "جهت", "مبلغ؛ ریال", "سررسید میلادی", "روز تأخیر", "وضعیت"], filteredQueue.map(r => [r.id, r.counterparty, r.direction === "receivable" ? "دریافتنی" : "پرداختنی", r.amount, r.due_date, r.overdue_days, r.status]))}>خروجی موارد فیلترشده</button>}>
        <div className={styles.inline}><label>نوع<select value={queueFilter} onChange={e => setQueueFilter(e.target.value)} className={fieldClass}><option value="receivable">دریافتنی</option><option value="payable">پرداختنی</option><option value="all">هر دو</option></select></label><TextField label="جست‌وجوی طرف حساب" value={queueSearch} onChange={setQueueSearch} /></div>
        <Table headers={["طرف حساب و سند", "مبلغ", "سررسید", "روز تأخیر", "وضعیت", "پیگیری"]}>{filteredQueue.map(row => <tr key={row.id}><td>{row.counterparty}<small>سند {fa(row.id, 0)}</small></td><td>{cash(row.amount)}</td><td>{formatIranDate(row.due_date)}</td><td>{fa(row.overdue_days, 0)}</td><td>{row.bounced ? "برگشتی" : row.overdue_days ? "سررسیدگذشته" : "باز"}</td><td>{row.direction === "receivable" && isCeo ? <button disabled={busy} className={styles.secondary} onClick={() => void followCollection(row)}>ثبت وظیفهٔ وصول</button> : "—"}</td></tr>)}</Table>{!filteredQueue.length && <p className={styles.empty}>سندی با این فیلتر ثبت نشده است.</p>}
      </Panel>
      <Panel title="تمرکز ماندهٔ دریافتنی‌ها"><p className={styles.help}>سهم پنج طرف حساب بزرگ از اسناد دریافتنی باز: {percent(data.collections.top_five_share_percent)}. این سهم، احتمال نکول نیست.</p><Table headers={["طرف حساب", "ماندهٔ اسناد", "سررسیدگذشته", "سهم"]}>{data.collections.concentration.slice(0, 10).map((row, index) => <tr key={index}><td>{row.counterparty}</td><td>{cash(row.balance)}</td><td>{cash(row.overdue)}</td><td>{percent(row.share_percent)}</td></tr>)}</Table>{data.snapshot && <p className={styles.warning}>گزارش جداگانهٔ مانده بدهکاران در {formatIranDate(data.snapshot.snapshot_date)}: {cash(data.snapshot.total_amount)}. به‌دلیل احتمال همپوشانی، با ماندهٔ اسناد جمع نشده و در پیش‌بینی وصول منظور نشده است.</p>}</Panel>
    </div>}

    {tab === "profit" && <div id="treasury-profit">
      <Panel title="صورت سود و زیان و بودجهٔ ماهانه">
        <p className={styles.help}>{data.definitions.net_profit} همهٔ هزینه‌ها را بدون همپوشانی دسته‌بندی کنید؛ مثلاً حقوق ثابت در هزینهٔ ثابت و پورسانت در هزینهٔ متغیر.</p>
        <div className={styles.inline}><TextField label="ماه شمسی" value={month} onChange={v => selectReport(normalized(v).replace("/", "-"), kind)} placeholder="۱۴۰۵-۰۶" /><label>نوع گزارش<select value={kind} onChange={e => selectReport(month, e.target.value as "actual" | "budget")} className={fieldClass}><option value="actual">عملکرد واقعی</option><option value="budget">بودجهٔ پیشنهادی</option></select></label><span className={styles.tag}>{selectedReport ? `نسخهٔ ${fa(selectedReport.revision, 0)} · ${selectedReport.approved_by ? "تأییدشده" : "پیش‌نویس"}` : "گزارش جدید"}</span></div>
        {selectedReport && <div className={styles.metrics}><Metric label="فروش خالص" value={cash(selectedReport.statement.net_sales)} /><Metric label="سود ناخالص" value={cash(selectedReport.statement.gross_profit)} /><Metric label="سود خالص این نسخه" value={cash(selectedReport.statement.net_profit)} note={selectedReport.approved_by ? "واقعی تأییدشده" : "پیش‌نویس؛ خارج از تحقق هدف"} /><Metric label="حاشیهٔ سود خالص" value={percent(selectedReport.statement.net_margin_percent)} /></div>}
        <form onSubmit={saveMonthly}>
          <div className={styles.formGrid}>{AMOUNT_FIELDS.map(([key, label]) => <TextField key={key} label={`${label}؛ تومان`} value={form[key] ?? ""} onChange={v => setForm({ ...form, [key]: v })} numeric required />)}</div>
          <details><summary>اطلاعات اختیاری سرمایهٔ در گردش و نسبت‌ها</summary><p className={styles.help}>متوسط مانده‌ها را از ابتدا و انتهای همان ماه محاسبه کنید. فیلد خالی به معنی نامشخص است.</p><div className={styles.formGrid}>{RATIO_FIELDS.map(([key, label]) => <TextField key={key} label={`${label}؛ تومان`} value={form[key] ?? ""} onChange={v => setForm({ ...form, [key]: v })} numeric />)}</div></details>
          <label className={styles.textarea}>منبع اعداد و دلیل ثبت یا اصلاح<textarea required minLength={8} maxLength={2000} value={form.source_note ?? ""} onChange={e => setForm({ ...form, source_note: e.target.value })} className={fieldClass} placeholder="نام گزارش هلو، دوره، منبع هزینه‌ها و دلیل اصلاح" /></label>
          {kind === "actual" && <label className={styles.check}><input type="checkbox" checked={coverageConfirmed} onChange={e => setCoverageConfirmed(e.target.checked)} />همهٔ فروش‌ها، برگشت‌ها، بهای کالا و هزینه‌های این ماه را تطبیق داده‌ام.</label>}
          <div className={styles.buttons}><button disabled={busy} value="draft" className={styles.secondary}>ذخیرهٔ نسخهٔ پیش‌نویس</button>{isCeo && kind === "actual" && <button disabled={busy || !coverageConfirmed || month >= data.current_month} value="approve" className={primaryButton}>تأیید نهایی عملکرد ماه کامل</button>}</div><p className={styles.help}>ماه جاری و آینده فقط پیش‌نویس می‌شوند. اصلاح هر گزارش نسخهٔ تازه می‌سازد و نسخهٔ قبلی حفظ می‌شود.</p>
        </form>
      </Panel>
      {selectedActual && <Panel title="شاخص‌های عملکرد تأییدشده"><div className={styles.metrics}><Metric label="نقطهٔ سربه‌سر فروش عملیاتی" value={cash(selectedActual.statement.break_even_sales)} /><Metric label="روزهای وصول مطالبات" value={selectedActual.statement.dso == null ? "دیتا تکمیل نشده" : `${fa(selectedActual.statement.dso)} روز`} /><Metric label="روزهای ماندگاری موجودی" value={selectedActual.statement.dio == null ? "دیتا تکمیل نشده" : `${fa(selectedActual.statement.dio)} روز`} /><Metric label="چرخهٔ تبدیل وجه" value={selectedActual.statement.cash_conversion_days == null ? "دیتا تکمیل نشده" : `${fa(selectedActual.statement.cash_conversion_days)} روز`} /><Metric label="روزهای پرداخت تأمین‌کننده" value={selectedActual.statement.dpo == null ? "دیتا تکمیل نشده" : `${fa(selectedActual.statement.dpo)} روز`} /><Metric label="نسبت جاری" value={selectedActual.statement.current_ratio == null ? "دیتا تکمیل نشده" : fa(selectedActual.statement.current_ratio, 2)} /></div><p className={styles.help}>{data.definitions.break_even} {data.definitions.cash_cycle}</p></Panel>}
      <Panel title="مقایسهٔ بودجه با عملکرد همان ماه">{selectedActual && selectedBudget ? <><p className={styles.help}>عملکرد تأییدشدهٔ نسخهٔ {fa(selectedActual.revision, 0)} در برابر بودجهٔ پیشنهادی نسخهٔ {fa(selectedBudget.revision, 0)}؛ انحراف، واقعی منهای بودجه است.</p><Table headers={["سرفصل", "بودجه", "واقعی", "انحراف"]}>{[...AMOUNT_FIELDS.map(([key, label]) => [label, Number(selectedBudget.payload[key]), Number(selectedActual.payload[key])] as const), ["سود خالص", selectedBudget.statement.net_profit, selectedActual.statement.net_profit] as const].map(([label, budget, actual]) => <tr key={label}><td>{label}</td><td>{cash(budget)}</td><td>{cash(actual)}</td><td>{cash(actual - budget)}</td></tr>)}</Table></> : <p className={styles.empty}>برای مقایسه، بودجه و عملکرد تأییدشدهٔ همین ماه لازم است.</p>}</Panel>
      <Panel title="روند سود و حاشیهٔ سود تأییدشده"><Table headers={["ماه", "فروش خالص", "سود ناخالص", "سود خالص", "حاشیهٔ خالص"]}>{[...data.approved_actuals].sort((a, b) => String(a.payload.month).localeCompare(String(b.payload.month))).map(r => <tr key={r.id}><td>{monthLabel(String(r.payload.month))}</td><td>{cash(r.statement.net_sales)}</td><td>{cash(r.statement.gross_profit)}</td><td>{cash(r.statement.net_profit)}</td><td>{percent(r.statement.net_margin_percent)}</td></tr>)}</Table>{!data.approved_actuals.length && <p className={styles.empty}>هنوز صورت سود و زیان تأییدشده‌ای ثبت نشده است.</p>}</Panel>
    </div>}

    {tab === "growth" && <div id="treasury-growth">
      <Panel title="مسیر رشد ماهانهٔ سود"><p className={styles.help}>{data.definitions.growth} این هدف تعهد به تحقق یا پیش‌بینی قطعی نیست.</p>
        {data.growth.status === "ready" ? <><GrowthChart rows={data.growth.rows} /><Table headers={["ماه", "سود هدف", "سود واقعی تأییدشده", "فاصله تا هدف", "تحقق"]}>{data.growth.rows.map(r => <tr key={r.month}><td>{monthLabel(r.month)}</td><td>{cash(r.target)}</td><td>{cash(r.actual)}</td><td>{cash(r.gap)}</td><td>{percent(r.attainment_percent)}</td></tr>)}</Table></> : <p className={styles.warning}>{data.growth.status === "positive_baseline_required" ? "سود مبنا صفر یا منفی است؛ ابتدا برنامهٔ خروج از زیان و هدف مبلغی تعیین کنید." : "برای تعیین مبالغ هدف، ماه کامل‌شده و سود مثبت مبنا را مشخص کنید. نرخ ۲۰ درصد از خواستهٔ شماست؛ سود مبنا حدس زده نشده است."}</p>}
        {isCeo && <details><summary>تعریف یا اصلاح هدف رشد</summary><form onSubmit={saveSettings}><div className={styles.formGrid}><TextField label="ماه کامل‌شدهٔ مبنا؛ شمسی" value={settings.baseline_month} onChange={v => setSettings({ ...settings, baseline_month: v })} placeholder="۱۴۰۵-۰۶" required /><TextField label="سود خالص مبنا؛ تومان" value={settings.baseline_profit} onChange={v => setSettings({ ...settings, baseline_profit: v })} numeric /><NumberField label="رشد هدف هر ماه؛ درصد" value={settings.monthly_growth_percent} min={0} max={100} onChange={v => setSettings({ ...settings, monthly_growth_percent: v })} /><TextField label="ماه پایان؛ شمسی" value={settings.end_month} onChange={v => setSettings({ ...settings, end_month: v })} required /></div><p className={styles.help}>اگر مبلغ مبنا خالی باشد، از آخرین نسخهٔ واقعی تأییدشدهٔ آن ماه گرفته و برای این مسیر ثابت نگه داشته می‌شود.</p><TextField label="منبع مبنا و دلیل تغییر هدف" value={settings.source_note} onChange={v => setSettings({ ...settings, source_note: v })} required /><button disabled={busy} className={`${primaryButton} mt-3`}>ذخیرهٔ مسیر هدف</button></form></details>}
      </Panel>
      <Panel title="اگر حجم، قیمت یا هزینه تغییر کند؟"><p className={styles.help}>سناریو از یک ماه واقعی تأییدشده ساخته می‌شود. اثر افزایش قیمت بر تقاضا و هزینه‌های ظرفیت باید جداگانه بررسی شود.</p>
        <form onSubmit={previewProfit}><label>ماه واقعی مبنا<select required value={profitMonth} onChange={e => { setProfitMonth(e.target.value); setProfitResult(null); }} className={fieldClass}><option value="">انتخاب ماه</option>{data.approved_actuals.map(r => <option key={r.id} value={String(r.payload.month)}>{monthLabel(String(r.payload.month))}</option>)}</select></label><div className={styles.formGrid}>{([ ["volume_change_percent", "تغییر حجم فروش؛ درصد"], ["price_change_percent", "تغییر قیمت فروش؛ درصد"], ["unit_cost_change_percent", "تغییر بهای خرید هر واحد؛ درصد"], ["fixed_cost_change_percent", "تغییر هزینهٔ ثابت؛ درصد"] ] as const).map(([key, label]) => <NumberField key={key} label={label} min={-100} max={300} value={profitAssumptions[key]} onChange={v => { setProfitAssumptions({ ...profitAssumptions, [key]: v }); setProfitResult(null); }} />)}</div><div className={styles.buttons}><button disabled={busy || !profitMonth} className={primaryButton}>محاسبهٔ اثر بر سود</button><button type="button" className={styles.secondary} onClick={() => { setProfitAssumptions({ volume_change_percent: "0", price_change_percent: "0", unit_cost_change_percent: "0", fixed_cost_change_percent: "0" }); setProfitResult(null); }}>پاک‌کردن سناریو</button></div></form>
        {profitResult && <><div className={styles.metrics}><Metric label="فروش خالص سناریو" value={cash(profitResult.net_sales)} /><Metric label="سود خالص سناریو" value={cash(profitResult.net_profit)} danger={profitResult.net_profit < 0} /><Metric label="تغییر سود نسبت به مبنا" value={cash(profitResult.profit_change)} danger={profitResult.profit_change < 0} /><Metric label="فروش لازم برای سود هدف ماه بعد" value={cash(profitResult.required_sales_at_current_margin)} note="با حاشیهٔ مشارکت و هزینه‌های ماه مبنا" /></div><p className={styles.help}>{profitResult.assumptions}</p></>}
      </Panel>
    </div>}

    {tab === "controls" && <>
      <Panel title="تطبیق مانده با صورت‌حساب بانک"><p className={styles.help}>ماندهٔ صورت‌حساب بانک را در همان زمان ماندهٔ ثبت‌شده وارد کنید. اختلاف، صورت‌حساب منهای داشبورد است؛ این مقایسه مانده یا سند مالی را تغییر نمی‌دهد.</p><form onSubmit={reconcile}><div className={styles.formGrid}><label>حساب<select required value={bankAccount} onChange={e => { setBankAccount(e.target.value); setReconciliation(null); }} className={fieldClass}><option value="">انتخاب حساب</option>{data.accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label><TextField numeric required label="ماندهٔ صورت‌حساب؛ تومان" value={bankBalance} onChange={v => { setBankBalance(v); setReconciliation(null); }} /></div><button disabled={busy || !bankAccount} className={primaryButton}>بررسی اختلاف</button></form>{reconciliation && <><div className={styles.metrics}><Metric label="ماندهٔ ثبت‌شده" value={cash(reconciliation.recorded_balance)} /><Metric label="ماندهٔ صورت‌حساب واردشده" value={cash(reconciliation.statement_balance)} /><Metric label="اختلاف مانده" value={cash(reconciliation.difference)} danger={!reconciliation.matched} /></div><p className={reconciliation.matched ? styles.message : styles.warning}>{reconciliation.matched ? "دو مانده برابرند؛ این برابری به‌تنهایی تأیید ریز تراکنش‌ها نیست." : "مغایرت وجود دارد؛ کارمزدها، واریزهای در راه، چک‌های وصول‌شده و پرداخت‌های ثبت‌نشده بررسی شوند."}</p></>}</Panel>
      <Panel title="کنترل منابع و محاسبات"><div className={styles.coverage}>{data.coverage.map(item => <article key={item.id}><b>{item.available ? "موجود" : "نیازمند تکمیل"}</b><h4>{item.label}</h4><p>{item.detail}</p></article>)}</div>{data.warnings.map(w => <p className={styles.warning} key={w}>{w}</p>)}<dl className={styles.definitions}>{Object.entries(data.definitions).map(([key, value]) => <div key={key}><dt>{({ net_profit: "سود خالص", break_even: "سربه‌سر عملیاتی", cash_cycle: "سرمایهٔ در گردش", forecast: "پیش‌بینی وجه", growth: "رشد سود" } as Record<string, string>)[key]}</dt><dd>{value}</dd></div>)}</dl><p className={styles.help}>تسویهٔ سند، خودش ماندهٔ بانک را جابه‌جا نمی‌کند؛ مانده باید جدا با صورت‌حساب تطبیق داده شود. گزارش ماهانه به‌صورت خلاصه ثبت می‌شود و جای دفتر حسابداری را نمی‌گیرد.</p></Panel>
      <Panel title="سابقهٔ نسخه‌های مالی و تأییدها"><Table headers={["موضوع", "نسخه", "ثبت‌کننده", "تأیید", "زمان تهران", "منبع و دلیل"]}>{data.history.map(h => <tr key={h.id}><td>{h.scope === "settings" ? "هدف رشد" : h.scope === "operating-plan" ? "بودجه و وضعیت منابع شرکت" : `${h.scope.startsWith("actual:") ? "عملکرد" : "بودجه"} ${monthLabel(h.scope.split(":")[1] ?? "")}`}</td><td>{fa(h.revision, 0)}</td><td>کاربر {fa(h.created_by, 0)}</td><td>{h.approved_by ? `مدیر ${fa(h.approved_by, 0)}` : "پیش‌نویس"}</td><td>{formatIranDateTime(h.created_at)}</td><td>{h.source_note}</td></tr>)}</Table>{!data.history.length && <p className={styles.empty}>هنوز نسخه‌ای ثبت نشده است.</p>}<p className={styles.help}>۴۰ ثبت اخیر؛ نسخه‌های قبلی در پایگاه‌داده حفظ می‌شوند. تأیید واقعی فقط برای مدیرعامل فعال است.</p></Panel>
      <Panel title="راهنمای روش مالی"><ul>{data.method_sources.map(s => <li key={s.url}><a className="text-cyan-300 underline" href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}</ul><p className={styles.help}>این منابع روش عمومی را توضیح می‌دهند؛ اعداد شرکت از رکوردهای داخلی و گزارش‌های دارای منبع می‌آیند.</p></Panel>
    </>}
    </div>
  </section>;
}

function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) { return <Surface className={styles.panel}><header><h3>{title}</h3>{action}</header>{children}</Surface>; }
function Metric({ label, value, note, danger = false }: { label: string; value: string; note?: string; danger?: boolean }) { return <article className={styles.metric}><span>{label}</span><strong className={danger ? styles.negative : ""}>{value}</strong>{note && <small>{note}</small>}</article>; }
function TextField({ label, value, onChange, required, numeric, placeholder }: { label: string; value: string; onChange: (value: string) => void; required?: boolean; numeric?: boolean; placeholder?: string }) { return <label className={styles.field}>{label}<input value={value} onChange={e => onChange(e.target.value)} required={required} inputMode={numeric ? "numeric" : undefined} placeholder={placeholder} className={fieldClass} dir={numeric ? "ltr" : undefined} /></label>; }
function NumberField({ label, value, onChange, min, max }: { label: string; value: string; onChange: (value: string) => void; min: number; max: number }) { return <label className={styles.field}>{label}<input type="number" required step="any" value={value} min={min} max={max} onChange={e => onChange(e.target.value)} className={fieldClass} dir="ltr" /></label>; }
function Table({ headers, children }: { headers: string[]; children: ReactNode }) { return <div className={styles.tableWrap} tabIndex={0}><table><thead><tr>{headers.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>; }

function CashChart({ projection }: { projection: Projection }) {
  const values = projection.weeks.flatMap(w => [w.base, w.no_inflows, w.scenario]);
  const low = Math.min(0, ...values), high = Math.max(1, projection.reserve, ...values), range = high - low;
  const y = (value: number) => 18 + (high - value) / range * 184;
  const x = (index: number) => 85 + index / Math.max(1, projection.weeks.length - 1) * 660;
  const colors = { base: "#67e8f9", no_inflows: "#fda4af", scenario: "#c4b5fd" };
  return <div className={styles.chart}><svg viewBox="0 0 780 250" role="img" aria-label="ماندهٔ پایان هفته برای برآورد پایه، بدون وصول و سناریوی انتخابی"><title>برنامهٔ وجه ۱۳ هفته</title>{[high, (high + low) / 2, low].map((v, index) => <g key={index}><line x1="80" x2="750" y1={y(v)} y2={y(v)} stroke="#334155" strokeDasharray="3 6" /><text x="72" y={y(v) + 4} textAnchor="end">{fa(v / 10000000)} م</text></g>)}<line x1="80" x2="750" y1={y(0)} y2={y(0)} stroke="#94a3b8" /><line x1="80" x2="750" y1={y(projection.reserve)} y2={y(projection.reserve)} stroke="#fbbf24" strokeDasharray="5 5" />{(["base", "no_inflows", "scenario"] as const).map(key => <polyline key={key} points={projection.weeks.map((w, i) => `${x(i)},${y(w[key])}`).join(" ")} fill="none" stroke={colors[key]} strokeWidth="2.5" />)}{projection.weeks.map((w, i) => <g key={w.start}><circle cx={x(i)} cy={y(w.scenario)} r="4" fill={colors.scenario}><title>{formatIranDate(w.start)}: {cash(w.scenario)}</title></circle>{i % 3 === 0 && <text x={x(i)} y="230" textAnchor="middle">هفتهٔ {fa(i + 1, 0)}</text>}</g>)}</svg><div className={styles.legend}><span style={{ color: colors.base }}>● برآورد پایه</span><span style={{ color: colors.no_inflows }}>● بدون وصول</span><span style={{ color: colors.scenario }}>● سناریو</span><span className="text-amber-300">― ذخیرهٔ حساب‌ها</span><span>محور عمودی: میلیون تومان</span></div></div>;
}
function GrowthChart({ rows }: { rows: GrowthRow[] }) {
  const max = Math.max(1, ...rows.flatMap(r => [r.target, r.actual ?? 0])), min = Math.min(0, ...rows.map(r => r.actual ?? 0));
  const y = (value: number) => 20 + (max - value) / (max - min) * 160;
  const x = (i: number) => 85 + i / Math.max(1, rows.length - 1) * 650;
  return <div className={styles.chart}><svg viewBox="0 0 780 220" role="img" aria-label="مقایسهٔ مسیر سود هدف با سود واقعی تأییدشده"><title>هدف و عملکرد سود</title><line x1="80" x2="750" y1={y(0)} y2={y(0)} stroke="#64748b" /><text x="70" y="24" textAnchor="end">{fa(max / 10000000)} م</text><text x="70" y={y(0) + 4} textAnchor="end">۰</text><polyline points={rows.map((r, i) => `${x(i)},${y(r.target)}`).join(" ")} fill="none" stroke="#c4b5fd" strokeWidth="3" />{rows.map((r, i) => <g key={r.month}><circle cx={x(i)} cy={y(r.target)} r="4" fill="#c4b5fd"><title>{monthLabel(r.month)} هدف: {cash(r.target)}</title></circle>{r.actual !== null && <circle cx={x(i)} cy={y(r.actual)} r="5" fill="#67e8f9"><title>واقعی: {cash(r.actual)}</title></circle>}{(rows.length < 13 || i % 2 === 0) && <text x={x(i)} y="207" textAnchor="middle">{monthLabel(r.month)}</text>}</g>)}</svg><div className={styles.legend}><span className="text-violet-300">● سود هدف</span><span className="text-cyan-300">● واقعی تأییدشده</span><span>میلیون تومان؛ ماه فاقد گزارش، نقطهٔ واقعی ندارد</span></div></div>;
}
