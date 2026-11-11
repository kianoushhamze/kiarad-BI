"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";

type ProductRow = {
  code: string;
  name: string;
  price_irr: number | null;
  price_toman: number | null;
  discount_price_irr: number | null;
  discount_price_toman: number | null;
  effective_price_irr: number | null;
  effective_price_toman: number | null;
  stock: number | null;
  site_category: string | null;
  image_url: string | null;
  hidden: boolean;
};

type ProductsResponse = { count: number; hidden_count: number; products: ProductRow[] };

type Draft = { site_category: string; image_url: string; hidden: boolean; price_toman: string; discount_toman: string };

type Banner = { id: number; title: string; link_url: string | null; sort: number; active: boolean; image_url: string };

type OrderItem = { code: string; name: string; qty: number; unit_price_irr: number; line_total_irr: number };
type SiteOrder = {
  id: number; customer_id: number; customer_name: string; phone: string | null;
  city: string | null; address: string | null; items: OrderItem[];
  total_irr: number; status: string; created_at: string | null;
};
type OrdersResponse = { count: number; orders: SiteOrder[] };

const ORDER_STATUSES = ["جدید", "تأیید شده", "ارسال شد", "لغو شد"] as const;

const toman = (value: number | null) =>
  value === null || value === undefined ? "—" : value.toLocaleString("fa-IR");

