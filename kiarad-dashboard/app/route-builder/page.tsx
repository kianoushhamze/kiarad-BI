"use client";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi, getSavedUser } from "../../lib/secure-api";

const FA_DIGITS = ["۰","۱","۲","۳","۴","۵","۶","۷","۸","۹"];
function faNum(n: number | string): string {
  return String(n).replace(/\d/g, d => FA_DIGITS[Number(d)]);
}

type Physician = {
  id?: number | string;
  name?: string;
  level?: string;
  specialty?: string;
  city?: string;
};

function asArray(v: unknown): unknown[] {
  if (Array.isArray(v)) return v;
  if (v && typeof v === "object") {
    const obj = v as Record<string, unknown>;
    for (const key of ["routes", "items", "data", "results", "members", "physicians", "list"]) {
      if (Array.isArray(obj[key])) return obj[key] as unknown[];
    }
  }
  return [];
}

function textOf(v: unknown): string {
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    for (const key of ["name", "label", "title", "full_name", "city", "value", "text"]) {
      if (typeof o[key] === "string") return o[key];
    }
  }
  return "";
}

function chipOf(v: unknown, i: number): string {
  const t = textOf(v);
  return t || "عضو " + faNum(i + 1);
}

/** Renders a scalar or nested value defensively as simple UI. */
function ValueBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    return <span>{faNum(String(value))}</span>;
  if (Array.isArray(value))
    return <div className="flex flex-wrap gap-1.5">
      {value.map((v, i) => <span key={i} className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] text-slate-200">{chipOf(v, i)}</span>)}
    </div>;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v !== null && v !== undefined && v !== "");
    if (entries.length === 0) return null;
    return <ul className="space-y-0.5 text-[11px] text-slate-300">
      {entries.map(([k, v]) => <li key={k}><span className="text-slate-500">{k}:</span> {Array.isArray(v) ? `(${v.length.toLocaleString("fa-IR")} مورد)` : faNum(String(v))}</li>)}
    </ul>;
  }
  return null;
}

