"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
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

export default function DigikalaStock() {
  const [variants, setVariants] = useState<Variant[]>([]);
  const [products, setProducts] = useState<HolooProduct[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [choices, setChoices] = useState<Record<string, string>>({}); // variant key -> holoo code
  const [searches, setSearches] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

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
    load();
    secureApi<unknown>("/catalog/products")
      .then(v => {
        const arr = Array.isArray(v) ? v
          : (v && typeof v === "object" && Array.isArray((v as Record<string, unknown>).items) ? (v as { items: HolooProduct[] }).items : []);
        setProducts(arr.map(p => (p && typeof p === "object" ? p as HolooProduct : { code: "", name: "" })));
      })
      .catch(() => setError("فهرست کالاهای هلو دریافت نشد."));
  }, [load]);

  const unmapped = useMemo(() => variants.filter(v => !v.holoo_code), [variants]);
  const mapped = useMemo(() => variants.filter(v => v.holoo_code), [variants]);

  function candidatesFor(v: Variant) {
    const q = (searches[keyOf(v)] || "").trim();
    if (q) {
      const needle = norm(q);
      return products.filter(p => norm(p.name).includes(needle) || p.code.includes(q)).slice(0, 20).map(p => ({ p, score: similarity(v.title, p.name) }));
    }
    return topCandidates(v.title, products);
  }

  function keyOf(v: Variant): string { return String(v.variant_id); }

  async function apply(v: Variant, code?: string) {
    setBusy(true); setError(""); setNotice("");
    try {
      const path = `/digikala/variants/${encodeURIComponent(keyOf(v))}`;
      if (code) {
        await secureApi(`${path}/mapping`, { method: "PATCH", body: JSON.stringify({ holoo_code: code }) });
        setNotice("اتصال کالا به هلو ثبت شد.");
      } else {
        const result = await secureApi<{ new_stock: number }>(`${path}/sync-stock`, { method: "POST" });
        setNotice(`موجودی دیجی‌کالا به ${result.new_stock.toLocaleString("fa-IR")} به‌روز شد.`);
      }
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "به‌روزرسانی انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="space-y-4">
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      {notice && <p role="status" className="text-emerald-300">{notice}</p>}
      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">متغیرهای نگاشت‌نشده ({unmapped.length.toLocaleString("fa-IR")})</h2>
        {unmapped.length === 0
          ? <p className="text-sm text-slate-400">همهٔ متغیرها نگاشت شده‌اند.</p>
          : <div className="space-y-3">
              {unmapped.map(v => {
                const cands = candidatesFor(v);
                const current = choices[keyOf(v)] ?? "";
                return <div key={keyOf(v)} className="rounded-xl border border-white/10 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <b className="text-sm text-white">{v.title || "(بدون عنوان)"}</b>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <select className={fieldClass} value={current} onChange={e => setChoices({ ...choices, [keyOf(v)]: e.target.value })}>
                      <option value="">— انتخاب کالای هلو —</option>
                      {cands.map(({ p, score }) => <option key={p.code} value={p.code}>{p.name} ({p.code}) — {(score * 100).toFixed(0)}٪</option>)}
                    </select>
                    <input className={fieldClass} value={searches[keyOf(v)] ?? ""} onChange={e => setSearches({ ...searches, [keyOf(v)]: e.target.value })} placeholder="جست‌وجوی آزاد در کالاهای هلو…"/>
                    <button className={primaryButton} disabled={busy || !current} onClick={() => void apply(v, current)}>ثبت اتصال به هلو</button>
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
                    <th className="p-2 font-medium">موجودی</th>
                    <th className="p-2 font-medium">آخرین به‌روزرسانی</th>
                    <th className="p-2 font-medium">عملیات</th>
                  </tr>
                </thead>
                <tbody>
                  {mapped.map(v => <tr key={keyOf(v)} className="border-b border-white/[0.05] text-slate-200">
                    <td className="p-2 font-medium text-white">{v.title || "—"}</td>
                    <td className="p-2">{v.holoo_code}</td>
                    <td className="p-2">{v.seller_stock === null || v.seller_stock === undefined ? "—" : v.seller_stock.toLocaleString("fa-IR")}</td>
                    <td className="p-2 text-[10px] text-slate-400">{v.last_sync_at ? formatIranDateTime(v.last_sync_at) : "—"}</td>
                    <td className="p-2"><button className={primaryButton} disabled={busy || !v.is_active} onClick={() => void apply(v)}>ارسال موجودی داشبورد</button></td>
                  </tr>)}
                </tbody>
              </table>
            </div>}
      </Surface>

    </div>;
}
