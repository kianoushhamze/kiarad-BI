"use client";

import { useCallback, useEffect, useState } from "react";
import { InteractiveChart } from "../../components/interactive-chart";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi, getSavedUser } from "../../lib/secure-api";
import { formatJalaliDateInput } from "../../lib/iran-date";

type Section = Record<string, unknown> | null;
type Brief = {
  generated_for: string;
  generated_at: string;
  sections: {
    sales_yesterday?: Section;
    due_checks?: Section;
    site_orders?: Section;
    low_stock?: Section;
    holoo_sync?: Section;
  };
  warnings: string[];
  notes: string | null;
};
type BriefEnvelope = { biz_date: string; is_stale: boolean; brief: Brief };
type HistoryRow = { biz_date: string; is_stale: boolean; net_sales_irr: string | null; new_orders: string | null };

const fa = (v: number | string | null | undefined) =>
  new Intl.NumberFormat("fa-IR").format(Number(v || 0));
const money = (v: number | string | null | undefined) => fa(Math.round(Number(v || 0) / 10)) + " تومان";
const jdate = (iso: string | null | undefined) => (iso ? formatJalaliDateInput(iso) : "—");

function num(section: Section, key: string): number {
  if (!section) return 0;
  const raw = (section as Record<string, unknown>)[key];
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}
function str(section: Section, key: string): string {
  if (!section) return "";
  const raw = (section as Record<string, unknown>)[key];
  return raw == null ? "" : String(raw);
}
function hasError(section: Section): string {
  if (!section) return "";
  const e = (section as Record<string, unknown>)["error"];
  return e ? String(e) : "";
}