export default function RouteBuilderPage() {
  const user = getSavedUser();
  const allowed = user?.role === "ceo";

  const [kind, setKind] = useState<"bases" | "physicians">("bases");
  const [perRoute, setPerRoute] = useState(10);
  const [session, setSession] = useState<"صبح" | "عصر">("صبح");
  const [city, setCity] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState<unknown>(null);
  const [routes, setRoutes] = useState<unknown[]>([]);

  // physicians section
  const [physicians, setPhysicians] = useState<Physician[]>([]);
  const [fLevel, setFLevel] = useState("");
  const [fCity, setFCity] = useState("");
  const [fQ, setFQ] = useState("");

  const loadPhysicians = useCallback(function (limit: number) {
    secureApi<unknown>(`/route-builder/physicians?limit=${limit}`)
      .then(v => {
        const arr = asArray(v);
        setPhysicians(arr.map(p => (p && typeof p === "object" ? p as Physician : {})));
        setError("");
      })
      .catch(r => setError(r instanceof Error ? r.message : "دریافت پزشکان ناموفق بود."));
  }, []);

  useEffect(function () {
    if (!allowed) return;
    loadPhysicians(200);
  }, [allowed, loadPhysicians]);

  async function suggest() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const body: Record<string, unknown> = {
        kind,
        per_route: Number(perRoute) || (kind === "bases" ? 10 : 6),
        session,
      };
      const trimmed = city.trim();
      if (trimmed) body.city = trimmed;
      const res = await secureApi<unknown>("/route-builder/suggest", { method: "POST", body: JSON.stringify(body) });
      // Defensive rendering: accept {summary, routes}, {items}, or a bare array.
      let foundRoutes: unknown[] = [];
      let foundSummary: unknown = null;
      if (res && typeof res === "object" && !Array.isArray(res)) {
        const obj = res as Record<string, unknown>;
        foundSummary = obj.summary ?? obj;
        if (Array.isArray(obj.routes)) foundRoutes = obj.routes;
        else if (Array.isArray(obj.cities)) {
          // پاسخ سرور بر پایهٔ شهر گروه‌بندی شده: مسیرهای همهٔ شهرها را تخت می‌کنیم
          foundRoutes = obj.cities.flatMap((c: unknown) => asArray((c as Record<string, unknown>)?.routes));
        }
        else if (Array.isArray(obj.items)) foundRoutes = obj.items;
        else if (Array.isArray(obj.data)) foundRoutes = obj.data;
        else if (Array.isArray(obj)) foundRoutes = obj;
      } else if (Array.isArray(res)) {
        foundRoutes = res;
        foundSummary = null;
      }
      // Each route may itself be a wrapper object; unwrap common keys.
      foundRoutes = foundRoutes.map(r => {
        if (r && typeof r === "object" && !Array.isArray(r)) {
          const o = r as Record<string, unknown>;
          const inner = o.route ?? o.routes ?? o.members ?? o.data;
          if (Array.isArray(inner) && Object.keys(o).length <= 4) return { ...o, members: inner };
        }
        return r;
      });
      setRoutes(foundRoutes);
      setSummary(foundSummary);
      if (foundRoutes.length === 0) setError("پاسخی با مسیرهای قابل نمایش برنگشت؛ ساختار پاسخ را بررسی کن.");
    } catch (r) {
      setError(r instanceof Error ? r.message : "دریافت پیشنهاد مسیرها ناموفق بود.");
      setRoutes([]); setSummary(null);
    } finally { setBusy(false); }
  }

  function renderSummary(): ReactNode {
    if (summary === null || summary === undefined) return null;
    if (typeof summary === "string") return <p className="text-xs text-slate-300">{summary}</p>;
    if (typeof summary === "object") {
      const entries = Object.entries(summary as Record<string, unknown>)
        .filter(([, v]) => v !== null && v !== undefined && v !== "");
      if (entries.length === 0) return null;
      return <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-300">
        {entries.map(([k, v]) => <span key={k}>
          <span className="text-slate-500">{k}: </span>
          <b className="text-white">{Array.isArray(v) ? v.length.toLocaleString("fa-IR") + " مورد" : faNum(String(v))}</b>
        </span>)}
      </div>;
    }
    return null;
  }

  function renderRoute(r: unknown, i: number) {
    const o = (r && typeof r === "object" ? r : {}) as Record<string, unknown>;
    const label = textOf(o.label) || textOf(o.name) || textOf(o.title) || `مسیر ${faNum(i + 1)}`;
    const rCity = textOf(o.city) || textOf(o.cities);
    const rSession = textOf(o.session);
    const members = asArray(o.members ?? o.stops ?? o.items ?? o.people ?? o.bases ?? o.physicians ?? o.list);
    const memberCount = typeof o.member_count === "number" ? o.member_count : members.length;
    return <div key={i} className="rounded-xl border border-white/10 p-4 print:break-inside-avoid">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <b className="text-sm text-white">{label}</b>
        <span className="flex flex-wrap gap-2 text-[10px]">
          {rCity && <span className="rounded-full bg-sky-500/15 px-2.5 py-1 text-sky-300">{rCity}</span>}
          {rSession && <span className="rounded-full bg-violet-500/15 px-2.5 py-1 text-violet-300">{rSession}</span>}
          <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-emerald-300">{faNum(memberCount)} عضو</span>
        </span>
      </div>
      {members.length > 0
        ? <div className="mt-3 flex flex-wrap gap-1.5">
            {members.map((m, j) => <span key={j} className="rounded-full bg-white/[0.07] px-2.5 py-1 text-[11px] text-slate-200">{chipOf(m, j)}</span>)}
          </div>
        : <div className="mt-3 text-xs text-slate-400">{Object.keys(o).length > 0
            ? Object.entries(o).filter(([k]) => !["label","name","title","city","cities","session","member_count"].includes(k)).map(([k, v], j) => <div key={j} className="mt-1"><span className="text-slate-500">{k}: </span><ValueBlock value={v} /></div>)
            : <p>بدون جزئیات.</p>}</div>}
    </div>;
  }

  const filteredPhysicians = physicians.filter(p => {
    if (fLevel.trim() && !(p.level ?? "").toLowerCase().includes(fLevel.trim().toLowerCase())) return false;
    if (fCity.trim() && !(p.city ?? "").includes(fCity.trim())) return false;
    if (fQ.trim() && !(p.name ?? "").includes(fQ.trim())) return false;
    return true;
  });

  if (!allowed) return <PortalShell title="مسیرسازی ویزیت" eyebrow="برنامه‌ریزی میدانی">
    <div className="mx-auto max-w-3xl p-6"><Surface className="p-6 text-center">
      <p className="text-sm text-amber-300">دسترسی مدیریتی لازم است</p>
      <p className="mt-2 text-xs text-slate-400">این صفحه فقط برای نقش مدیرعامل (ceo) فعال است.</p>
    </Surface></div>
  </PortalShell>;

  return <PortalShell title="مسیرسازی ویزیت" eyebrow="برنامه‌ریزی میدانی">
    <div className="mx-auto max-w-5xl space-y-5 p-4 lg:p-6">
      {error && <p role="alert" className="text-rose-300">{error}</p>}

      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">دریافت پیشنهاد مسیرها</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1 text-xs text-slate-400">نوع مسیر
            <div className="flex items-center gap-4 pt-1.5 text-xs text-white">
              <label className="flex items-center gap-1.5"><input type="radio" checked={kind === "bases"} onChange={() => { setKind("bases"); setPerRoute(10); }}/>پایگاه‌ها</label>
              <label className="flex items-center gap-1.5"><input type="radio" checked={kind === "physicians"} onChange={() => { setKind("physicians"); setPerRoute(6); }}/>پزشکان</label>
            </div></div>
          <label className="space-y-1 text-xs text-slate-400">تعداد در هر مسیر
            <input type="number" min={1} className={fieldClass} value={perRoute} onChange={e => setPerRoute(Number(e.target.value) || 1)}/></label>
          <div className="space-y-1 text-xs text-slate-400">شیفت
            <div className="flex items-center gap-4 pt-1.5 text-xs text-white">
              <label className="flex items-center gap-1.5"><input type="radio" checked={session === "صبح"} onChange={() => setSession("صبح")}/>صبح</label>
              <label className="flex items-center gap-1.5"><input type="radio" checked={session === "عصر"} onChange={() => setSession("عصر")}/>عصر</label>
            </div></div>
          <label className="space-y-1 text-xs text-slate-400">شهر (اختیاری)
            <input className={fieldClass} value={city} onChange={e => setCity(e.target.value)} placeholder="مثلاً کرمان"/></label>
        </div>
        <button className={primaryButton} disabled={busy} onClick={() => void suggest()}>
          {busy ? "در حال دریافت…" : "دریافت پیشنهاد مسیرها"}</button>
      </Surface>

      {summary !== null && <Surface className="space-y-3 p-5 print:border-none print:bg-transparent">
        <h2 className="text-base font-bold">خلاصه</h2>
        {renderSummary()}
      </Surface>}

      {routes.length > 0 && <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">مسیرهای پیشنهادی</h2>
        <div className="space-y-3">{routes.map((r, i) => renderRoute(r, i))}</div>
      </Surface>}

      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">پزشکان</h2>
        <p className="text-xs text-slate-400">ورود اطلاعات پزشکان از فایل JSONL در بک‌اند انجام می‌شود؛ این فهرست فقط برای مشاهده و فیلتر است.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <input className={fieldClass} value={fLevel} onChange={e => setFLevel(e.target.value)} placeholder="فیلتر سطح (level)"/>
          <input className={fieldClass} value={fCity} onChange={e => setFCity(e.target.value)} placeholder="فیلتر شهر"/>
          <input className={fieldClass} value={fQ} onChange={e => setFQ(e.target.value)} placeholder="جست‌وجوی نام"/>
        </div>
        {filteredPhysicians.length === 0
          ? <p className="text-sm text-slate-400">پزشکی برای نمایش نیست.</p>
          : <div className="overflow-x-auto">
              <table className="w-full min-w-[600px] text-right text-xs">
                <thead className="text-slate-400">
                  <tr className="border-b border-white/10">
                    <th className="p-2 font-medium">نام</th>
                    <th className="p-2 font-medium">سطح</th>
                    <th className="p-2 font-medium">تخصص</th>
                    <th className="p-2 font-medium">شهر</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPhysicians.map((p, i) => <tr key={p.id ?? i} className="border-b border-white/[0.05] text-slate-200">
                    <td className="p-2 font-medium text-white">{p.name ?? "—"}</td>
                    <td className="p-2">{p.level ?? "—"}</td>
                    <td className="p-2">{p.specialty ?? "—"}</td>
                    <td className="p-2">{p.city ?? "—"}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>}
      </Surface>
    </div>
  </PortalShell>;
}
