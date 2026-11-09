"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi, getSavedUser } from "../../lib/secure-api";
import { formatIranDateTime } from "../../lib/iran-date";

type Variant = {
  variant_id: string | number;
  product_id?: string | number | null;
  title: string;
  holoo_code: string | null | "";
  selling_price?: number | null;
  seller_stock?: number | null;
  is_active?: boolean;
  last_sync_at?: string | null;
};
type HolooProduct = { code: string; name: string };
type QueuedMapping = { variant_id: string | number; holoo_code: string; title: string; confirmed_at: string };

const QUEUE_KEY = "kiarad_dk_mapping_queue";

/** Normalize Persian/Arabic characters and lowercase latin for matching. */
function norm(s: string): string {
  return (s || "")
    .replace(/ي/g, "ی").replace(/ك/g, "ک")
    .replace(/[ًٌٍَُِّْآأإئءۀة]/g, ch => (ch === "آ" || ch === "أ" || ch === "إ") ? "ا" : ch === "ۀ" || ch === "ة" ? "ه" : "")
    .replace(/[\u200c\u200f\u200e]/g, " ")
    .toLowerCase()
    .replace(/[^a-z0-9\u0600-\u06FF]+/g, " ")
    .trim();
}
function tokens(s: string): string[] {
  return norm(s).split(" ").filter(t => t.length > 1);
}
/** Latin tokens (likely brands / model codes) get extra weight. */
function latinTokens(s: string): string[] {
  return norm(s).split(" ").filter(t => /^[a-z0-9]+$/.test(t) && t.length > 1);
}

function similarity(variantTitle: string, productName: string): number {
  const vt = tokens(variantTitle), pt = tokens(productName);
  if (vt.length === 0 || pt.length === 0) return 0;
  const vSet = new Set(vt), pSet = new Set(pt);
  let overlap = 0;
  for (const t of vSet) if (pSet.has(t)) overlap += 1;
  const denom = Math.max(vSet.size, pSet.size) || 1;
  let score = overlap / denom;
  const vLatin = latinTokens(variantTitle), pLatin = new Set(latinTokens(productName));
  let latinHit = 0;
  for (const t of vLatin) if (pLatin.has(t)) latinHit += 1;
  if (vLatin.length > 0) score += (latinHit / vLatin.length) * 0.5;
  if (overlap > 0 && overlap === Math.min(vSet.size, pSet.size)) score += 0.1;
  return Math.max(0, Math.min(1, score));
}

