"use client";

import { useEffect, useState, type ReactNode } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
import { currentPersianMonth, displayMoney, emptyRules, inputMoney, normalizeNumberText, parseRules, record, validPersianMonth, validateForm, type MoneyUnit, type RulesForm, type RuleTarget } from "../../lib/payroll-contract";

type Person = { id: number; name: string };
type Contract = { configured?: boolean; rules_approved?: boolean; effective_month?: string; rule_version?: number; rules?: unknown; unresolved_questions?: string[]; question_answers?: Record<string, string>; decision_note?: string };
type Preview = { provisional_total?: number; base_pay?: number; overtime_pay?: number; sales_commission?: number; collection_commission?: number; blockers?: Array<{ message: string }> };
const unitLabel = (unit: MoneyUnit) => unit === "toman" ? "تومان" : "ریال";
const errorText = (cause: unknown) => cause instanceof Error ? cause.message : "ارتباط با سرویس انجام نشد.";
const questionList = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <Surface className="p-5"><h2 className="mb-4 text-sm font-bold text-violet-200">{title}</h2>{children}</Surface>;
}
function Amount({ label, value, change, unit }: { label: string; value: string; change: (value: string) => void; unit: MoneyUnit }) {
  const [editing, setEditing] = useState(false);
  const [typed, setTyped] = useState("");
  return <label className="block text-xs text-slate-400">{label} ({unitLabel(unit)})<input type="text" inputMode="decimal" value={editing ? typed : displayMoney(value, unit)} onFocus={() => { setTyped(displayMoney(value, unit)); setEditing(true); }} onBlur={() => setEditing(false)} onChange={event => { setTyped(event.target.value); change(inputMoney(event.target.value, unit)); }} className={`${fieldClass} mt-2`} dir="ltr" /></label>;
}
function NumberField({ label, value, change, optional = false }: { label: string; value: string | null; change: (value: string | null) => void; optional?: boolean }) {
  return <label className="block text-xs text-slate-400">{label}<input type="text" inputMode="decimal" value={value ?? ""} placeholder={optional ? "تعیین نشده" : ""} onChange={event => change(optional && !event.target.value.trim() ? null : normalizeNumberText(event.target.value))} className={`${fieldClass} mt-2`} dir="ltr" /></label>;
}

