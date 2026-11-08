"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Surface, fieldClass, primaryButton } from "./portal-shell";
import { authFetch, secureApi } from "../lib/secure-api";
import { formatIranDateTime } from "../lib/iran-date";
import { matchesSearch } from "../lib/text-search";
import styles from "./treasury-strategy.module.css";
import type { PurchaseEstimate } from "./treasury-operating-plan";

type Batch = { id: number; kind: string; title: string; status: string; created_at: string; row_count: string; input_unit: string };
type Preview = { id: number; kind: string; title: string; status: string; headers: string[]; rows: (string | number | boolean | null)[][]; row_count: number; effects: string; source_note?: string; offset?: number; preview_limit?: number };
export type ExcelEstimate = { estimate: PurchaseEstimate; provenance: { kind: string; report_id: number | null; title: string }[]; source: string };
const KINDS = [["balances", "حساب و موجودی"], ["checks", "چک‌ها"], ["purchases", "خرید"], ["sales", "فروش"], ["purchase_returns", "برگشت خرید"], ["sales_returns", "برگشت فروش"], ["monthly", "گزارش ماهانه"], ["inventory", "موجودی کالا"], ["general", "گزارش عمومی"]] as const;
const fa = (value: number) => value.toLocaleString("fa-IR", { maximumFractionDigits: 0 });
const money = (value: number | null) => value == null ? "نیازمند تکمیل دیتا" : `${fa(value/10)} تومان`;
const errorText = (e: unknown) => e instanceof Error ? e.message : "عملیات انجام نشد.";
async function responseJson<T>(response: Response): Promise<T> { const body = await response.json(); if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "ساختار فایل یا ورودی معتبر نیست."); return body as T; }

