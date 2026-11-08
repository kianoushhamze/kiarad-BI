"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Surface, fieldClass, primaryButton } from "./portal-shell";
import { secureApi } from "../lib/secure-api";
import { formatIranDate, formatIranDateTime } from "../lib/iran-date";
import styles from "./treasury-strategy.module.css";

export type OperatingPlan = { monthly_expense_irr: string | number; balance_source?: "holoo" | "excel"; bank_balances_current: boolean; receivable_checks_current: boolean; payable_checks_current: boolean; endorsed_checks_current: boolean; checks_registry_complete: boolean; source_note: string };
export type OperatingProjection = {
  start: string; end: string; opening_balance_irr: number | null; health_confirmed: boolean;
  readiness: { complete: boolean; sources: { key: string; label: string; ready: boolean; evidence: string }[] };
  totals: { minimum_balance_irr: number | null; required_extra_collections_irr: number | null; first_shortage: string | null };
  months: { month: string; days_in_horizon: number; period_expense_budget_irr: number; operating_envelope_outflow_irr: number; payable_outflow_irr: number; expected_receipts_irr: number; closing_balance_irr: number | null; required_extra_collections_irr: number | null }[];
  warnings: string[]; methods: string[];
};
export type PurchaseEstimate = {
  status: string; limitations: string[]; blockers: { code: string; reason: string; month?: string }[];
  months: { month: string; partial_month: boolean; covered_days: number; days_in_month: number; net_sales_irr: number | null; sales_discount_irr: number | null; purchase_discount_irr: number | null; purchase_net_irr: number | null; budget_expense_for_period_irr: number; estimated_cogs_irr: number | null; estimated_net_profit_irr: number | null; estimated_profit_before_unverified_purchase_tax_irr: number | null; sales_lines: number; costed_sales_lines: number; blockers: { code: string; reason: string }[] }[];
};
export type RefreshStatus = { automatic?: {enabled:boolean;running:boolean;interval_seconds:number;next_attempt_at:string|null}; status: string; sources: { kind: string; count: number; ok: boolean; complete: boolean }[]; finished_at?: string; message?: string; snapshot_id?: number | null };

