"use client";
import React, { useState } from "react";

type BucketKey = "on_schedule" | "missed" | "rescheduled" | "unplanned";

type ReconciliationItem = {
  center_name?: string; center_id?: number; visit_date?: string; planned_date?: string;
  outcome_status?: string; order_amount_rial?: number; outcome_notes?: string; visit_goal?: string;
};
export type ReconciliationData = {
  summary: Partial<Record<`${BucketKey}_count` | "strict_compliance_percent" | "effective_coverage_percent", number>>;
  buckets: Partial<Record<BucketKey, ReconciliationItem[]>>;
};

export default function ReconciliationPanel({ data }: { data: ReconciliationData | null }) {
  const [activeTab, setActiveTab] = useState<BucketKey>("on_schedule");

  if (!data || !data.summary) return null;
  const { summary, buckets } = data;

  const tabs: { key: BucketKey; label: string; count: number; badgeClass: string }[] = [
    { key: "on_schedule", label: "انجام‌شده طبق برنامه", count: summary.on_schedule_count || 0, badgeClass: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
    { key: "missed", label: "عقب‌افتاده / انجام‌نشده", count: summary.missed_count || 0, badgeClass: "bg-rose-500/20 text-rose-300 border-rose-500/40" },
    { key: "rescheduled", label: "جابه‌جاشده در ماه", count: summary.rescheduled_count || 0, badgeClass: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
    { key: "unplanned", label: "خارج از برنامه (سرزده)", count: summary.unplanned_count || 0, badgeClass: "bg-purple-500/20 text-purple-300 border-purple-500/40" },
  ];

  return (
    <div className="mt-6 rounded-2xl border border-purple-500/20 bg-slate-900/90 p-5 text-right shadow-xl" dir="rtl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h3 className="text-lg font-bold text-white">تطبیق ۴گانه برنامه ماهانه و عملکرد میدانی</h3>
          <p className="text-xs text-slate-400">مقایسه برنامه مصوب با حضور GPS، گزارش بازدید و پیش‌فاکتورهای ثبت‌شده</p>
        </div>
        <div className="flex gap-4 text-sm">
          <div className="rounded-xl bg-slate-800/80 px-4 py-2">
            <span className="text-slate-400">انضباط دقیق زمانی: </span>
            <span className="font-bold text-emerald-400">{summary.strict_compliance_percent}٪</span>
          </div>
          <div className="rounded-xl bg-slate-800/80 px-4 py-2">
            <span className="text-slate-400">پوشش مؤثر تا تاریخ گزارش: </span>
            <span className="font-bold text-purple-400">{summary.effective_coverage_percent}٪</span>
          </div>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center justify-between rounded-xl border p-3 transition ${
              activeTab === tab.key
                ? "border-purple-500 bg-purple-950/40 text-white shadow-md"
                : "border-slate-800 bg-slate-900/50 text-slate-400 hover:bg-slate-800/50"
            }`}
          >
            <span className="text-xs font-medium">{tab.label}</span>
            <span className={`rounded-lg border px-2.5 py-0.5 text-xs font-bold ${tab.badgeClass}`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-right text-xs text-slate-200">
          <thead className="bg-slate-800/70 text-slate-400">
            <tr>
              <th className="p-3">نام پایگاه</th>
              <th className="p-3">تاریخ برنامه</th>
              <th className="p-3">نتیجه ویزیت / سفارش</th>
              <th className="p-3">توضیحات / هدف</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {(!buckets[activeTab] || buckets[activeTab].length === 0) ? (
              <tr>
                <td colSpan={4} className="p-6 text-center text-slate-500">
                  موردی در این دسته ثبت نشده است.
                </td>
              </tr>
            ) : (
              (buckets[activeTab] ?? []).map((item, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30">
                  <td className="p-3 font-semibold text-white">{item.center_name || `پایگاه #${item.center_id || idx + 1}`}</td>
                  <td className="p-3">{item.visit_date || item.planned_date || "—"}</td>
                  <td className="p-3">
                    {item.outcome_status === "order_placed" ? (
                      <span className="text-emerald-400">ثبت سفارش ({Number(item.order_amount_rial || 0).toLocaleString("fa-IR")} ریال)</span>
                    ) : (
                      <span className="text-slate-300">{item.outcome_status === "verified" ? "ویزیت معتبر" : item.outcome_status || "در انتظار بررسی"}</span>
                    )}
                  </td>
                  <td className="p-3 text-slate-400">{item.outcome_notes || item.visit_goal || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