export default function CompensationPage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [person, setPerson] = useState("");
  const [month, setMonth] = useState(currentPersianMonth);
  const [unit, setUnit] = useState<MoneyUnit>("toman");
  const [rules, setRules] = useState<RulesForm>(emptyRules);
  const [contract, setContract] = useState<Contract>({});
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadedKey, setLoadedKey] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [description, setDescription] = useState("");
  const [summary, setSummary] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [decisionNote, setDecisionNote] = useState("");
  const [approvalConfirmed, setApprovalConfirmed] = useState(false);
  const [copyPerson, setCopyPerson] = useState("");
  const [previewHours, setPreviewHours] = useState("0");
  const [previewDays, setPreviewDays] = useState("0");
  const [preview, setPreview] = useState<Preview | null>(null);
  const normalizedMonth = normalizeNumberText(month).replace("/", "-");
  const key = `${person}:${normalizedMonth}`;
  const ready = loadedKey === key && validPersianMonth(month);
  const busy = saving || drafting || previewing;
  const unresolved = questions.filter(question => !answers[question]?.trim());

  useEffect(() => {
    let active = true;
    secureApi<{ items: Person[]; can_approve: boolean }>("/api/compensation/payroll-people").then(data => {
      if (!active) return;
      const rows = Array.isArray(data.items) ? data.items : [];
      setPeople(rows); setCanEdit(data.can_approve === true);
      const search = new URLSearchParams(window.location.search);
      const requested = search.get("salesperson_id");
      const assistantDescription = search.get("assistant_description");
      if (data.can_approve && assistantDescription && rows.some(row => String(row.id) === requested)) {
        setDescription(assistantDescription.slice(0, 4000));
        setMessage("شرح دستیار دریافت شد؛ پیشنهاد قواعد را بزنید و پیش از ذخیره، شرایط و شخص را بررسی کنید.");
        search.delete("assistant_description");
        window.history.replaceState(null, "", `${window.location.pathname}?${search.toString()}${window.location.hash}`);
      }
      setPerson(String(rows.find(row => String(row.id) === requested)?.id ?? rows[0]?.id ?? ""));
    }).catch(cause => { if (active) setError(errorText(cause)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!person || !validPersianMonth(month)) return;
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      setLoading(true); setError(""); setMessage(""); setLoadedKey("");
      try {
        const data = await secureApi<Contract>(`/api/compensation/contract/${person}?month=${encodeURIComponent(normalizedMonth)}`);
        if (!active) return;
        setContract(data); setRules(parseRules(data.rules ?? data));
        setQuestions(questionList(data.unresolved_questions)); setAnswers(data.question_answers ?? {});
        setDecisionNote(data.decision_note ?? "");
        setSummary(""); setPreview(null); setDirty(false); setApprovalConfirmed(false); setLoadedKey(`${person}:${normalizedMonth}`);
      } catch (cause: unknown) { if (active) setError(errorText(cause)); }
      finally { if (active) setLoading(false); }
    });
    return () => { active = false; };
  }, [person, normalizedMonth, month, refreshKey]);

  const touch = () => { setDirty(true); setApprovalConfirmed(false); setMessage(""); setPreview(null); };
  const update = <K extends keyof RulesForm>(field: K, value: RulesForm[K]) => { setRules(previous => ({ ...previous, [field]: value })); touch(); };
  const updateTarget = (index: number, patch: Partial<RuleTarget>) => update("targets", rules.targets.map((target, targetIndex) => targetIndex === index ? { ...target, ...patch } : target));
  const addTarget = (type: "brand" | "product") => update("targets", [...rules.targets, { target_type: type, item_identifier: "", item_title: "", target_amount: "0", target_quantity: "0", commission_percent: "0", target_gate: null, commission_basis: null }]);
  const addTier = () => {
    const tiers = [...rules.sales_tiers], newTier = { up_to_amount: "", percent: "" };
    const last = tiers[tiers.length - 1];
    tiers.splice(last?.up_to_amount === null ? tiers.length - 1 : tiers.length, 0, newTier);
    update("sales_tiers", tiers);
  };
  const combinedDecision = () => [decisionNote.trim(), ...questions.filter(question => answers[question]?.trim()).map(question => `${question}\n${answers[question].trim()}`)].filter(Boolean).join("\n\n");
  const payload = () => ({ ...rules, currency: "IRR", sales_scope: "personal", commission_tier_basis: "marginal", effective_month: normalizedMonth, unresolved_questions: unresolved, decision_note: combinedDecision() });

  const save = async (approve: boolean) => {
    if (!ready || busy || !canEdit) return;
    setError(""); setMessage("");
    const validation = validateForm(rules);
    if (validation) { setError(validation); return; }
    if (approve) {
      if (rules.salary_mode === "fixed" && !rules.fixed_proration) { setError("نحوهٔ پرداخت کامل یا متناسب با روز کار حقوق ثابت را مشخص کنید."); return; }
      if (rules.salary_mode === "fixed" && rules.fixed_proration === "working_days" && Number(rules.required_workdays ?? 0) <= 0) { setError("روز موظفی مصوب ماه برای حقوق ثابت متناسب باید مشخص باشد."); return; }
      if (rules.salary_mode !== "commission_only" && Number(rules.min_monthly_hours) > 0 && rules.overtime_multiplier === null) { setError("ضریب مصوب اضافه‌کار را مشخص کنید؛ اگر اضافه‌کار تعلق نمی‌گیرد، آن را صریحاً صفر ثبت کنید."); return; }
      if (rules.targets.some(target => Number(target.commission_percent) > 0 && (!target.item_identifier.trim() || !target.target_gate || !target.commission_basis))) { setError("شناسهٔ ثابت، شرط تحقق و مبنای مبلغ همهٔ هدف‌های دارای پورسانت را مشخص کنید."); return; }
      const bonus = record(rules.content_bonus);
      if ((Number(bonus.monthly_amount ?? 0) > 0 || Number(bonus.per_post_amount ?? 0) > 0) && Number(bonus.required_stories ?? 0) > 0 && !bonus.story_requirement) { setError("رابطهٔ شرط استوری و پاداش محتوا هنوز مشخص نشده است."); return; }
    }
    if (combinedDecision().length > 2000) { setError("جمع یادداشت مصوبه و پاسخ‌های ابهام‌ها باید حداکثر ۲۰۰۰ نویسه باشد."); return; }
    if (approve && (!approvalConfirmed || unresolved.length)) { setError("ابهام‌ها را پاسخ دهید و بازبینی شخص و ماه را تأیید کنید."); return; }
    setSaving(true);
    try {
      const data = await secureApi<Contract>(`/api/compensation/contract/${person}`, { method: "POST", body: JSON.stringify({ ...payload(), rules_approved: approve }) });
      setContract({ ...data, configured: true }); setRules(parseRules(data.rules ?? rules)); setDirty(false); setApprovalConfirmed(false);
      setDecisionNote(combinedDecision()); setQuestions(unresolved); setAnswers({});
      setMessage(approve ? "نسخهٔ قواعد این شخص و ماه تصویب شد. این کار به معنی تأیید فیش یا پرداخت نیست." : "نسخهٔ پیش‌نویس ذخیره شد؛ هنوز مبنای فیش قطعی نیست.");
    } catch (cause: unknown) { setError(errorText(cause)); }
    finally { setSaving(false); }
  };

  const draftWithAssistant = async () => {
    if (!description.trim() || !ready || busy || !canEdit) return;
    setDrafting(true); setError(""); setMessage("");
    try {
      const data = await secureApi<{ rules: unknown; questions?: unknown; summary?: string }>("/api/compensation/rules-draft", { method: "POST", body: JSON.stringify({ description, current_rules: rules }) });
      setRules(parseRules(data.rules)); setQuestions(questionList(data.questions)); setAnswers({}); setSummary(data.summary || ""); touch();
      setMessage("پیشنهاد دستیار فقط در فرم قرار گرفت؛ برای ثبت، پیش‌نویس را ذخیره کنید یا پس از رفع ابهام‌ها نسخه را تصویب کنید.");
    } catch (cause: unknown) { setError(errorText(cause)); }
    finally { setDrafting(false); }
  };

  const copyRules = async () => {
    if (!copyPerson || busy || !ready || !canEdit) return;
    setDrafting(true); setError("");
    try {
      const data = await secureApi<Contract>(`/api/compensation/contract/${copyPerson}?month=${encodeURIComponent(normalizedMonth)}`);
      if (!data.configured) throw new Error("برای شخص مبدأ در این ماه قواعدی ثبت نشده است.");
      setRules(parseRules(data.rules ?? data)); setQuestions(questionList(data.unresolved_questions)); setAnswers({}); touch();
      setMessage("قواعد شخص مبدأ فقط به فرم کپی شد؛ برای شخص انتخاب‌شده هنوز ذخیره نشده است.");
    } catch (cause: unknown) { setError(errorText(cause)); }
    finally { setDrafting(false); }
  };

  const najmiDraft = () => {
    setRules({ ...emptyRules(), salary_mode: "fixed", fixed_monthly_amount: "130000000", fixed_proration: "working_days", sales_tiers: [{ up_to_amount: null, percent: "1" }], content_bonus: { monthly_amount: "20000000", required_posts: 4, required_stories: 30, per_post_amount: "5000000", story_requirement: null } });
    setQuestions(["روزهای موظفی مصوب این ماه برای تسهیم حقوق ثابت چند روز است؟", "تکمیل استوری شرط کل پاداش محتواست یا پاداش هر پست مستقل پرداخت می‌شود؟"]);
    setAnswers({}); setSummary("پیش‌نویس بر اساس توضیح ثبت‌شده: پایهٔ ۱۳ میلیون تومان متناسب با روز کار، و بخش مستقل تولید محتوا. پاسخ‌های باز باید پیش از تصویب روشن شوند."); touch();
  };

  const kermaniDraft = () => {
    setRules({ ...emptyRules(), settlement_commission_percent: "1", sales_tiers: [{ up_to_amount: "", percent: "5" }] });
    setQuestions(["سقف فروش شخصی پلهٔ اول با نرخ ۵ درصد چقدر است؟", "سقف و درصد هر پلهٔ بالاتر چگونه تعیین شده است؟"]);
    setAnswers({}); setSummary("نرخ ۵ درصد پلهٔ اول و ۱ درصد وصول شخصی وارد فرم شد. سقف پلهٔ اول و پله‌های بعدی حدس زده نشده‌اند؛ برای ذخیره، سقف را وارد کنید و پله‌های مصوب را اضافه کنید."); touch();
  };

  const runPreview = async () => {
    if (!ready || busy || !canEdit) return;
    const validation = validateForm(rules);
    if (validation) { setError(validation); return; }
    setPreviewing(true); setError("");
    try {
      const data = await secureApi<Preview>("/api/compensation/rules-preview", { method: "POST", body: JSON.stringify({ rules, worked_hours: normalizeNumberText(previewHours), verified_visit_days: normalizeNumberText(previewDays), facts: [], source_complete: {} }) });
      setPreview(data);
    } catch (cause: unknown) { setError(errorText(cause)); }
    finally { setPreviewing(false); }
  };

  const content = record(rules.content_bonus);
  const contentField = (field: string, value: unknown) => update("content_bonus", { ...content, [field]: value });
  const personName = people.find(item => String(item.id) === person)?.name || "پرسنل";
  return <PortalShell title="قواعد حقوق و پورسانت ماهانه" eyebrow="قرارداد اختصاصی پرسنل">
    <div className="space-y-5">
      <Surface className="p-5">
        <p className="text-xs leading-6 text-slate-400">هر شخص برای هر ماه نسخهٔ مستقل دارد. کپی یا پیشنهاد دستیار، فرم را پر می‌کند و ذخیرهٔ خودکار ندارد. مبالغ همیشه در سرور به ریال ذخیره می‌شوند.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-slate-400">پرسنل<select value={person} disabled={busy} onChange={event => setPerson(event.target.value)} className={`${fieldClass} mt-2`}><option value="">انتخاب شخص</option>{people.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          <label className="text-xs text-slate-400">ماه اثرگذاری شمسی<input value={month} disabled={busy} onChange={event => setMonth(event.target.value)} placeholder="۱۴۰۵-۰۷" className={`${fieldClass} mt-2`} dir="ltr" aria-invalid={!validPersianMonth(month)} /></label>
          <label className="text-xs text-slate-400">واحد ورود مبلغ<select value={unit} onChange={event => setUnit(event.target.value as MoneyUnit)} disabled={busy} className={`${fieldClass} mt-2`}><option value="toman">تومان</option><option value="rial">ریال</option></select></label>
        </div>
        {!validPersianMonth(month) && <p className="mt-3 text-xs text-amber-200">ماه را به شکل سال چهاررقمی و ماه دورقمی شمسی وارد کنید؛ نمونه: ۱۴۰۵-۰۷.</p>}
        {dirty && <p className="mt-3 text-xs text-amber-200">فرم تغییر کرده و ذخیره نشده است؛ تغییر شخص یا ماه این تغییرات را کنار می‌گذارد.</p>}
      </Surface>
      {error && <p role="alert" className="rounded-xl border border-rose-400/20 bg-rose-500/10 p-4 text-xs leading-6 text-rose-200">{error}</p>}
      {message && <p role="status" className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-4 text-xs leading-6 text-emerald-200">{message}</p>}
      {loading ? <Surface className="p-8 text-center text-xs text-slate-400">در حال دریافت قواعد ماه انتخاب‌شده…</Surface> : !ready ? <Surface className="p-6 text-xs text-slate-400">شخص و ماه معتبر را انتخاب کنید.{person && validPersianMonth(month) && <button type="button" onClick={() => setRefreshKey(value => value + 1)} className={`${primaryButton} mr-3`}>دریافت دوباره</button>}</Surface> : <>
        <Surface className="p-4"><div className="flex flex-wrap justify-between gap-3 text-xs"><b className="text-white">{personName} · {normalizedMonth}</b><span className={contract.rules_approved && !dirty ? "text-emerald-300" : "text-amber-200"}>{dirty ? "تغییرات ذخیره‌نشده" : contract.rules_approved ? "نسخهٔ مصوب قواعد" : contract.configured ? "پیش‌نویس قواعد" : "قواعد جدید"}{contract.rule_version ? ` · نسخهٔ ${contract.rule_version.toLocaleString("fa-IR")}` : ""}</span></div>{contract.effective_month && contract.effective_month !== normalizedMonth && <p className="mt-3 text-xs leading-6 text-slate-400">آخرین نسخهٔ مؤثر از ماه {contract.effective_month} نمایش داده شده است؛ ذخیره، نسخهٔ جدیدی برای ماه انتخاب‌شده می‌سازد.</p>}{!canEdit && <p className="mt-3 text-xs text-slate-400">این حساب فقط می‌تواند قواعد خودش را مشاهده کند.</p>}</Surface>
        <fieldset disabled={!canEdit || busy} className="space-y-5 disabled:opacity-75">
          <Section title="پیشنهاد دستیار و کپی قواعد">
            <label className="text-xs text-slate-400">شرح حقوق و پورسانت این شخص<textarea value={description} onChange={event => setDescription(event.target.value)} rows={3} maxLength={12000} className={`${fieldClass} mt-2`} placeholder="شرایط مصوب، درصد پله‌ها، حقوق ثابت یا ساعتی و ابهام‌های باقی‌مانده را بنویسید." /></label>
            <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={draftWithAssistant} disabled={!description.trim()} className={primaryButton}>{drafting ? "در حال آماده‌سازی…" : "پیشنهاد قواعد از توضیح"}</button><button type="button" onClick={kermaniDraft} className="rounded-xl border border-white/15 px-4 py-2 text-xs text-slate-200">الگوی کرمانی؛ تعیین سقف لازم است</button><button type="button" onClick={najmiDraft} className="rounded-xl border border-white/15 px-4 py-2 text-xs text-slate-200">الگوی نجمی؛ فقط پیش‌نویس</button></div>
            <div className="mt-4 flex flex-wrap gap-2"><select aria-label="شخص مبدأ کپی قواعد" value={copyPerson} onChange={event => setCopyPerson(event.target.value)} className={`${fieldClass} max-w-xs`}><option value="">کپی از قواعد شخص دیگر</option>{people.filter(item => String(item.id) !== person).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button type="button" onClick={copyRules} disabled={!copyPerson} className="rounded-xl border border-violet-400/20 px-4 py-2 text-xs text-violet-200">کپی به فرم این ماه</button></div>
            {summary && <p className="mt-4 rounded-xl bg-white/5 p-3 text-xs leading-7 text-slate-300">{summary}</p>}
          </Section>
          <Section title="حقوق پایه، موظفی و اضافه‌کار">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <label className="text-xs text-slate-400">نوع حقوق<select value={rules.salary_mode} onChange={event => update("salary_mode", event.target.value as RulesForm["salary_mode"])} className={`${fieldClass} mt-2`}><option value="hourly">حقوق ساعتی</option><option value="fixed">حقوق ثابت ماهانه</option><option value="commission_only">فقط پورسانت</option></select></label>
              {rules.salary_mode === "fixed" && <><Amount label="حقوق ثابت ماهانه" value={rules.fixed_monthly_amount} change={value => update("fixed_monthly_amount", value)} unit={unit} /><label className="text-xs text-slate-400">نحوهٔ پرداخت ثابت<select value={rules.fixed_proration ?? ""} onChange={event => update("fixed_proration", event.target.value as RulesForm["fixed_proration"] || null)} className={`${fieldClass} mt-2`}><option value="">تعیین نشده</option><option value="full">پرداخت کامل ماهانه</option><option value="working_days">متناسب با روزهای کار مستند</option></select></label>{rules.fixed_proration === "working_days" && <NumberField label="روز موظفی مصوب ماه" value={rules.required_workdays} optional change={value => update("required_workdays", value)} />}</>}
              {rules.salary_mode !== "commission_only" && <><Amount label={rules.salary_mode === "fixed" ? "نرخ ساعتی اضافه‌کار" : "نرخ هر ساعت کار"} value={rules.hourly_rate} change={value => update("hourly_rate", value)} unit={unit} /><NumberField label="ساعت موظفی ماه؛ صفر یعنی بدون آستانه" value={rules.min_monthly_hours} change={value => update("min_monthly_hours", value ?? "")} /><NumberField label="ضریب مصوب اضافه‌کار" optional value={rules.overtime_multiplier} change={value => update("overtime_multiplier", value)} /></>}
            </div>
            <p className="mt-4 text-xs leading-6 text-slate-500">روز کارکرد از اسناد تأییدشده دریافت می‌شود. این فرم عدد روز کارکرد نمی‌سازد و هیچ نرخ قانونی را خودکار فرض نمی‌کند.</p>
          </Section>
          <Section title="فروش و وصول شخصی، مأموریت و مسیر">
            <p className="mb-4 text-xs leading-6 text-slate-400">مبنای فروش و وصول، اطلاعات خود همین شخص است. فروش خالص با کسر برگشت محاسبه می‌شود.</p>
            <div className="grid gap-4 sm:grid-cols-3"><NumberField label="درصد پورسانت وصول شخصی" value={rules.settlement_commission_percent} change={value => update("settlement_commission_percent", value ?? "")} /><Amount label="مأموریت هر روز بازدید معتبر" value={rules.daily_mission_allowance} change={value => update("daily_mission_allowance", value)} unit={unit} /><Amount label="مبلغ هر کیلومتر مسیر مصوب" value={rules.per_km_rate} change={value => update("per_km_rate", value)} unit={unit} /></div>
          </Section>
          <Section title="پلکان پورسانت؛ هر درصد فقط روی مازاد پلهٔ قبل">
            <p className="mb-4 text-xs leading-6 text-slate-400">سقف‌ها صعودی‌اند. هر پله از سقف پلهٔ قبل شروع می‌شود؛ درصد پلهٔ بالاتر به کل فروش برنمی‌گردد. آخرین پله می‌تواند بدون سقف باشد.</p>
            <div className="space-y-3">{rules.sales_tiers.map((tier, index) => <div key={index} className="rounded-xl border border-white/10 bg-black/15 p-3"><div className="mb-3 flex justify-between text-xs"><b className="text-slate-300">پلهٔ {(index + 1).toLocaleString("fa-IR")}</b><button type="button" aria-label={`حذف پلهٔ ${index + 1}`} onClick={() => update("sales_tiers", rules.sales_tiers.filter((_, itemIndex) => itemIndex !== index))} className="text-rose-300">حذف</button></div><div className="grid gap-3 sm:grid-cols-3">{tier.up_to_amount !== null ? <Amount label="سقف فروش خالص این پله" value={tier.up_to_amount} unit={unit} change={value => update("sales_tiers", rules.sales_tiers.map((row, rowIndex) => rowIndex === index ? { ...row, up_to_amount: value } : row))} /> : <p className="self-center text-xs text-slate-400">مازاد آخرین سقف، بدون محدودیت</p>}<NumberField label="درصد این بخش از فروش" value={tier.percent} change={value => update("sales_tiers", rules.sales_tiers.map((row, rowIndex) => rowIndex === index ? { ...row, percent: value ?? "" } : row))} />{index === rules.sales_tiers.length - 1 && <label className="flex items-center gap-2 self-center text-xs text-slate-400"><input type="checkbox" checked={tier.up_to_amount === null} onChange={event => update("sales_tiers", rules.sales_tiers.map((row, rowIndex) => rowIndex === index ? { ...row, up_to_amount: event.target.checked ? null : "" } : row))} />آخرین پله بدون سقف</label>}</div></div>)}</div>
            {!rules.sales_tiers.length && <p className="mb-3 text-xs text-slate-500">پلکانی تعریف نشده است.</p>}<button type="button" onClick={addTier} className={`${primaryButton} mt-3`}>افزودن پله</button>
          </Section>
          <Section title="هدف اختیاری برند و کالا و روش همپوشانی">
            <label className="block max-w-md text-xs text-slate-400">اگر چند پورسانت به یک فروش تعلق بگیرند<select value={rules.commission_overlap ?? ""} onChange={event => update("commission_overlap", event.target.value as RulesForm["commission_overlap"] || null)} className={`${fieldClass} mt-2`}><option value="">تعیین نشده</option><option value="highest">فقط بیشترین پورسانت</option><option value="sum">جمع پورسانت‌های مصوب</option></select></label>
            <div className="mt-4 space-y-4">{rules.targets.map((target, index) => <div key={index} className="rounded-xl border border-white/10 p-4"><div className="mb-4 flex justify-between text-xs"><b className="text-violet-200">هدف {target.target_type === "brand" ? "برند" : "کالا"} {(index + 1).toLocaleString("fa-IR")}</b><button type="button" onClick={() => update("targets", rules.targets.filter((_, itemIndex) => itemIndex !== index))} className="text-rose-300">حذف هدف</button></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><label className="text-xs text-slate-400">شناسهٔ ثابت برند یا کالا<input value={target.item_identifier} onChange={event => updateTarget(index, { item_identifier: event.target.value })} className={`${fieldClass} mt-2`} /></label><label className="text-xs text-slate-400">عنوان نمایشی<input value={target.item_title} onChange={event => updateTarget(index, { item_title: event.target.value })} className={`${fieldClass} mt-2`} /></label><Amount label="مبلغ هدف" value={target.target_amount} unit={unit} change={value => updateTarget(index, { target_amount: value })} /><NumberField label="تعداد هدف؛ صفر یعنی بدون شرط تعداد" value={target.target_quantity} change={value => updateTarget(index, { target_quantity: value ?? "" })} /><NumberField label="درصد پورسانت هدف" value={target.commission_percent} change={value => updateTarget(index, { commission_percent: value ?? "" })} /><label className="text-xs text-slate-400">شرط مبلغ و تعداد<select value={target.target_gate ?? ""} onChange={event => updateTarget(index, { target_gate: event.target.value as RuleTarget["target_gate"] || null })} className={`${fieldClass} mt-2`}><option value="">تعیین نشده</option><option value="all">تحقق همهٔ شرط‌های تعیین‌شده</option><option value="any">تحقق یکی از شرط‌های تعیین‌شده</option></select></label><label className="text-xs text-slate-400">مبنای مبلغ پورسانت<select value={target.commission_basis ?? ""} onChange={event => updateTarget(index, { commission_basis: event.target.value as RuleTarget["commission_basis"] || null })} className={`${fieldClass} mt-2`}><option value="">تعیین نشده</option><option value="whole">کل مبلغ پس از تحقق هدف</option><option value="excess">فقط مبلغ مازاد بر هدف</option></select></label></div></div>)}</div>
            <div className="mt-4 flex flex-wrap gap-2"><button type="button" onClick={() => addTarget("brand")} className={primaryButton}>افزودن هدف برند</button><button type="button" onClick={() => addTarget("product")} className={primaryButton}>افزودن هدف کالا</button></div>
          </Section>
          <Section title="پاداش مستقل تولید محتوا">
            <label className="flex items-center gap-2 text-xs text-slate-300"><input type="checkbox" checked={!!rules.content_bonus} onChange={event => update("content_bonus", event.target.checked ? { monthly_amount: "0", required_posts: 0, required_stories: 0, per_post_amount: "0", story_requirement: null } : undefined)} />این شخص پاداش تولید محتوا دارد</label>
            {rules.content_bonus && <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Amount label="سقف پاداش ماهانه" value={String(content.monthly_amount ?? "0")} unit={unit} change={value => contentField("monthly_amount", value)} />
              <NumberField label="تعداد پست کامل موردنیاز" value={String(content.required_posts ?? "0")} change={value => contentField("required_posts", value ?? "")} />
              <NumberField label="تعداد استوری موردنیاز" value={String(content.required_stories ?? "0")} change={value => contentField("required_stories", value ?? "")} />
              <Amount label={content.story_requirement === "per_bundle" ? "مبلغ هر بستهٔ کامل" : "مبلغ هر پست کامل"} value={String(content.per_post_amount ?? "0")} unit={unit} change={value => contentField("per_post_amount", value)} />
              <label className="text-xs text-slate-400">رابطهٔ شرط استوری و پاداش<select value={String(content.story_requirement ?? "")} onChange={event => contentField("story_requirement", event.target.value || null)} className={`${fieldClass} mt-2`}><option value="">تعیین نشده</option><option value="gate_full">تکمیل استوری شرط کل پاداش است</option><option value="independent">پاداش هر پست مستقل از شرط استوری است</option><option value="per_bundle">هر بستهٔ یک پست و استوری‌های مشخص</option></select></label>
              {content.story_requirement === "per_bundle" && <NumberField label="تعداد استوری در هر بستهٔ یک‌پستی" value={String(content.stories_per_bundle ?? "")} change={value => contentField("stories_per_bundle", value ?? "")} />}
            </div>}
            <p className="mt-3 text-xs leading-6 text-slate-500">تعداد محتوای انجام‌شده از اسناد کار تأییدشده می‌آید؛ این بخش فقط قاعدهٔ پرداخت را تعریف می‌کند.</p>
          </Section>
          <Section title="سیاست پاداش مستقل">
            <label className="block text-xs text-slate-400">شرایط تعلق پاداش، هدف و مرجع تأیید<textarea value={rules.bonus_note} onChange={event => update("bonus_note", event.target.value)} maxLength={1000} rows={3} className={`${fieldClass} mt-2`} placeholder="نمونه: پاداش انجام هدف مشخص، پس از بررسی نتیجه و تأیید مدیر" /></label>
            <p className="mt-3 text-xs leading-6 text-slate-500">این متن سیاست پاداش را نگه می‌دارد. مبلغ متغیر هر ماه با دلیل و سند، توسط مدیر در کارکرد همان ماه ثبت می‌شود؛ نوشتن مبلغ در این متن به‌تنهایی پاداش ایجاد نمی‌کند.</p>
          </Section>
          {questions.length > 0 && <Section title="ابهام‌هایی که پیش از تصویب باید پاسخ داده شوند"><div className="space-y-4">{questions.map(question => <label key={question} className="block text-xs leading-6 text-amber-200">{question}<textarea value={answers[question] ?? ""} onChange={event => { setAnswers(previous => ({ ...previous, [question]: event.target.value })); touch(); }} rows={2} className={`${fieldClass} mt-2`} placeholder="تصمیم مصوب را بنویسید و فیلد مرتبط فرم را مطابق آن تنظیم کنید." /></label>)}</div><p className="mt-3 text-xs text-slate-500">پاسخ متنی، مقدار فیلدهای فرمول را خودکار تغییر نمی‌دهد؛ هر دو را بازبینی کنید.</p></Section>}
          <Section title="پیش‌نمایش آزمایشی محاسبه">
            <p className="mb-4 text-xs leading-6 text-slate-400">این اعداد فقط برای پیش‌نمایش‌اند و به عنوان کارکرد واقعی یا سند فروش ثبت نمی‌شوند. فروش، وصول، مسیر و محتوا در این پیش‌نمایش منبع کامل ندارند و ممکن است محاسبه مسدود بماند.</p>
            <div className="grid gap-3 sm:grid-cols-3"><NumberField label="ساعت کار آزمایشی" value={previewHours} change={value => setPreviewHours(value ?? "")} /><NumberField label="روز بازدید آزمایشی" value={previewDays} change={value => setPreviewDays(value ?? "")} /><button type="button" onClick={runPreview} className={`${primaryButton} self-end`}>{previewing ? "در حال محاسبه…" : "دیدن پیش‌نمایش"}</button></div>
            {preview && <div className="mt-4 rounded-xl border border-white/10 bg-black/15 p-4"><div className="text-sm text-white">جمع موقت: {Number(preview.provisional_total || 0).toLocaleString("fa-IR")} ریال</div>{preview.blockers?.map((blocker, index) => <p key={index} className="mt-2 text-xs leading-6 text-amber-200">{blocker.message}</p>)}</div>}
          </Section>
        </fieldset>
        {canEdit && <Surface className="p-5"><p className="text-xs leading-6 text-slate-400">ذخیرهٔ پیش‌نویس، فرمول را قطعی نمی‌کند. تصویب، نسخهٔ صریح قواعد همین شخص و ماه را می‌سازد؛ فیش و پرداخت مرحلهٔ جداگانه دارند.</p><label className="mt-4 block text-xs text-slate-400">یادداشت مصوبه و تصمیم نهایی<textarea value={decisionNote} maxLength={2000} disabled={busy} onChange={event => { setDecisionNote(event.target.value); touch(); }} rows={3} className={`${fieldClass} mt-2`} placeholder="تاریخ یا مرجع مصوبه و توضیح تصمیم مدیر" /></label><label className="mt-4 flex items-start gap-2 text-xs leading-6 text-slate-300"><input type="checkbox" disabled={busy} checked={approvalConfirmed} onChange={event => setApprovalConfirmed(event.target.checked)} className="mt-1" />قواعد {personName} برای ماه {normalizedMonth}، واحد مبلغ و پاسخ ابهام‌ها را بازبینی کرده‌ام.</label>{unresolved.length > 0 && <p className="mt-3 text-xs text-amber-200">{unresolved.length.toLocaleString("fa-IR")} ابهام بی‌پاسخ است؛ پیش‌نویس قابل ذخیره است و تصویب بسته می‌ماند.</p>}<div className="mt-4 flex flex-wrap gap-3"><button type="button" disabled={busy} onClick={() => void save(false)} className="rounded-xl border border-violet-400/30 px-5 py-3 text-xs font-bold text-violet-200 disabled:opacity-40">{saving ? "در حال ثبت…" : "ذخیرهٔ پیش‌نویس"}</button><button type="button" disabled={busy || !approvalConfirmed || unresolved.length > 0} onClick={() => void save(true)} className="rounded-xl bg-emerald-600 px-5 py-3 text-xs font-bold text-white disabled:opacity-40">تصویب نسخهٔ قواعد این ماه</button></div></Surface>}
      </>}
    </div>
  </PortalShell>;
}