export function TreasuryExcel({ reload, estimate }: { reload: () => Promise<void>; estimate: ExcelEstimate | null }) {
  const [kind, setKind] = useState("balances");
  const [inputMode,setInputMode]=useState<"excel"|"manual">("excel");
  const [manualHeaders,setManualHeaders]=useState<string[]>([]);
  const [manualRows,setManualRows]=useState<string[][]>([]);
  const [unit, setUnit] = useState("TOMAN");
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [sheet, setSheet] = useState("");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reports, setReports] = useState<Batch[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const refreshList = useCallback(async () => { try { setReports(await secureApi<Batch[]>("/treasury/excel/reports")); } catch (e) { setError(errorText(e)); } }, []);
  useEffect(() => { let active = true; void Promise.resolve().then(() => { if (active) void refreshList(); }); return () => { active = false; }; }, [refreshList]);
  useEffect(()=>{
    if(inputMode!=="manual")return;
    let active=true;
    secureApi<{headers:string[]}>(`/treasury/excel/manual-schema?kind=${kind}`).then(result=>{
      if(active){setManualHeaders(result.headers);setManualRows([result.headers.map(()=>"")]);}
    }).catch(error=>{if(active)setError(errorText(error));});
    return()=>{active=false;};
  },[inputMode,kind]);
  const invoice = ["purchases", "sales", "purchase_returns", "sales_returns"].includes(kind);
  async function chooseFile(selected: File | null) {
    setFile(null); setSheets([]); setSheet(""); setPreview(null); setError("");
    if (!selected) return;
    if (selected.size > 5*1024*1024) { setError("حداکثر حجم فایل پنج مگابایت است."); return; }
    setBusy(true);
    try {
      const body = new FormData(); body.append("file", selected);
      const response = await responseJson<{ sheets: string[] }>(await authFetch("/treasury/excel/sheets", { method: "POST", body }));
      setFile(selected); setSheets(response.sheets); setSheet(response.sheets.find(s => s === KINDS.find(k => k[0] === kind)?.[1]) ?? response.sheets[0]);
      if (!title) setTitle(selected.name.replace(/\.xlsx$/i, ""));
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function upload(event: FormEvent) {
    event.preventDefault(); if (inputMode==="excel" && !file) return; setBusy(true); setError(""); setMessage("");
    try {
      if(inputMode==="manual"){
        setPreview(await secureApi<Preview>("/treasury/excel/manual/preview",{method:"POST",body:JSON.stringify({kind,unit,title,source_note:note,headers:manualHeaders,rows:manualRows,from_date:invoice?from:"",to_date:invoice?to:""})}));
      } else {
      const body = new FormData(); body.append("file", file!); body.append("kind", kind); body.append("unit", unit); body.append("title", title); body.append("source_note", note); body.append("sheet_name", sheet);
      if (invoice) { body.append("from_date", from); body.append("to_date", to); }
      setPreview(await responseJson<Preview>(await authFetch("/treasury/excel/preview", { method: "POST", body })));
      }
      await refreshList(); setMessage("پیش‌نمایش آماده شد؛ هنوز هیچ چک، حساب یا عملکرد مالی وارد نشده است.");
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function commit() {
    if (!preview || !window.confirm(`${preview.effects}\n${fa(preview.row_count)} ردیف پس از بررسی ثبت شود؟`)) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await secureApi<{message: string}>(`/treasury/excel/${preview.id}/commit`, { method: "POST", body: JSON.stringify({ confirm: true }) });
      setPreview({ ...preview, status: "committed" }); await refreshList(); await reload(); setMessage(result.message);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  async function openReport(id: number, offset = 0) { setError(""); try { setPreview(await secureApi<Preview>(`/treasury/excel/reports/${id}?offset=${offset}`)); setSearch(""); } catch (e) { setError(errorText(e)); } }
  async function download(path: string, filename: string) {
    setError("");
    try {
      const response = await authFetch(path); if (!response.ok) throw new Error("دریافت فایل ممکن نشد.");
      const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(errorText(e)); }
  }
  return <>
    {(error || message) && <p role={error ? "alert" : "status"} className={error ? styles.error : styles.message}>{error || message}</p>}
    <Surface className={styles.panel}><header><h3>ورود دستی یا اکسل گزارش‌ها</h3><button onClick={() => void download("/treasury/excel/template", "treasury-import.xlsx")} className={styles.secondary}>دریافت قالب همهٔ گزارش‌ها</button></header>
      <p className={styles.help}>هر شیت یک جدول با سرستون در سطر اول باشد. فایل دارای فرمول یا ماکرو را به مقادیر ساده تبدیل کنید. گزارش عمومی با ستون‌های دلخواه برای نگهداری و مشاهده پذیرفته می‌شود؛ فقط نوع‌های مشخص وارد محاسبات مربوط می‌شوند. فایل اصلی هلو تغییر نمی‌کند.</p>
      <form onSubmit={upload}><div className={styles.formGrid}>
        <label className={styles.field}>روش ورود<select value={inputMode} disabled={busy} onChange={e=>{setInputMode(e.target.value as "excel"|"manual");setPreview(null);}} className={fieldClass}><option value="excel">اکسل</option><option value="manual">دستی</option></select></label>
        <label className={styles.field}>نوع گزارش<select value={kind} onChange={e => { setKind(e.target.value); setPreview(null); const name = KINDS.find(k => k[0] === e.target.value)?.[1]; if (name && sheets.includes(name)) setSheet(name); }} className={fieldClass}>{KINDS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
        <label className={styles.field}>واحد همهٔ مبالغ شیت<select value={unit} onChange={e => { setUnit(e.target.value); setPreview(null); }} className={fieldClass}><option value="TOMAN">تومان</option><option value="IRR">ریال</option></select></label>
        {inputMode==="excel"&&<><label className={styles.field}>فایل اکسل؛ حداکثر پنج مگابایت<input type="file" accept=".xlsx" disabled={busy} onChange={e => void chooseFile(e.target.files?.[0] ?? null)} className={fieldClass} /></label>
        <label className={styles.field}>شیت<select value={sheet} onChange={e => { setSheet(e.target.value); setPreview(null); }} required className={fieldClass}><option value="">انتخاب شیت</option>{sheets.map(s => <option key={s} value={s}>{s}</option>)}</select></label></>}
        <label className={styles.field}>عنوان گزارش<input required minLength={2} maxLength={200} className={fieldClass} value={title} onChange={e => {setTitle(e.target.value);setPreview(null);}} /></label>
        {invoice && <><label className={styles.field}>ابتدای بازه؛ شمسی<input required placeholder="۱۴۰۵/۰۱/۰۱" className={fieldClass} value={from} onChange={e => {setFrom(e.target.value);setPreview(null);}} /></label><label className={styles.field}>انتهای بازه؛ شمسی<input required placeholder="۱۴۰۵/۰۷/۲۷" className={fieldClass} value={to} onChange={e => {setTo(e.target.value);setPreview(null);}} /></label></>}
      </div><label className={styles.textarea}>منبع گزارش، تاریخ و دوره و توضیح کامل‌بودن<textarea required minLength={8} maxLength={2000} value={note} onChange={e => {setNote(e.target.value);setPreview(null);}} className={fieldClass} /></label>
        {invoice && <p className={styles.warning}>شناسهٔ کالا در همهٔ فایل‌ها یکسان و از هلو باشد. تخفیف کل فاکتور شامل تخفیف ردیف‌هاست؛ مبلغ سربرگ در هر ردیف فاکتور عیناً تکرار شود. گزارش بدون فاکتور باید فقط سرستون و بازهٔ صریح داشته باشد؛ صفر ردیف را هنگام تأیید بررسی کنید.</p>}
        {kind === "checks" && <p className={styles.warning}>هر چک یک شناسهٔ یکتا، جهت و وضعیت صریح داشته باشد. چک خرج‌شده را دوباره دریافتنی یا پرداختنیِ باز ثبت نکنید؛ انتقال‌های نامشخص را فعلاً با نوع «گزارش عمومی» برای تطبیق نگه دارید.</p>}
        {inputMode==="manual"&&<div className="mt-4 space-y-3">
          <p className={styles.help}>تاریخ‌ها را شمسی مانند ۱۴۰۵/۰۷/۲۸ وارد کنید. برای نوع چک «دریافتنی» یا «پرداختنی»، وضعیت «باز»، «تسویه»، «وصول»، «برگشتی»، «لغو» یا «سررسید گذشته»، و نوع حساب «بانک» یا «صندوق» بنویسید. احتمال وصول بین صفر تا صد است. نوع گزارش ماهانه «عملکرد» یا «بودجه» است. مقادیر صفر را صریح وارد کنید؛ مقدار خالی، صفر فرض نمی‌شود.</p>
          {manualRows.map((row,index)=><fieldset key={index} disabled={busy} className="rounded-xl border border-white/10 p-3"><legend className="px-2 text-xs">ردیف {(index+1).toLocaleString("fa-IR")}</legend><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{manualHeaders.map((header,column)=><label key={header} className={styles.field}>{header}<input value={row[column]||""} maxLength={2000} className={fieldClass} onChange={e=>{setManualRows(current=>current.map((old,i)=>i===index?old.map((cell,j)=>j===column?e.target.value:cell):old));setPreview(null);}}/></label>)}</div>{(manualRows.length>1||invoice)&&<button type="button" onClick={()=>{setManualRows(manualRows.filter((_,i)=>i!==index));setPreview(null);}} className="mt-3 text-xs text-rose-300">حذف ردیف پیش‌نویس</button>}</fieldset>)}
          {!manualRows.length&&invoice&&<p className={styles.warning}>گزارش بدون فاکتور است؛ خالی‌بودن تمام بازهٔ اعلام‌شده را پیش از تأیید بررسی کنید.</p>}
          <button type="button" disabled={busy||manualRows.length>=500||!manualHeaders.length} onClick={()=>{setManualRows([...manualRows,manualHeaders.map(()=>"")]);setPreview(null);}} className={styles.secondary}>افزودن ردیف دستی</button>
        </div>}
        <button className={`${primaryButton} mt-3`} disabled={busy || (inputMode==="excel"?!file:!manualHeaders.length)}>اعتبارسنجی و پیش‌نمایش</button>
      </form>
    </Surface>
    {preview && <Surface className={styles.panel}><header><h3>{preview.title} · {preview.status === "committed" ? "ثبت‌شده" : "پیش‌نمایش"}</h3>{preview.status === "preview" && <button className={primaryButton} disabled={busy} onClick={() => void commit()}>تأیید و ثبت گزارش</button>}</header><p className={styles.warning}>{preview.effects}</p><p className={styles.help}>{fa(preview.row_count)} ردیف؛ نمایش ردیف‌های {fa(Math.min(preview.row_count,(preview.offset ?? 0)+1))} تا {fa(Math.min(preview.row_count,(preview.offset ?? 0)+preview.rows.length))}. همهٔ ردیف‌ها قبل از ثبت اعتبارسنجی می‌شوند. {preview.source_note}</p><div className={styles.buttons}><button disabled={(preview.offset ?? 0) === 0} className={styles.secondary} onClick={() => void openReport(preview.id,Math.max(0,(preview.offset ?? 0)-100))}>صفحهٔ قبل</button><button disabled={(preview.offset ?? 0)+preview.rows.length >= preview.row_count} className={styles.secondary} onClick={() => void openReport(preview.id,(preview.offset ?? 0)+100)}>صفحهٔ بعد</button><button className={styles.secondary} onClick={() => void download(`/treasury/excel/reports/${preview.id}/export`,`treasury-report-${preview.id}.csv`)}>دریافت همهٔ ردیف‌ها</button></div><label className={styles.field}>جست‌وجو در ردیف‌های همین صفحه<input className={fieldClass} value={search} onChange={e => setSearch(e.target.value)} /></label><div className={styles.tableWrap} tabIndex={0}><table><thead><tr>{preview.headers.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{preview.rows.filter(r => matchesSearch(search,...r)).map((r, i) => <tr key={i}>{r.map((v, n) => <td key={n}>{v == null ? "—" : String(v)}</td>)}</tr>)}</tbody></table></div></Surface>}
    <Surface className={styles.panel}><header><h3>گزارش‌های بارگذاری‌شده</h3></header><div className={styles.tableWrap} tabIndex={0}><table><thead><tr>{["عنوان", "نوع", "ردیف", "واحد ورودی", "زمان تهران", "وضعیت", "مشاهده"].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{reports.map(r => <tr key={r.id}><td>{r.title}</td><td>{KINDS.find(k => k[0] === r.kind)?.[1]}</td><td>{fa(Number(r.row_count))}</td><td>{r.input_unit === "IRR" ? "ریال" : "تومان"}</td><td>{formatIranDateTime(r.created_at)}</td><td>{r.status === "committed" ? "ثبت‌شده" : "منتظر تأیید"}</td><td><button className={styles.secondary} onClick={() => void openReport(r.id)}>بازکردن</button></td></tr>)}</tbody></table></div>{!reports.length && <p className={styles.empty}>هنوز گزارشی بارگذاری نشده است.</p>}</Surface>
    {estimate && <Surface className={styles.panel}><header><h3>برآورد مستقل فاکتورهای اکسل</h3></header><p className={styles.help}>گزارش‌های خرید، فروش و دو نوع برگشت باید هم‌بازه باشند؛ با فاکتورهای هلو جمع نمی‌شوند. بهای ابتدای دوره و پیوند برگشت‌ها همچنان باید بررسی شوند.</p><ul>{estimate.provenance.map(p => <li key={p.kind}>{KINDS.find(k => k[0] === p.kind)?.[1]}: {p.title}</li>)}</ul><div className={styles.tableWrap} tabIndex={0}><table><thead><tr>{["ماه", "فروش خالص", "تخفیف خرید", "بودجهٔ هزینهٔ بازه", "برآورد سود پس از بودجه"].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{estimate.estimate.months.map(m => <tr key={m.month}><td>{m.month.replace("-", "/")}</td><td>{money(m.net_sales_irr)}</td><td>{money(m.purchase_discount_irr)}</td><td>{money(m.budget_expense_for_period_irr)}</td><td>{money(m.estimated_net_profit_irr)}</td></tr>)}</tbody></table></div><p className={styles.warning}>این برآورد، گزارش واقعی تأییدشده نیست؛ دیتای ناقص به‌صورت سود صفر نمایش داده نمی‌شود.</p></Surface>}
  </>;
}