function topCandidates(title: string, products: HolooProduct[]): Array<{ p: HolooProduct; score: number }> {
  return products
    .map(p => ({ p, score: similarity(title, p.name) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);
}

export default function DigikalaMappingPage() {
  const user = getSavedUser();
  const allowed = user?.role === "ceo";

  const [variants, setVariants] = useState<Variant[]>([]);
  const [products, setProducts] = useState<HolooProduct[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [queue, setQueue] = useState<QueuedMapping[]>([]);
  const [choices, setChoices] = useState<Record<string, string>>({}); // variant key -> holoo code
  const [searches, setSearches] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const loadQueue = useCallback(function () {
    try {
      const raw = window.localStorage.getItem(QUEUE_KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      setQueue(Array.isArray(parsed) ? parsed as QueuedMapping[] : []);
    } catch { setQueue([]); }
  }, []);

  const load = useCallback(function () {
    secureApi<unknown>("/digikala/variants")
      .then(v => {
        const arr = Array.isArray(v) ? v
          : (v && typeof v === "object" && Array.isArray((v as Record<string, unknown>).items) ? (v as { items: Variant[] }).items : []);
        setVariants(arr.map(x => (x && typeof x === "object" ? x as Variant : { variant_id: "", title: "", holoo_code: "" })));
        setError("");
      })
      .catch(r => setError(r instanceof Error ? r.message : "دریافت متغیرهای دیجی‌کالا ناموفق بود."));
  }, []);

  useEffect(function () {
    if (!allowed) return;
    load();
    secureApi<unknown>("/catalog/products")
      .then(v => {
        loadQueue();
        const arr = Array.isArray(v) ? v
          : (v && typeof v === "object" && Array.isArray((v as Record<string, unknown>).items) ? (v as { items: HolooProduct[] }).items : []);
        setProducts(arr.map(p => (p && typeof p === "object" ? p as HolooProduct : { code: "", name: "" })));
      })
      .catch(() => { loadQueue(); });
  }, [allowed, load, loadQueue]);

  function persistQueue(next: QueuedMapping[]) {
    setQueue(next);
    try { window.localStorage.setItem(QUEUE_KEY, JSON.stringify(next)); } catch { /* storage full or unavailable */ }
  }

  const unmapped = useMemo(() => variants.filter(v => !v.holoo_code), [variants]);
  const mapped = useMemo(() => variants.filter(v => v.holoo_code), [variants]);

  function candidatesFor(v: Variant) {
    const q = (searches[keyOf(v)] || "").trim();
    if (q) {
      const needle = norm(q);
      return products.filter(p => norm(p.name).includes(needle)).slice(0, 20).map(p => ({ p, score: similarity(v.title, p.name) }));
    }
    return topCandidates(v.title, products);
  }

  function keyOf(v: Variant): string { return String(v.variant_id); }

  async function confirmMapping(v: Variant) {
    const code = choices[keyOf(v)];
    if (!code) { setError("ابتدا کالای هلو را انتخاب کن."); return; }
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      let applied = false;
      try {
        await secureApi(`/digikala/variants/${encodeURIComponent(keyOf(v))}/mapping`, { method: "PATCH", body: JSON.stringify({ holoo_code: code }) });
        applied = true;
      } catch { /* بدون پاسخ سرور فقط صف محلی معنا دارد */ }
      const entry: QueuedMapping = { variant_id: v.variant_id, holoo_code: code, title: v.title, confirmed_at: new Date().toISOString() };
      persistQueue([entry, ...queue.filter(q => String(q.variant_id) !== String(v.variant_id))]);
      setNotice(applied
        ? `نگاشت «${v.title}» روی سرور ثبت شد و در صف محلی هم ماند (برای CSV).`
        : `ثبت روی سرور ناموفق بود؛ نگاشت «${v.title}» فقط در صف محلی ماند (CSV قابل کپی).`);
    } finally { setBusy(false); }
  }

  function copyCsv() {
    const header = "supplier_code,holoo_code";
    const rows = queue.map(q => `${String(q.variant_id).replace(/[",\n]/g, " ")},${q.holoo_code}`);
    const csv = [header, ...rows].join("\n");
    void navigator.clipboard.writeText(csv)
      .then(() => setNotice("CSV در کلیپ‌بورد کپی شد."))
      .catch(() => setError("کپی در کلیپ‌بورد ناموفق بود؛ محتوا را دستی کپی کن."));
  }

  function removeFromQueue(q: QueuedMapping) {
    persistQueue(queue.filter(x => String(x.variant_id) !== String(q.variant_id)));
  }

  if (!allowed) return <PortalShell title="نگاشت کالاهای دیجی‌کالا" eyebrow="فروش آنلاین">
    <div className="mx-auto max-w-3xl p-6"><Surface className="p-6 text-center">
      <p className="text-sm text-amber-300">دسترسی مدیریتی لازم است</p>
      <p className="mt-2 text-xs text-slate-400">این صفحه فقط برای نقش مدیرعامل (ceo) فعال است.</p>
    </Surface></div>
  </PortalShell>;

  return <PortalShell title="نگاشت کالاهای دیجی‌کالا" eyebrow="فروش آنلاین">
    <div className="mx-auto max-w-6xl space-y-5 p-4 lg:p-6">
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      {notice && <p className="text-emerald-300">{notice}</p>}
      <Surface className="space-y-2 p-5 text-sm">
        <h2 className="text-base font-bold text-white">این صفحه چطور کار می‌کند؟ (دو مرحله)</h2>
        <ol className="list-inside list-decimal space-y-1 text-slate-300">
          <li><b className="text-white">مرحله ۱ — تأیید نگاشت‌ها اینجا:</b> نگاشت‌های تأییدشده در «صف محلی» همین مرورگر ذخیره می‌شوند و هنوز روی سایت اعمال نمی‌شوند.</li>
          <li><b className="text-white">مرحله ۲ — اعمال نهایی:</b> با تأیید هر ردیف، نگاشت مستقیماً روی سرور ثبت می‌شود؛ خروجی CSV هم برای جریان دستی اکسل باقی مانده است.</li>
        </ol>
      </Surface>

      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">نگاشت‌های در انتظار اعمال ({queue.length.toLocaleString("fa-IR")})</h2>
        {queue.length === 0
          ? <p className="text-sm text-slate-400">صف خالی است.</p>
          : <>
              <ul className="space-y-1 text-xs text-slate-300">
                {queue.map(q => <li key={String(q.variant_id)} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 px-3 py-2">
                  <span><b className="text-white">{q.title}</b> <span className="text-slate-500">← {q.holoo_code}</span></span>
                  <span className="flex items-center gap-3 text-[10px] text-slate-500">
                    {formatIranDateTime(q.confirmed_at)}
                    <button className="text-rose-300" onClick={() => removeFromQueue(q)}>حذف</button>
                  </span>
                </li>)}
              </ul>
              <button className={primaryButton} onClick={copyCsv}>کپی CSV نگاشت‌ها برای مدیر فنی (variant_map.csv)</button>
            </>}
      </Surface>

      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">متغیرهای نگاشت‌نشده ({unmapped.length.toLocaleString("fa-IR")})</h2>
        {unmapped.length === 0
          ? <p className="text-sm text-slate-400">همهٔ متغیرها نگاشت شده‌اند.</p>
          : <div className="space-y-3">
              {unmapped.map(v => {
                const cands = candidatesFor(v);
                const current = choices[keyOf(v)] ?? (cands[0]?.p.code || "");
                return <div key={keyOf(v)} className="rounded-xl border border-white/10 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <b className="text-sm text-white">{v.title || "(بدون عنوان)"}</b>
                    <span className="flex gap-2 text-[10px] text-slate-400">
                      <span className="rounded-full bg-white/10 px-2 py-0.5">قیمت: {(v.selling_price ?? 0).toLocaleString("fa-IR")}</span>
                      <span className="rounded-full bg-white/10 px-2 py-0.5">موجودی: {(v.seller_stock ?? 0).toLocaleString("fa-IR")}</span>
                    </span>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <select className={fieldClass} value={current} onChange={e => setChoices({ ...choices, [keyOf(v)]: e.target.value })}>
                      <option value="">— انتخاب کالای هلو —</option>
                      {cands.map(({ p, score }) => <option key={p.code} value={p.code}>{p.name} ({p.code}) — {(score * 100).toFixed(0)}٪</option>)}
                    </select>
                    <input className={fieldClass} value={searches[keyOf(v)] ?? ""} onChange={e => setSearches({ ...searches, [keyOf(v)]: e.target.value })} placeholder="جست‌وجوی آزاد در کالاهای هلو…"/>
                    <button className={primaryButton} disabled={busy || !current} onClick={() => void confirmMapping(v)}>تأیید نگاشت و افزودن به صف محلی</button>
                  </div>
                </div>;
              })}
            </div>}
      </Surface>

      <Surface className="space-y-3 p-5">
        <h2 className="text-base font-bold">متغیرهای نگاشت‌شده ({mapped.length.toLocaleString("fa-IR")})</h2>
        {mapped.length === 0
          ? <p className="text-sm text-slate-400">موردی نگاشت‌شده نیست.</p>
          : <div className="overflow-x-auto">
              <table className="w-full min-w-[700px] text-right text-xs">
                <thead className="text-slate-400">
                  <tr className="border-b border-white/10">
                    <th className="p-2 font-medium">عنوان</th>
                    <th className="p-2 font-medium">کد هلو</th>
                    <th className="p-2 font-medium">قیمت</th>
                    <th className="p-2 font-medium">موجودی</th>
                    <th className="p-2 font-medium">آخرین همگام‌سازی</th>
                  </tr>
                </thead>
                <tbody>
                  {mapped.map(v => <tr key={keyOf(v)} className="border-b border-white/[0.05] text-slate-200">
                    <td className="p-2 font-medium text-white">{v.title || "—"}</td>
                    <td className="p-2">{v.holoo_code}</td>
                    <td className="p-2">{v.selling_price === null || v.selling_price === undefined ? "—" : v.selling_price.toLocaleString("fa-IR")}</td>
                    <td className="p-2">{v.seller_stock === null || v.seller_stock === undefined ? "—" : v.seller_stock.toLocaleString("fa-IR")}</td>
                    <td className="p-2 text-[10px] text-slate-400">{v.last_sync_at ? formatIranDateTime(v.last_sync_at) : "—"}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>}
      </Surface>

      <a href="/platforms" className="block text-violet-300">بازگشت به مدیریت سکوهای فروش</a>
    </div>
  </PortalShell>;
}
