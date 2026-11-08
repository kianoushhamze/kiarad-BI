"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { DataEntryLink } from "../../components/data-entry-link";
import { PortalShell } from "../../components/portal-shell";
import { authFetch } from "../../lib/secure-api";
import { IranDateInput } from "../../components/IranDateInput";

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
  const [editing, setEditing] = useState<TargetDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [filterSp, setFilterSp] = useState<string>("");
  const [role, setRole] = useState("");
  const [managerDataReady, setManagerDataReady] = useState(false);
  const draftLoaded = useRef(false);
  const canManageTargets = role === "ceo" || role === "sales_manager";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        authFetch("/targets/person-targets" + (canManageTargets && filterSp ? "?salesperson_id=" + filterSp : "")),
        canManageTargets ? authFetch("/salespersons") : Promise.resolve(null),
      ]);
      if (r1.ok) {
        const d = await r1.json();
        setItems(d.items || []);
      }
      if (r2?.ok) {
        const d = await r2.json();
        setSps(d.salespersons || []);
        setManagerDataReady(true);
      }
    } catch {}
    setLoading(false);
  }, [canManageTargets, filterSp]);

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
    setEditing({
      _new: true,
      title: "",
      target_amount: "",
      target_type: "ماهانه",
      product_focus: "",
      period_type: "",
      salesperson_id: sps[0]?.id || "",
      status: "active",
      bonus_reward: "",
      start_date: "",
      end_date: "",
    });
  };

  const save = async () => {
    if (!editing) return;
    if (!editing.title?.trim() || !Number.isFinite(Number(editing.target_amount)) || Number(editing.target_amount) <= 0 || !editing.start_date || !editing.end_date || editing.start_date > editing.end_date) {
      setMsg("عنوان، مبلغ مثبت و بازهٔ شروع و پایان معتبر لازم است.");
      return;
    }
    setSaving(true);
    setMsg("");
    try {
      const payload: Record<string, unknown> = { ...editing };
      delete payload._new;
      delete payload.id;
      delete payload.salesperson_name;
      const asNumberOrNull = (value: number | string | undefined) => value === "" || value === undefined ? null : Number(value);
      payload.target_amount = Number(editing.target_amount);
      payload.salesperson_id = asNumberOrNull(editing.salesperson_id);
      payload.bonus_reward = asNumberOrNull(editing.bonus_reward);
      payload.month = asNumberOrNull(editing.month);
      payload.year = asNumberOrNull(editing.year);
      payload.start_date = editing.start_date || null;
      payload.end_date = editing.end_date || null;

      const isNew = !!editing._new;
      const url = isNew ? "/targets/person-targets" : "/targets/person-targets/" + editing.id;
      const method = isNew ? "POST" : "PATCH";
      const r = await authFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (r.ok) {
        setMsg("ذخیره شد ✓");
        setEditing(null);
        load();
      } else {
        const e = await r.json().catch(() => ({}));
        setMsg("خطا: " + (e.detail || r.status));
      }
    } catch (e: unknown) {
      setMsg("خطا: " + (e instanceof Error ? e.message : ""));
    }
    setSaving(false);
    setTimeout(() => setMsg(""), 4000);
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
                    <button onClick={() => setEditing({ ...t })} className="rounded-lg border border-violet-400/30 bg-violet-500/10 px-2 py-1 text-[10px] text-violet-200">✏️</button>
                    <button onClick={() => toggleStatus(t)} className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-200">{t.status === "active" ? "📦" : "✅"}</button>
                    <button onClick={() => remove(t.id)} className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200">🗑️</button>
                  </div> : null}
                </div>
              </div>
            ))}
          </div>
        )}

        {canManageTargets && editing && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" onClick={() => setEditing(null)}>
            <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#0f1222] p-5" onClick={(e) => e.stopPropagation()}>
              <h3 className="mb-4 text-sm font-bold text-white">{editing._new ? "افزودن تارگت" : "ویرایش تارگت"}</h3>
              <div className="grid max-h-[70vh] gap-3 overflow-y-auto">
                <label><span className="mb-1 block text-[10px] text-slate-400">عنوان</span>
                  <input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                <label><span className="mb-1 block text-[10px] text-slate-400">ویزیتور</span>
                  <select value={editing.salesperson_id} onChange={(e) => setEditing({ ...editing, salesperson_id: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white">
                    <option value="">کل شرکت</option>
                    {sps.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select></label>
                <div className="grid grid-cols-2 gap-2">
                  <label><span className="mb-1 block text-[10px] text-slate-400">مبلغ تارگت (ریال)</span>
                    <input type="number" value={editing.target_amount} onChange={(e) => setEditing({ ...editing, target_amount: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                  <label><span className="mb-1 block text-[10px] text-slate-400">پاداش (ریال)</span>
                    <input type="number" value={editing.bonus_reward} onChange={(e) => setEditing({ ...editing, bonus_reward: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white outline-none" /></label>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <label><span className="mb-1 block text-[10px] text-slate-400">نوع تارگت</span>
                    <select value={editing.target_type} onChange={(e) => setEditing({ ...editing, target_type: e.target.value })} className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-white">
                      <option value="ماهانه">ماهانه</option>
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
              <div className="mt-5 flex justify-end gap-2">
                <button onClick={() => setEditing(null)} className="rounded-lg border border-white/10 px-4 py-2 text-xs text-slate-400">انصراف</button>
                <button onClick={save} disabled={saving} className="rounded-lg bg-violet-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-50">{saving ? "..." : "ذخیره"}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