export default function SiteCmsPage() {
  const [data, setData] = useState<ProductsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [hiddenFilter, setHiddenFilter] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [banners, setBanners] = useState<Banner[]>([]);
  const [orders, setOrders] = useState<SiteOrder[]>([]);
  const [bannerBusy, setBannerBusy] = useState(false);
  const [orderBusy, setOrderBusy] = useState<number | null>(null);
  const [bannerTitle, setBannerTitle] = useState("");
  const [bannerLink, setBannerLink] = useState("");
  const [bannerSort, setBannerSort] = useState("0");
  const [bannerActive, setBannerActive] = useState(true);
  const [bannerImage, setBannerImage] = useState<string>("");

  const loadBanners = useCallback(() => {
      return secureApi<{ count: number; banners: Banner[] }>("/site-cms/banners").then(result => {
      setBanners(result.banners ?? []);
      }).catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : "دریافت بنرها انجام نشد.");
      });
  }, []);

  const loadOrders = useCallback(() => {
      return secureApi<OrdersResponse>("/site-orders/all").then(result => {
      setOrders(result.orders ?? []);
      }).catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : "دریافت سفارش‌های سایت انجام نشد.");
      });
  }, []);

  const load = useCallback((q: string, hidden: string) => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (hidden) params.set("hidden", hidden);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return secureApi<ProductsResponse>(`/site-cms/products${suffix}`).then(result => {
      setData(result);
      setDrafts(Object.fromEntries((result.products ?? []).map(p => [p.code, {
        site_category: p.site_category ?? "",
        image_url: p.image_url ?? "",
        hidden: p.hidden,
        price_toman: p.price_toman === null ? "" : String(p.price_toman),
        discount_toman: p.discount_price_toman === null || p.discount_price_toman === undefined ? "" : String(p.discount_price_toman),
      }])));
      setMessage("");
      }).catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : "دریافت کالاهای سایت انجام نشد.");
      }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void load("", "");
    void loadBanners();
    void loadOrders();
  }, [load, loadBanners, loadOrders]);

  const onBannerFile = (file: File) => {
    if (file.size > 600 * 1024) {
      setMessage("حجم تصویر باید کمتر از ۶۰۰ کیلوبایت باشد.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setBannerImage(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  };

  const createBanner = async () => {
    if (!bannerImage) { setMessage("برای بنر، تصویر انتخاب کنید."); return; }
    setBannerBusy(true);
    try {
      await secureApi("/site-cms/banners", {
        method: "POST",
        body: JSON.stringify({
          title: bannerTitle,
          image_base64: bannerImage,
          link_url: bannerLink.trim() === "" ? null : bannerLink.trim(),
          sort: Number(bannerSort) || 0,
          active: bannerActive,
        }),
      });
      setBannerTitle(""); setBannerLink(""); setBannerSort("0"); setBannerImage("");
      setMessage("بنر ساخته شد.");
      await loadBanners();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ساخت بنر انجام نشد.");
    } finally {
      setBannerBusy(false);
    }
  };

  const patchBanner = async (id: number, patch: Record<string, unknown>) => {
    setBannerBusy(true);
    try {
      await secureApi(`/site-cms/banners/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
      await loadBanners();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ذخیرهٔ بنر انجام نشد.");
    } finally {
      setBannerBusy(false);
    }
  };

  const deleteBanner = async (id: number) => {
    setBannerBusy(true);
    try {
      await secureApi(`/site-cms/banners/${id}`, { method: "DELETE" });
      setMessage(`بنر ${id} حذف شد.`);
      await loadBanners();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "حذف بنر انجام نشد.");
    } finally {
      setBannerBusy(false);
    }
  };

  const setOrderStatus = async (id: number, status: string) => {
    setOrderBusy(id);
    try {
      await secureApi(`/site-orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setOrders(prev => prev.map(o => (o.id === id ? { ...o, status } : o)));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "تغییر وضعیت سفارش انجام نشد.");
    } finally {
      setOrderBusy(null);
    }
  };

  const setDraft = (code: string, patch: Partial<Draft>) =>
    setDrafts(prev => ({ ...prev, [code]: { ...prev[code], ...patch } }));

  const dirty = useMemo(() => {
    if (!data) return new Set<string>();
    const changed = new Set<string>();
    for (const p of data.products) {
      const d = drafts[p.code];
      if (!d) continue;
      if (d.site_category !== (p.site_category ?? "") || d.image_url !== (p.image_url ?? "")
        || d.hidden !== p.hidden || d.price_toman !== (p.price_toman === null ? "" : String(p.price_toman))
        || d.discount_toman !== (p.discount_price_toman === null || p.discount_price_toman === undefined ? "" : String(p.discount_price_toman))) {
        changed.add(p.code);
      }
    }
    return changed;
  }, [data, drafts]);

  const saveRow = async (code: string) => {
    const d = drafts[code];
    if (!d) return;
    setBusy(true);
    try {
      const discountToman = d.discount_toman.trim() === "" ? null : Number(d.discount_toman.replace(/,/g, ""));
      if (discountToman !== null && (!Number.isFinite(discountToman) || discountToman < 0)) {
        setMessage(`کد ${code}: قیمت تخفیفی نامعتبر است.`);
        setBusy(false);
        return;
      }
      await secureApi(`/site-cms/products/${encodeURIComponent(code)}`, {
        method: "PATCH",
        body: JSON.stringify({
          site_category: d.site_category, image_url: d.image_url, hidden: d.hidden,
          discount_price_irr: discountToman === null ? null : Math.round(discountToman * 10),
        }),
      });
      const priceToman = d.price_toman.trim() === "" ? null : Number(d.price_toman.replace(/,/g, ""));
      const original = data?.products.find(p => p.code === code);
      if (priceToman !== null && Number.isFinite(priceToman) && original?.price_toman !== priceToman) {
        await secureApi(`/site-cms/products/${encodeURIComponent(code)}/price`, {
          method: "POST",
          body: JSON.stringify({ price_irr: Math.round(priceToman * 10) }),
        });
        setMessage(`کد ${code}: قیمت کاتالوگ محلی ذخیره شد؛ قیمت در نرم‌افزار هلو تغییر نکرده است و همگام‌سازی بعدی هلو ممکن است آن را بازنویسی کند.`);
      } else {
        setMessage(`کد ${code} ذخیره شد.`);
      }
      await load(query, hiddenFilter);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ذخیرهٔ تغییرات انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  const rebuild = async () => {
    setBusy(true);
    setMessage("در حال بازسازی data.json سایت…");
    try {
      const result = await secureApi<{ ok: boolean; output: string }>("/site-cms/rebuild", { method: "POST" });
      setMessage(`بازسازی انجام شد: ${result.output}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "بازسازی کاتالوگ انجام نشد.");
    } finally {
      setBusy(false);
    }
  };

  return <PortalShell title="مدیریت سایت" eyebrow="داشبورد مدیریت سایت عمومی">
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <div>
        <label className="block text-xs text-slate-400">جست‌وجو (کد یا نام)</label>
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { setLoading(true); void load(query, hiddenFilter); } }}
          placeholder="مثلاً آجر یا 10-001" className={`${fieldClass} mt-1 w-64`} />
      </div>
      <div>
        <label className="block text-xs text-slate-400">وضعیت نمایش</label>
        <select value={hiddenFilter} onChange={(e) => { setHiddenFilter(e.target.value); setLoading(true); void load(query, e.target.value); }} className={`${fieldClass} mt-1 w-44`}>
          <option value="">همه</option>
          <option value="false">نمایش‌داده‌شده</option>
          <option value="true">مخفی</option>
        </select>
      </div>
      <button onClick={() => { setLoading(true); void load(query, hiddenFilter); }} className={primaryButton}>نمایش</button>
      <button disabled={busy} onClick={() => void rebuild()}
        className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-2 text-xs font-bold text-amber-200 hover:bg-amber-500/20">بازسازی data.json سایت</button>
      <div className="text-xs text-slate-400">
        {data ? <>تعداد: {data.count.toLocaleString("fa-IR")} · مخفی: {data.hidden_count.toLocaleString("fa-IR")}</> : null}
      </div>
    </div>
    {message && <div className="mb-4 rounded-xl border border-violet-400/20 bg-violet-500/10 p-3 text-xs leading-6 text-violet-200 whitespace-pre-wrap">{message}</div>}
    <Surface className="overflow-hidden">
      {loading ? <div className="p-8 text-center text-xs text-slate-500">در حال دریافت…</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead className="border-b border-white/[0.06] text-[10px] text-slate-400">
              <tr>
                <th className="p-3">کد</th><th className="p-3">نام کالا</th>
                <th className="p-3">قیمت (تومان)</th><th className="p-3">تخفیف (تومان)</th><th className="p-3">موجودی</th>
                <th className="p-3">دستهٔ سایت</th><th className="p-3">آدرس تصویر</th>
                <th className="p-3">نمایش</th><th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.products ?? []).map(p => {
                const d = drafts[p.code];
                return <tr key={p.code} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
                  <td className="p-3 font-mono text-[10px] text-slate-400">{p.code}</td>
                  <td className="p-3 text-white">{p.name}</td>
                  <td className="p-3">
                    <input value={d?.price_toman ?? ""} onChange={(e) => setDraft(p.code, { price_toman: e.target.value })}
                      className="w-28 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-left tabular-nums text-white"
                      inputMode="numeric" />
                    <div className="mt-1 text-[10px] text-slate-500">{toman(p.price_toman)} تومان (فعلی)</div>
                  </td>
                  <td className="p-3">
                    <input value={d?.discount_toman ?? ""} onChange={(e) => setDraft(p.code, { discount_toman: e.target.value })}
                      className="w-28 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-left tabular-nums text-white"
                      inputMode="numeric" placeholder="بدون تخفیف" />
                    <div className="mt-1 text-[10px] text-slate-500">
                      مؤثر: {toman(p.effective_price_toman)} تومان
                    </div>
                  </td>
                  <td className="p-3 tabular-nums text-slate-300">{p.stock ?? 0}</td>
                  <td className="p-3">
                    <input value={d?.site_category ?? ""} onChange={(e) => setDraft(p.code, { site_category: e.target.value })}
                      placeholder={p.site_category ?? "بدون دسته"} className="w-36 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-white" />
                  </td>
                  <td className="p-3">
                    <input value={d?.image_url ?? ""} onChange={(e) => setDraft(p.code, { image_url: e.target.value })}
                      placeholder="URL تصویر" dir="ltr" className="w-56 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-left text-white" />
                  </td>
                  <td className="p-3">
                    <button onClick={() => setDraft(p.code, { hidden: !(d?.hidden ?? p.hidden) })}
                      className={`rounded-full px-3 py-1 text-[10px] font-bold ${(d?.hidden ?? p.hidden) ? "bg-rose-500/15 text-rose-300" : "bg-emerald-500/15 text-emerald-300"}`}>
                      {(d?.hidden ?? p.hidden) ? "مخفی" : "نمایش"}
                    </button>
                  </td>
                  <td className="p-3">
                    <button disabled={busy || !dirty.has(p.code)} onClick={() => void saveRow(p.code)}
                      className={`rounded-lg px-3 py-2 text-[10px] font-bold ${dirty.has(p.code) ? primaryButton : "cursor-not-allowed bg-white/[0.04] text-slate-500"}`}>
                      ذخیره
                    </button>
                  </td>
                </tr>;
              })}
              {!data?.products.length && <tr><td colSpan={9} className="p-8 text-center text-slate-500">کالایی یافت نشد.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Surface>
    <Surface className="mt-6 overflow-hidden">
      <div className="flex items-center justify-between p-4">
        <h2 className="text-sm font-bold text-white">بنرها</h2>
        <span className="text-[10px] text-slate-400">{banners.length.toLocaleString("fa-IR")} بنر (تصویر تا ۶۰۰KB)</span>
      </div>
      <div className="flex flex-wrap items-end gap-3 border-y border-white/[0.06] p-4">
        <label className="block text-xs text-slate-400">
          تصویر
          <input type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) onBannerFile(f); }}
            className="mt-1 block w-56 text-[10px] text-slate-300 file:mr-2 file:rounded-lg file:border-0 file:bg-violet-500/20 file:px-3 file:py-1.5 file:text-[10px] file:text-violet-200" />
        </label>
        <label className="block text-xs text-slate-400">عنوان
          <input value={bannerTitle} onChange={(e) => setBannerTitle(e.target.value)} className={`${fieldClass} mt-1 w-44`} />
        </label>
        <label className="block text-xs text-slate-400">لینک
          <input value={bannerLink} onChange={(e) => setBannerLink(e.target.value)} dir="ltr" placeholder="https://…" className={`${fieldClass} mt-1 w-56`} />
        </label>
        <label className="block text-xs text-slate-400">ترتیب
          <input value={bannerSort} onChange={(e) => setBannerSort(e.target.value)} inputMode="numeric" className={`${fieldClass} mt-1 w-20`} />
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={bannerActive} onChange={(e) => setBannerActive(e.target.checked)} /> فعال
        </label>
        <button disabled={bannerBusy || !bannerImage} onClick={() => void createBanner()}
          className={`${bannerBusy || !bannerImage ? "cursor-not-allowed bg-white/[0.04] text-slate-500" : primaryButton} rounded-xl px-4 py-2 text-xs font-bold`}>
          افزودن بنر
        </button>
        {bannerImage && <img src={bannerImage} alt="پیش‌نمایش" className="h-12 rounded-lg object-cover" />}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-right text-xs">
          <thead className="border-b border-white/[0.06] text-[10px] text-slate-400">
            <tr><th className="p-3">تصویر</th><th className="p-3">عنوان</th><th className="p-3">لینک</th>
              <th className="p-3">ترتیب</th><th className="p-3">فعال</th><th className="p-3"></th></tr>
          </thead>
          <tbody>
            {banners.map(b => <tr key={b.id} className="border-b border-white/[0.04] hover:bg-white/[0.03]">
              <td className="p-3"><img src={b.image_url} alt={b.title} className="h-12 rounded-lg object-cover" /></td>
              <td className="p-3 text-white">{b.title || "—"}</td>
              <td className="p-3 max-w-56 truncate text-slate-300" dir="ltr">{b.link_url || "—"}</td>
              <td className="p-3 tabular-nums text-slate-300">{b.sort}</td>
              <td className="p-3">
                <button onClick={() => void patchBanner(b.id, { active: !b.active })}
                  className={`rounded-full px-3 py-1 text-[10px] font-bold ${b.active ? "bg-emerald-500/15 text-emerald-300" : "bg-slate-500/15 text-slate-400"}`}>
                  {b.active ? "فعال" : "غیرفعال"}
                </button>
              </td>
              <td className="p-3"><button disabled={bannerBusy} onClick={() => void deleteBanner(b.id)}
                className="rounded-lg bg-rose-500/15 px-3 py-2 text-[10px] font-bold text-rose-300 hover:bg-rose-500/25">حذف</button></td>
            </tr>)}
            {!banners.length && <tr><td colSpan={6} className="p-6 text-center text-slate-500">بنری ثبت نشده است.</td></tr>}
          </tbody>
        </table>
      </div>
    </Surface>

    <Surface className="mt-6 overflow-hidden">
      <div className="flex items-center justify-between p-4">
        <h2 className="text-sm font-bold text-white">سفارش‌های سایت</h2>
        <button onClick={() => void loadOrders()} className="rounded-lg border border-white/10 px-3 py-1.5 text-[10px] text-slate-300 hover:bg-white/[0.05]">به‌روزرسانی</button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-right text-xs">
          <thead className="border-b border-white/[0.06] text-[10px] text-slate-400">
            <tr><th className="p-3">#</th><th className="p-3">مشتری</th><th className="p-3">تماس</th>
              <th className="p-3">شهر / نشانی</th><th className="p-3">اقلام</th><th className="p-3">جمع (تومان)</th>
              <th className="p-3">تاریخ</th><th className="p-3">وضعیت</th></tr>
          </thead>
          <tbody>
            {orders.map(o => <tr key={o.id} className="border-b border-white/[0.04] align-top hover:bg-white/[0.03]">
              <td className="p-3 font-mono text-[10px] text-slate-400">{o.id}</td>
              <td className="p-3 text-white">{o.customer_name}</td>
              <td className="p-3 text-slate-300" dir="ltr">{o.phone ?? "—"}</td>
              <td className="p-3 max-w-64 text-slate-300">{o.city ?? "—"} — {o.address ?? "—"}</td>
              <td className="p-3 text-slate-300">{(o.items ?? []).map(it => `${it.name} ×${it.qty}`).join("، ")}</td>
              <td className="p-3 tabular-nums font-bold text-white">{toman(o.total_irr / 10)}</td>
              <td className="p-3 text-[10px] text-slate-500" dir="ltr">{o.created_at ? new Date(o.created_at).toLocaleString("fa-IR") : "—"}</td>
              <td className="p-3">
                <select value={o.status} disabled={orderBusy === o.id}
                  onChange={(e) => void setOrderStatus(o.id, e.target.value)}
                  className="rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-[11px] text-white">
                  {ORDER_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </td>
            </tr>)}
            {!orders.length && <tr><td colSpan={8} className="p-6 text-center text-slate-500">سفارشی ثبت نشده است.</td></tr>}
          </tbody>
        </table>
      </div>
    </Surface>
  </PortalShell>;
}