export default function MorningBriefPage() {
  const user = getSavedUser();
  const allowed = user?.role === "ceo";

  const [data, setData] = useState<BriefEnvelope | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");

  const loadHistory = useCallback(async function () {
    try {
      const res = await secureApi<{ days: HistoryRow[] }>("/morning-brief/history?days=14");
      setHistory(res.days || []);
    } catch { setHistory([]); }
  }, []);

  useEffect(function () {
    if (!allowed) return;
    const controller = new AbortController();
    secureApi<BriefEnvelope>("/morning-brief", { signal: controller.signal }).then(function (res) {
      if (controller.signal.aborted) return;
      setData(res);
      setNotes(res.brief?.notes || "");
      setError("");
      secureApi("/morning-brief/viewed", { method: "POST", signal: controller.signal }).catch(() => undefined);
    }).catch(function (reason) {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "دریافت گزارش صبحگاهی ناموفق بود.");
      }
    });
    secureApi<{ days: HistoryRow[] }>("/morning-brief/history?days=14", { signal: controller.signal }).then(function (res) {
      if (!controller.signal.aborted) setHistory(res.days || []);
    }).catch(function () {
      if (!controller.signal.aborted) setHistory([]);
    });
    return function () { controller.abort(); };
  }, [allowed]);

  async function refresh() {
    setBusy(true); setNotice("");
    try {
      const res = await secureApi<BriefEnvelope>("/morning-brief/refresh", { method: "POST" });
      setData(res); setNotes(res.brief?.notes || ""); setNotice("گزارش با دادهٔ زنده بازسازی شد.");
      loadHistory();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "بازسازی ناموفق بود.");
    } finally { setBusy(false); }
  }

  async function saveNote() {
    setBusy(true); setNotice("");
    try {
      await secureApi("/morning-brief/note", { method: "POST", body: JSON.stringify({ notes }) });
      setNotice("یادداشت ثبت شد.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "ثبت یادداشت ناموفق بود.");
    } finally { setBusy(false); }
  }

  if (!allowed) {
    return (
      <PortalShell title="گزارش صبحگاهی" eyebrow="مدیریت و مالی">
        <Surface>
          <p className="mt-2 text-xs text-slate-400">این صفحه فقط برای نقش مدیرعامل (ceo) فعال است.</p>
        </Surface>
      </PortalShell>
    );
  }

  const s = data?.brief?.sections;
  const sales = s?.sales_yesterday ?? null;
  const checks = s?.due_checks ?? null;
  const orders = s?.site_orders ?? null;
  const stock = s?.low_stock ?? null;
  const sync = s?.holoo_sync ?? null;
  const warnings = data?.brief?.warnings || [];
  const syncHealthy = sync ? sync["healthy"] === true : false;
  const salesDelta = sales ? num(sales, "net_sales_irr") - num(sales, "prev_day_net_sales_irr") : 0;
  const salesDeltaPct = sales && num(sales, "prev_day_net_sales_irr") > 0
    ? Math.round((salesDelta / num(sales, "prev_day_net_sales_irr")) * 100) : null;
  const stockItems = stock && Array.isArray(stock["items"]) ? (stock["items"] as Record<string, unknown>[]) : [];
  const nearest = checks && Array.isArray(checks["nearest"]) ? (checks["nearest"] as Record<string, unknown>[]) : [];
  const top = sales && sales["top_product"] ? (sales["top_product"] as Record<string, unknown>) : null;

  return (
    <PortalShell title="گزارش صبحگاهی — کیاراد" eyebrow="مدیریت و مالی">
      {error && <p role="alert" className="text-rose-300 mb-3">{error}</p>}
      {notice && <p className="text-emerald-300 mb-3">{notice}</p>}
      {data?.is_stale && (
        <div className="mb-4 rounded-xl border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-amber-200">
          ⚠️ این گزارش با هشدار ساخته شده — با دکمهٔ «بازسازی زنده» بعد از رفع منبع، تازه‌سازی کن.
        </div>
      )}
      {warnings.length > 0 && (
        <div className="mb-4 rounded-xl border border-amber-400/30 bg-amber-400/5 p-3 text-sm text-amber-100">
          <ul className="list-disc pr-5 space-y-1">
            {warnings.map((w, i) => (<li key={i}>{w}</li>))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-slate-400">
          برای {jdate(data?.brief?.generated_for)} — ساخته‌شده در {data?.brief?.generated_at?.slice(11, 16)} • صددرصد دادهٔ زندهٔ دیتابیس، بدون مدل زبانی
        </p>
        <button className={primaryButton} onClick={refresh} disabled={busy}>
          {busy ? "..." : "🔄 بازسازی زنده"}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Sales yesterday */}
        <Surface>
          <h3 className="font-bold mb-2">💼 فروش دیروز</h3>
          {hasError(sales) ? <p className="text-rose-300 text-sm">{hasError(sales)}</p> : (
            <div className="space-y-1 text-sm">
              <p className="text-2xl font-black text-emerald-300">{money(num(sales, "net_sales_irr"))}</p>
              <p className="text-slate-300">{fa(num(sales, "documents"))} فاکتور</p>
              {salesDeltaPct !== null && (
                <p className={salesDelta >= 0 ? "text-emerald-300 text-xs" : "text-rose-300 text-xs"}>
                  {salesDelta >= 0 ? "▲" : "▼"} {fa(Math.abs(salesDeltaPct))}٪ نسبت به پریروز ({money(Math.abs(salesDelta))})
                </p>
              )}
              {top && (
                <p className="text-xs text-slate-400 mt-1">🥇 محصول اول روز: {String(top["name"] || "")} — {money(top["amount"] as number)}</p>
              )}
            </div>
          )}
        </Surface>

        {/* Checks */}
        <Surface>
          <h3 className="font-bold mb-2">🧾 چک‌های دریافتی (۷ روز پیش رو)</h3>
          {hasError(checks) ? <p className="text-rose-300 text-sm">{hasError(checks)}</p> : (
            <div className="space-y-1 text-sm">
              {num(checks, "overdue_count") > 0 ? (
                <p className="text-rose-300 font-bold">🔴 {fa(num(checks, "overdue_count"))} چک گذشته از سرسید — {money(num(checks, "overdue_amount_irr"))}</p>
              ) : <p className="text-emerald-300">✅ هیچ چک عقب‌افتاده‌ای نیست</p>}
              <p>📅 {fa(num(checks, "week_count"))} چک در ۷ روز آینده — {money(num(checks, "week_amount_irr"))}</p>
              <ul className="text-xs text-slate-400 space-y-0.5 mt-1">
                {nearest.map((c, i) => (
                  <li key={i}>{jdate(String(c["due_date"] || ""))} — {String(c["counterparty"] || "")} ({String(c["document_type"] === "receivable" ? "دریافت" : "پرداخت")}) — {money(c["amount"] as number)}</li>
                ))}
              </ul>
            </div>
          )}
        </Surface>

        {/* Site orders */}
        <Surface>
          <h3 className="font-bold mb-2">🛒 سفارش‌های تازهٔ سایت همکاران</h3>
          {hasError(orders) ? <p className="text-rose-300 text-sm">{hasError(orders)}</p> : (
            <div className="space-y-1 text-sm">
              <p className="text-2xl font-black text-sky-300">{fa(num(orders, "new_orders"))} سفارش</p>
              <p className="text-slate-300">{money(num(orders, "new_orders_amount_irr"))}</p>
              <p className="text-xs text-slate-400">امروز تا این لحظه: {fa(num(orders, "today_so_far"))} سفارش جدید</p>
            </div>
          )}
        </Surface>

        {/* Holoo sync health */}
        <Surface>
          <h3 className="font-bold mb-2">🔗 سلامت سینک هلو</h3>
          <div className="space-y-1 text-sm">
            <p className={syncHealthy ? "text-emerald-300 font-bold" : "text-rose-300 font-bold"}>
              {syncHealthy ? "✅ سالم" : "🔴 نامطمئن"} — وضعیت: {str(sync, "status") || "نامشخص"}
            </p>
            <p className="text-xs text-slate-400">
              آخرین سینک: {str(sync, "last_sync_at")?.replace("T", " ").slice(0, 16) || "—"}
              {sync && sync["hours_ago"] != null ? ` (${fa(sync["hours_ago"] as number)} ساعت پیش)` : ""}
            </p>
            <p className="text-xs text-slate-500">عددی که این‌جا سبز است یعنی فروش دیروز قابل اتکاست.</p>
          </div>
        </Surface>

        {/* Low stock */}
        <Surface className="md:col-span-2">
          <h3 className="font-bold mb-2">📦 موجودی کم (آستانهٔ {fa(num(stock, "threshold") || 5)})</h3>
          {hasError(stock) ? <p className="text-rose-300 text-sm">{hasError(stock)}</p>
            : stockItems.length === 0 ? <p className="text-emerald-300 text-sm">✅ قلمی زیر آستانه نیست.</p> : (
              <table className="w-full text-sm">
                <thead><tr className="text-slate-400 text-xs"><th className="text-right pb-1">کد</th><th className="text-right pb-1">نام</th><th className="text-right pb-1">موجودی</th></tr></thead>
                <tbody>
                  {stockItems.map((it, i) => (
                    <tr key={i} className="border-t border-white/5">
                      <td className="py-1 text-slate-400">{String(it["code"] || "")}</td>
                      <td className="py-1">{String(it["name"] || "")}</td>
                      <td className="py-1 font-bold text-rose-300">{fa(it["stock"] as number)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Surface>

        {/* CEO note */}
        <Surface className="md:col-span-2">
          <h3 className="font-bold mb-2">✍️ یادداشت امروز (برای خودت / تیم فردا)</h3>
          <textarea
            className={fieldClass + " min-h-[80px] w-full"}
            placeholder="مثلاً: امروز با آقای کرمانی جلسه دارم؛ چک بانک ملت پیگیری شود..."
            value={notes}
            onChange={e => setNotes(e.target.value)}
          />
          <button className={primaryButton + " mt-2"} onClick={saveNote} disabled={busy}>ذخیرهٔ یادداشت</button>
        </Surface>

        {/* History */}
        {history.length > 0 && (
          <Surface className="md:col-span-2">
            <h3 className="font-bold mb-2">📜 ۱۴ روز اخیر</h3>
            <div className="mb-4">
              <InteractiveChart
                ariaLabel="روند فروش و سفارش‌های سایت در ۱۴ روز اخیر"
                labels={[...history].sort((a, b) => a.biz_date.localeCompare(b.biz_date)).map((r) => jdate(r.biz_date))}
                series={[
                  { name: "فروش (میلیون تومان)", color: "#8b7cff", values: [...history].sort((a, b) => a.biz_date.localeCompare(b.biz_date)).map((r) => (r.net_sales_irr == null ? null : Math.round(Number(r.net_sales_irr) / 10_000_000 * 10) / 10)) },
                  { name: "سفارش سایت", color: "#3ddc97", values: [...history].sort((a, b) => a.biz_date.localeCompare(b.biz_date)).map((r) => (r.new_orders == null ? null : Number(r.new_orders))) },
                ]}
              />
            </div>
            <table className="w-full text-sm">
              <thead><tr className="text-slate-400 text-xs"><th className="text-right pb-1">تاریخ</th><th className="text-right pb-1">فروش</th><th className="text-right pb-1">سفارش سایت</th><th className="text-right pb-1">وضعیت</th></tr></thead>
              <tbody>
                {history.map((r, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="py-1">{jdate(r.biz_date)}</td>
                    <td className="py-1">{r.net_sales_irr ? money(r.net_sales_irr) : "—"}</td>
                    <td className="py-1">{r.new_orders ? fa(r.new_orders) : "—"}</td>
                    <td className="py-1">{r.is_stale ? "⚠️" : "✅"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Surface>
        )}
      </div>
    </PortalShell>
  );
}