const fa = (n: number) => n.toLocaleString("fa-IR", { maximumFractionDigits: 0 });
const cash = (n: number | null | undefined) => n == null ? "نیازمند تکمیل دیتا" : `${fa(n / 10)} تومان`;
const monthLabel = (s: string) => s.replace("-", "/").replace(/\d/g, d => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const FLAGS = [["bank_balances_current", "بانک و صندوق در هلو اصلاح و تطبیق شدند"], ["receivable_checks_current", "چک‌های دریافتنی در هلو به‌روزند"], ["payable_checks_current", "چک‌های پرداختنی در هلو به‌روزند"], ["endorsed_checks_current", "چک‌های خرج‌شده به تأمین‌کنندگان در هلو به‌روزند"]] as const;

export function TreasuryOperatingPlan({ plan, revision, projection, estimate, initialRefresh, isCeo, reload }: { plan: OperatingPlan; revision: number; projection: OperatingProjection; estimate: PurchaseEstimate | null; initialRefresh: RefreshStatus; isCeo: boolean; reload: () => Promise<void> }) {
  const [form, setForm] = useState(plan);
  const [expense, setExpense] = useState(String(Number(plan.monthly_expense_irr) / 10));
  const [status, setStatus] = useState(initialRefresh);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await secureApi<RefreshStatus>("/treasury/strategy/holoo-refresh");
        if (!active) return;
        setStatus(next);
        if (next.status === "running") timer = setTimeout(() => void poll(), 3000);
        else { if(next.snapshot_id&&next.snapshot_id!==initialRefresh.snapshot_id)await reload(); if (active&&status.status==="running") setMessage(next.status === "completed" ? "دیتای هلو دوباره دریافت شد. تأیید اصلاح اطلاعات در هلو را جدا بررسی و ذخیره کنید." : "دریافت کامل نشده؛ وضعیت منابع و اتصال هلو را بررسی کنید."); timer=setTimeout(()=>void poll(),10000); }
      } catch { if (active) { setError("وضعیت دریافت در دسترس نیست؛ تازه‌سازی صفحه را بزنید. دریافت ممکن است در سرور ادامه داشته باشد."); setStatus(s => ({ ...s, status: "unknown" })); } }
    };
    timer = setTimeout(() => void poll(), 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [status.status, reload, initialRefresh.snapshot_id]);

  async function refresh() {
    setBusy(true); setError(""); setMessage("");
    try { setStatus(await secureApi<RefreshStatus>("/treasury/strategy/holoo-refresh", { method: "POST" })); }
    catch { setError("شروع دریافت هلو ممکن نشد؛ اتصال یا مجوز خزانه را بررسی کنید."); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const normalized = expense.replace(/[۰-۹٠-٩]/g, d => String("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩".indexOf(d) % 10)).replace(/[,٬\s]/g, "");
      if (!/^\d+$/.test(normalized)) throw new Error("بودجه را به تومان صحیح و نامنفی وارد کنید.");
      const amount = BigInt(normalized) * BigInt(10);
      if (amount > BigInt("10000000000000000")) throw new Error("بودجه از سقف ورودی بیشتر است.");
      const flags = Object.fromEntries(FLAGS.map(([key]) => [key, form[key]]));
      await secureApi("/treasury/strategy/operating-plan", { method: "POST", body: JSON.stringify({ ...flags, balance_source: form.balance_source ?? "holoo", source_note: form.source_note, monthly_expense_irr: amount.toString(), expected_revision: revision }) });
      await reload(); setMessage("بودجه و اعلام وضعیت منابع نسخه‌بندی شد؛ این کار گزارش سود یا کفایت وجه را تأیید نمی‌کند.");
    } catch (e) { setError(e instanceof Error ? e.message : "ذخیره انجام نشد."); }
    finally { setBusy(false); }
  }
  return <>
    {(error || message) && <p role={error ? "alert" : "status"} className={error ? styles.error : styles.message}>{error || message}</p>}
    <Surface className={styles.panel}><header><h3>بودجهٔ شرکت و آمادگی منابع هلو</h3><button className={primaryButton} disabled={busy || status.status === "running"} onClick={() => void refresh()}>{status.status === "running" ? "در حال دریافت هلو…" : "دریافت تازه از هلو"}</button></header>
      <p className={styles.help}>اطلاعات به‌صورت دوره‌ای از هلو دریافت می‌شوند؛ پس از اصلاح اطلاعات می‌توانید دریافت تازه را هم بزنید. تأیید تطبیق منابع همچنان جداست. دریافت فاکتور، بانک و صندوق فقط خواندنی است. فهرست کامل چک‌ها در رابط فعلی هلو موجود نیست؛ اصلاح چک‌ها به‌تنهایی ریز سررسیدها را به این صفحه نمی‌آورد.</p>
      {status.status === "running" && <p role="status" className={styles.warning}>دریافت در پس‌زمینه ادامه دارد؛ {fa(status.sources.length)} منبع تا اینجا بررسی شده است. بستن این صفحه، فرایند روی سرور را قطع نمی‌کند.</p>}
      {status.finished_at && <p className={styles.help}>آخرین پایان دریافت: {formatIranDateTime(status.finished_at)} · {status.status === "completed" ? "پاسخ منابع کامل بود" : "نیازمند بررسی منابع"}</p>}
      <div className={styles.coverage}>{projection.readiness.sources.map(s => <article key={s.key}><b>{s.ready ? "اعلام به‌روزبودن موجود است" : "نیازمند تکمیل"}</b><h4>{s.label}</h4><p>{s.evidence}</p></article>)}</div>
      {isCeo && <details><summary>اصلاح بودجه و تأیید وضعیت اطلاعات</summary><form onSubmit={save}>
        <label className={styles.field}>مبنای ماندهٔ برنامهٔ وجه<select value={form.balance_source ?? "holoo"} onChange={e => setForm({ ...form, balance_source: e.target.value as "holoo" | "excel", bank_balances_current: false })} className={fieldClass}><option value="holoo">آخرین ماندهٔ هلو</option><option value="excel">آخرین گزارش حساب و موجودیِ ثبت‌شده از اکسل</option></select></label>
        <label className={styles.field}>مجموع هزینهٔ ثابت و متغیر یک ماه کامل؛ تومان<input className={fieldClass} required inputMode="numeric" value={expense} onChange={e => setExpense(e.target.value)} /></label>
        <p className={styles.help}>مبنای توافق‌شده: ماهی ۳۰۰ میلیون تومان. حقوق، پورسانت و هزینهٔ ثابت داخل این مجموع‌اند. بهای کالای فروش‌رفته جداست؛ مالیات و هزینهٔ مالی نامشخص، صفر فرض نمی‌شوند. این بودجه جای عملکرد واقعی را نمی‌گیرد.</p>
        {FLAGS.map(([key, label]) => <label className={styles.check} key={key}><input type="checkbox" checked={form[key]} onChange={e => setForm({ ...form, [key]: e.target.checked })} />{label}</label>)}
        <label className={styles.textarea}>منبع بودجه، تاریخ اصلاح هلو و توضیح تأیید<textarea required minLength={8} maxLength={2000} value={form.source_note} onChange={e => setForm({ ...form, source_note: e.target.value })} className={fieldClass} /></label>
        <button className={`${primaryButton} mt-3`} disabled={busy}>ذخیرهٔ نسخهٔ بودجه و وضعیت</button>
      </form></details>}
    </Surface>
    <Surface className={styles.panel}><header><h3>اثر تخفیف و افر در خرید و فروش</h3></header><p className={styles.help}>تخفیف خرید، بهای موجودی را کاهش می‌دهد. هدیهٔ هم‌کالا در تعداد خرید منظور می‌شود و هدیهٔ فروش هزینه دارد. درصد ردیف و تخفیف سربرگ پس از تطبیق، یک‌بار کسر می‌شوند؛ خریدِ ماه به‌جای بهای فروش‌رفته قرار نمی‌گیرد.</p>
      {estimate ? <><div className={styles.tableWrap} tabIndex={0}><table><thead><tr>{["ماه و پوشش", "تخفیف خرید", "خرید پس از تخفیف", "تخفیف فروش", "فروش خالص پس از برگشت", "پوشش بهای ردیف فروش", "بهای برآوردی", "بودجهٔ هزینهٔ بازه", "برآورد پس از بودجه"].map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{estimate.months.map(m => <tr key={m.month}><td>{monthLabel(m.month)}<small>{fa(m.covered_days)} از {fa(m.days_in_month)} روز{m.partial_month ? "؛ ماه ناقص" : ""}</small></td><td>{cash(m.purchase_discount_irr)}</td><td>{cash(m.purchase_net_irr)}</td><td>{cash(m.sales_discount_irr)}</td><td>{cash(m.net_sales_irr)}</td><td>{fa(m.costed_sales_lines)} از {fa(m.sales_lines)}</td><td>{cash(m.estimated_cogs_irr)}</td><td>{cash(m.budget_expense_for_period_irr)}</td><td>{cash(m.estimated_net_profit_irr)}{m.estimated_net_profit_irr == null && m.estimated_profit_before_unverified_purchase_tax_irr != null && <small>پیش از تعیین مالیات خرید: {cash(m.estimated_profit_before_unverified_purchase_tax_irr)}</small>}</td></tr>)}</tbody></table></div>
      <p className={styles.warning}>این بخش برآورد عملیاتی است؛ موجودی و ارزش ابتدای دوره، پیوند برگشت‌ها، سیاست مالیات خرید و پوشش مالیات دوره و هزینهٔ مالی کامل نیست. مبلغ نامعلوم صفر نمی‌شود و در سود تأییدشده یا تحقق هدف رشد ۲۰ درصد وارد نمی‌شود.</p>
      <details><summary>محدودیت محاسبه و علت پوشش ناقص</summary>{estimate.limitations.map(s => <p key={s} className={styles.help}>{s}</p>)}<ul>{[...new Set(estimate.blockers.map(b => `${b.month ? monthLabel(b.month) + "؛ " : ""}${b.reason}`))].slice(0, 40).map(reason => <li key={reason}>{reason}</li>)}</ul></details></> : <p className={styles.empty}>ابتدا دیتای مالی هلو را دریافت کنید.</p>}
    </Surface>
    <Surface className={styles.panel}><header><h3>برنامهٔ هزینه، تعهد و وصول لازم</h3></header><p className={styles.warning}>مانده‌های بانک و صندوق و تعهدات هنوز کامل و به‌روز تأیید نشده‌اند؛ اعداد زیر فقط سناریو هستند و نشان‌دهندهٔ سلامت قطعی نقدینگی نیستند.</p>
      <p className={styles.help}>بازه: {formatIranDate(projection.start)} تا {formatIranDate(projection.end)}. مبنای موجودی: {plan.balance_source === "excel" ? "گزارش اکسل انتخاب‌شده" : "هلو"}؛ با حساب‌های دستی جمع نمی‌شود. هزینهٔ ماه ناقص به نسبت روزهای تقویمی محاسبه می‌شود؛ فروش آینده حدس زده نشده است.</p>
      <div className={styles.metrics}>{[["موجودی مبنای انتخاب‌شده؛ نیازمند تطبیق", projection.opening_balance_irr], ["کمترین ماندهٔ سناریو", projection.totals.minimum_balance_irr], ["وصول اضافهٔ لازم برای پوشش کسری سناریو", projection.totals.required_extra_collections_irr]].map(([label, value]) => <article className={styles.metric} key={String(label)}><span>{label}</span><strong>{cash(value as number | null)}</strong></article>)}</div>
      <div className={styles.tableWrap} tabIndex={0}><table><thead><tr>{["ماه", "روزهای برنامه", "بودجهٔ هزینهٔ بازه", "هزینهٔ فاقد سند مرتبط", "پرداختنی ثبت‌شده", "وصول موردانتظار ثبت‌شده", "ماندهٔ پایان", "وصول اضافهٔ لازم تا کف وجه"].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{projection.months.map(m => <tr key={m.month}><td>{monthLabel(m.month)}</td><td>{fa(m.days_in_horizon)}</td><td>{cash(m.period_expense_budget_irr)}</td><td>{cash(m.operating_envelope_outflow_irr)}</td><td>{cash(m.payable_outflow_irr)}</td><td>{cash(m.expected_receipts_irr)}</td><td>{cash(m.closing_balance_irr)}</td><td>{cash(m.required_extra_collections_irr)}</td></tr>)}</tbody></table></div>
      <p className={styles.help}>وصول لازم، فروش پیش‌بینی‌شده نیست و مقادیر ماه‌ها با هم جمع نمی‌شوند. ماندهٔ هر ماه ادامهٔ ماه قبل است؛ چک خرج‌شده بدون شناسه و وضعیت معتبر دوباره پرداخت حساب نمی‌شود.</p>
      <details><summary>فرض‌ها و هشدارهای برنامهٔ وجه</summary>{[...projection.warnings, ...projection.methods].map((s, i) => <p key={i} className={styles.help}>{s}</p>)}</details>
    </Surface>
  </>;
}
