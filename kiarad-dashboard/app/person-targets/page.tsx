"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { DataEntryLink } from "../../components/data-entry-link";
import { PortalShell } from "../../components/portal-shell";
import { authFetch, secureApi } from "../../lib/secure-api";
import { IranDateInput } from "../../components/IranDateInput";
import { displayMoney, inputMoney, type MoneyUnit } from "../../lib/payroll-contract";

type Target = {
  id: number;
  title: string;
  target_amount: number;
  target_type: string;
  product_focus?: string;
  period_type?: string;
  start_date?: string;
  end_date?: string;
  status: string;
  salesperson_id?: number;
  salesperson_name?: string;
  bonus_reward?: number;
  month?: number;
  year?: number;
};

type SP = { id: number; name: string };
type TargetDraft = Omit<Partial<Target>, "target_amount" | "salesperson_id" | "bonus_reward"> & {
  _new?: boolean;
  target_amount: number | string;
  salesperson_id?: number | string;
  bonus_reward?: number | string;
};

const toman = (n?: number) => new Intl.NumberFormat("fa-IR").format(Math.round((n || 0) / 10)) + " تومان";

export default function PersonTargetsPage() {
  const [items, setItems] = useState<Target[]>([]);
  const [sps, setSps] = useState<SP[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [formError, setFormError] = useState("");
  const [editing, setEditing] = useState<TargetDraft | null>(null);
  const [unit, setUnit] = useState<MoneyUnit>("rial");
  const [saving, setSaving] = useState(false);
  const [filterSp, setFilterSp] = useState<string>("");
  const [role, setRole] = useState("");
  const [managerDataReady, setManagerDataReady] = useState(false);
  const [canWrite, setCanWrite] = useState(false);
  const draftLoaded = useRef(false);
  const managerRole = role === "ceo" || role === "sales_manager";
  const canManageTargets = managerRole && canWrite;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [targets, options] = await Promise.allSettled([
        secureApi<{items: Target[]}>("/targets/person-targets" + (managerRole && filterSp ? "?salesperson_id=" + filterSp : "")),
        managerRole ? secureApi<{salespersons: SP[]; can_write: boolean}>("/targets/person-targets/options") : Promise.resolve(null),
      ]);
      if (targets.status === "fulfilled") {
        setItems(targets.value.items || []);
      } else {
        setMsg(targets.reason instanceof Error ? targets.reason.message : "فهرست تارگت‌ها دریافت نشد.");
      }
      if (options.status === "fulfilled" && options.value) {
        setSps(options.value.salespersons);
        setCanWrite(options.value.can_write);
        setManagerDataReady(true);
      } else if (options.status === "rejected") {
        setCanWrite(false);
        setMsg(options.reason instanceof Error ? options.reason.message : "گزینه‌های ثبت تارگت دریافت نشد.");
      }
    } finally {
      setLoading(false);
    }
  }, [managerRole, filterSp]);

  useEffect(() => {
    authFetch("/auth/me").then((response) => response.ok ? response.json() : null).then((user) => setRole(user?.role || "")).catch(() => setRole("visitor"));
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  useEffect(() => {
    if (!canManageTargets || !managerDataReady || draftLoaded.current || loading) return;
    const raw = new URLSearchParams(window.location.search).get("assistant_draft");
    if (!raw) return;
    let active = true;
    void Promise.resolve().then(() => {
    if (!active || draftLoaded.current) return;
    draftLoaded.current = true;
    try {
      if (raw.length > 3000) throw new Error("invalid");
      const data: unknown = JSON.parse(raw);
      if (!data || typeof data !== "object") throw new Error("invalid");
      const d = data as Record<string, unknown>;
      const amount = Number(d.target_amount);
      const person = d.salesperson_id === null ? "" : Number(d.salesperson_id);
      if (!Number.isFinite(amount) || amount <= 0 || amount > 1e15 || (person !== "" && !sps.some(s => s.id === person))) throw new Error("invalid");
      if (typeof d.title !== "string" || typeof d.start_date !== "string" || typeof d.end_date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(d.start_date) || !/^\d{4}-\d{2}-\d{2}$/.test(d.end_date) || d.start_date > d.end_date) throw new Error("invalid");
      setUnit("rial");
      setFormError("");
      setEditing({_new:true,title:d.title.slice(0,160),target_amount:amount,salesperson_id:person,start_date:d.start_date,end_date:d.end_date,
        period_type:typeof d.period_type === "string" ? d.period_type.slice(0,50) : "",target_type:"ماهانه",product_focus:typeof d.product_focus === "string" ? d.product_focus.slice(0,150) : "",bonus_reward:0,status:"active"});
      setMsg("پیش‌نویس دستیار؛ هنوز ذخیره نشده. مبلغ به ریال، فرد یا شرکت و بازه را بازبینی کنید.");
    } catch {
      setMsg("پیش‌نویس معتبر نیست؛ تارگت را دستی وارد کنید.");
    }
    });
    return () => { active = false; };
  }, [canManageTargets, managerDataReady, loading, sps]);

  const openNew = () => {
    setUnit("rial");
    setFormError("");
    setEditing({
      _new: true,
      title: "",
      target_amount: "",
      target_type: "ماهانه",
      product_focus: "",
      period_type: "",
      salesperson_id: filterSp || sps[0]?.id || "",
      status: "active",
      bonus_reward: "",
      start_date: "",
      end_date: "",
    });
  };

  const save = async () => {
    if (!editing || saving) return;
    const amount = inputMoney(String(editing.target_amount), unit);
    const bonus = inputMoney(String(editing.bonus_reward ?? ""), unit) || "0";
    const validMoney = /^\d+(?:\.\d{1,2})?$/;
    if (!editing.title?.trim() || editing.title.trim().length < 2) {
      setFormError("عنوان تارگت را کامل وارد کنید.");
      return;
    }
    if (!validMoney.test(amount) || Number(amount) <= 0 || !validMoney.test(bonus)) {
      setFormError("مبلغ تارگت باید عدد مثبت و پاداش عددی صفر یا بیشتر باشد.");
      return;
    }
    if (!editing.start_date || !editing.end_date || editing.start_date > editing.end_date) {
      setFormError("تاریخ شمسی شروع و پایان را کامل وارد کنید. پایان نباید پیش از شروع باشد.");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      const isNew = !!editing._new;
      const url = isNew ? "/targets/person-targets" : "/targets/person-targets/" + editing.id;
      await secureApi(url, {
        method: isNew ? "POST" : "PATCH",
        body: JSON.stringify({
          title: editing.title.trim(), target_amount: amount, bonus_reward: bonus,
          salesperson_id: editing.salesperson_id ? Number(editing.salesperson_id) : null,
          start_date: editing.start_date, end_date: editing.end_date,
          target_type: editing.target_type || "ماهانه", status: editing.status || "active",
          period_type: editing.period_type || "", product_focus: editing.product_focus || "",
        }),
      });
      setMsg("تارگت ذخیره شد.");
      setEditing(null);
      void load();
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : "ذخیرهٔ تارگت انجام نشد.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("حذف این تارگت؟")) return;
    try {
      const r = await authFetch("/targets/person-targets/" + id, { method: "DELETE" });
      if (r.ok) load();
    } catch {}
  };

  const toggleStatus = async (t: Target) => {
    const newStatus = t.status === "active" ? "archived" : "active";
    try {
      await authFetch("/targets/person-targets/" + t.id, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      load();
    } catch {}
  };

  return (
    <PortalShell title="تارگت فردی" eyebrow="تارگت و پاداش هر ویزیتور">
      {canManageTargets&&<div className="mb-4"><DataEntryLink entity="targets"/></div>}
<div className="kskin">
        <div className="mb-4 rounded-xl border border-violet-400/20 bg-violet-500/[0.06] p-4">
          <b className="text-sm text-white">🎯 تارگت‌های فردی</b>
          <p className="mt-2 text-[11px] text-slate-400">
            {canManageTargets ? "برای ویزیتورها تارگت تعریف و پیگیری کن." : "تارگت‌ها و میزان تحقق فروش خودت را ببین."}
          </p>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          {canManageTargets ? <select value={filterSp} onChange={(e) => setFilterSp(e.target.value)} className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white">
            <option value="">همه‌ی ویزیتورها</option>
            {sps.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select> : null}
          {canManageTargets ? <button onClick={openNew} className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500">+ تارگت جدید</button> : null}
          <button onClick={load} className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-xs text-white">🔄 بروزرسانی</button>
          {msg && <span className="text-xs text-violet-200">{msg}</span>}
        </div>

        {loading ? (
          <div className="p-8 text-center text-xs text-slate-500">در حال بارگذاری...</div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl border border-white/[0.06] bg-[#0f1222] p-8 text-center text-xs text-slate-500">
            {canManageTargets ? "هنوز تارگتی ثبت نشده — اولین تارگت را اضافه کن." : "برای حساب شما هنوز تارگتی ثبت نشده است."}
          </div>
        ) : (
          <div className="grid gap-3">
            {items.map((t) => (
              <div key={t.id} className="rounded-2xl border border-white/[0.06] bg-[#0f1222] p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <b className="text-sm text-white">{t.title || "بدون عنوان"}</b>
                      <span className={"rounded-full px-2 py-0.5 text-[10px] " + (t.status === "active" ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-500/15 text-slate-400")}>
                        {t.status === "active" ? "فعال" : "بایگانی"}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                      <div><span className="text-slate-500">ویزیتور: </span><b className="text-slate-200">{t.salesperson_name || "-"}</b></div>
                      <div><span className="text-slate-500">مبلغ: </span><b className="text-violet-300">{toman(t.target_amount)}</b></div>
                      <div><span className="text-slate-500">نوع: </span><b className="text-slate-200">{t.target_type || "-"}</b></div>
                      <div><span className="text-slate-500">دوره: </span><b className="text-slate-200">{t.period_type || "-"}</b></div>
                    </div>
                    {t.product_focus && <div className="mt-2 text-[11px] text-slate-400">🎁 کالای هدف: <b className="text-slate-200">{t.product_focus}</b></div>}
                    {t.bonus_reward ? <div className="mt-1 text-[11px] text-amber-300">💰 پاداش تحقق: {toman(t.bonus_reward)}</div> : null}
                  </div>
                  {canManageTargets ? <div className="flex gap-1">
                    <button onClick={() => {setUnit("rial"); setFormError(""); setEditing({ ...t });}} className="rounded-lg border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] text-violet-200">✏️</button>
                    <button onClick={() => toggleStatus(t)} className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-200">{t.status === "active" ? "📦" : "✅"}</button>
                    <button onClick={() => remove(t.id)} className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200">🗑️</button>
                  </div> : null}
                </div>
              </div>
            ))}
          </div>
        )}

        {canManageTargets && editing && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onClick={() => {if (!saving) setEditing(null);}}>
            <form className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0f1222] p-5" onClick={(e) => e.stopPropagation()} onSubmit={(e) => {e.preventDefault(); void save();}}>
              <h3 className="mb-4 text-sm font-bold text-white">{editing._new ? "افزودن تارگت" : "ویرایش تارگت"}</h3>
              <div className="grid max-h-[70vh] gap-3 overflow-y-auto">
                <label><span className="mb-1 block text-[10px] text-slate-400">عنوان</span>
                  <input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                <label><span className="mb-1 block text-[10px] text-slate-400">ویزیتور</span>
                  <select value={editing.salesperson_id} onChange={(e) => setEditing({ ...editing, salesperson_id: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white">
                    <option value="">کل شرکت</option>
                    {sps.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select></label>
                <label className="text-xs text-slate-400">واحد مبالغ
                  <select value={unit} onChange={(e) => {
                    const next = e.target.value as MoneyUnit;
                    setEditing({...editing,
                      target_amount: displayMoney(inputMoney(String(editing.target_amount), unit), next),
                      bonus_reward: displayMoney(inputMoney(String(editing.bonus_reward ?? ""), unit), next),
                    });
                    setUnit(next);
                  }} className="block w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white">
                    <option value="rial">ریال</option><option value="toman">تومان</option>
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <label><span className="mb-1 block text-[10px] text-slate-400">مبلغ تارگت ({unit === "rial" ? "ریال" : "تومان"})</span>
                    <input inputMode="decimal" value={editing.target_amount} onChange={(e) => setEditing({ ...editing, target_amount: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                  <label><span className="mb-1 block text-[10px] text-slate-400">پاداش ({unit === "rial" ? "ریال" : "تومان"})</span>
                    <input inputMode="decimal" value={editing.bonus_reward ?? ""} onChange={(e) => setEditing({ ...editing, bonus_reward: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <label><span className="mb-1 block text-[10px] text-slate-400">نوع تارگت</span>
                    <select value={editing.target_type} onChange={(e) => setEditing({ ...editing, target_type: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white">
                      <option value="ماهانه">ماهانه</option>
                      <option value="فروش">فروش</option>
                      <option value="تسویه">تسویه</option>
                      <option value="هفتگی">هفتگی</option>
                      <option value="کالای مانده">کالای مانده</option>
                      <option value="سودده">سودده</option>
                      <option value="کمپین">کمپین</option>
                      <option value="کوتاه‌مدت">کوتاه‌مدت</option>
                    </select></label>
                  <label><span className="mb-1 block text-[10px] text-slate-400">دوره</span>
                    <input value={editing.period_type || ""} onChange={(e) => setEditing({ ...editing, period_type: e.target.value })} placeholder="مثلاً: تا پایان شهریور" className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                </div>
                <label><span className="mb-1 block text-[10px] text-slate-400">کالای هدف (اختیاری)</span>
                  <input value={editing.product_focus || ""} onChange={(e) => setEditing({ ...editing, product_focus: e.target.value })} placeholder="مثلاً: شامپو ضد ریزش درمالیست" className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                <div className="grid grid-cols-2 gap-2">
                  <label><span className="mb-1 block text-[10px] text-slate-400">از تاریخ</span>
                    <IranDateInput value={editing.start_date || ""} onChange={(value) => setEditing({ ...editing, start_date: value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                  <label><span className="mb-1 block text-[10px] text-slate-400">تا تاریخ</span>
                    <IranDateInput value={editing.end_date || ""} onChange={(value) => setEditing({ ...editing, end_date: value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                </div>
              </div>
              {formError && <p role="alert" className="mt-3 rounded-lg bg-rose-500/15 p-3 text-xs text-rose-200">{formError}</p>}
              <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={() => setEditing(null)} disabled={saving} className="rounded-lg border border-white/10 px-4 py-2 text-xs text-slate-400">انصراف</button>
                <button type="submit" disabled={saving} className="rounded-lg bg-violet-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{saving ? "در حال ذخیره…" : "ذخیره"}</button>
              </div>
            </form>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
