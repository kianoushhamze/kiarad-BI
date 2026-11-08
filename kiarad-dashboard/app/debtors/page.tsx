"use client";

import { useCallback, useEffect, useState } from "react";
import { PortalShell } from "../../components/portal-shell";
import { authFetch } from "../../lib/secure-api";
import { formatIranReportPeriod } from "../../lib/iran-date";

type Debtor = { counterparty: string; balance: number; share_percent?: number | null; customer_id?: number | null };
type Snapshot = { report_from_text?: string | null; report_to_text?: string | null; snapshot_date?: string | null; total_amount?: number | null; row_count?: number | null };
type Report = { snapshot: Snapshot | null; debtors: Debtor[] };
const money = (value?: number | null) => new Intl.NumberFormat("fa-IR").format(Math.round(value || 0)) + " ریال";

export default function DebtorsPage() {
  const [report, setReport] = useState<Report>({ snapshot: null, debtors: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await authFetch("/treasury/debtors");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "دریافت گزارش بدهکاران ناموفق بود.");
      setReport({ snapshot: data.snapshot || null, debtors: Array.isArray(data.debtors) ? data.debtors : [] });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "خطای دریافت اطلاعات");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  return (
    <PortalShell title="بدهکاران" eyebrow="گزارش فقط‌خواندنی مطالبات">
      <div className="kskin space-y-4">
        <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/[0.07] bg-[#0f1222] p-4">
          <div>
            <b className="text-sm text-white">آخرین تصویر بدهکاران</b>
            <p className="mt-1 text-[10px] text-slate-500">
              {report.snapshot ? `بازهٔ ${formatIranReportPeriod(report.snapshot.report_from_text)} تا ${formatIranReportPeriod(report.snapshot.report_to_text)} · تاریخ ثبت ${formatIranReportPeriod(report.snapshot.snapshot_date)}` : "هنوز گزارشی وارد نشده است."}
            </p>
          </div>
          <button onClick={load} className="rounded-xl border border-white/10 px-4 py-2 text-xs text-slate-300">به‌روزرسانی</button>
        </section>

        {report.snapshot ? (
          <section className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-white/[0.07] bg-[#0f1222] p-4"><div className="text-[10px] text-slate-500">جمع مطالبات در آخرین گزارش</div><div className="mt-2 text-lg font-black text-cyan-300">{money(report.snapshot.total_amount)}</div></div>
            <div className="rounded-2xl border border-white/[0.07] bg-[#0f1222] p-4"><div className="text-[10px] text-slate-500">تعداد ردیف‌های گزارش</div><div className="mt-2 text-lg font-black text-white">{new Intl.NumberFormat("fa-IR").format(report.snapshot.row_count || 0)}</div></div>
          </section>
        ) : null}

        <section className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0f1222]">
          <div className="border-b border-white/[0.06] px-4 py-3"><b className="text-sm text-white">بیشترین مانده‌ها</b><span className="mr-2 text-[10px] text-slate-500">تا ۱۰۰ ردیف</span></div>
          {loading ? <div className="p-10 text-center text-xs text-slate-500">در حال دریافت اطلاعات…</div> : null}
          {error ? <div className="p-6 text-center text-xs text-rose-300">{error}</div> : null}
          {!loading && !error && report.debtors.length === 0 ? <div className="p-10 text-center text-xs text-slate-500">داده‌ای در گزارش بدهکاران نیست.</div> : null}
          {report.debtors.length > 0 ? (
            <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-right text-xs">
              <thead className="bg-white/[0.025] text-slate-500"><tr><th className="px-4 py-3">مشتری / طرف حساب</th><th className="px-4 py-3">مانده</th><th className="px-4 py-3">سهم از کل</th></tr></thead>
              <tbody>{report.debtors.map((row, index) => <tr key={`${row.customer_id || row.counterparty}-${index}`} className="border-t border-white/[0.05] text-slate-300"><td className="px-4 py-3 font-bold text-white">{row.counterparty}</td><td className="px-4 py-3 font-bold text-cyan-300">{money(row.balance)}</td><td className="px-4 py-3">{row.share_percent == null ? "—" : `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 }).format(row.share_percent)}٪`}</td></tr>)}</tbody>
            </table></div>
          ) : null}
        </section>
      </div>
    </PortalShell>
  );
}
