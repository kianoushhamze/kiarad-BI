"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { InteractiveChart } from "../../components/interactive-chart";
import { PortalShell, Surface } from "../../components/portal-shell";
import { authFetch, getToken } from "../../lib/secure-api";
import { formatIranDate, formatIranDateTime } from "../../lib/iran-date";

type Period = "month" | "30d" | "90d";
type Dashboard = {
  data_sync?: {status:string;finished_at?:string;scope?:string;unattributed_documents?:number};
  period?: {from_date:string;to_date:string;calendar:string};
  view_mode?: string;
  my_debtors?: Array<{ name?: string; balance?: number; customer_name?: string; city?: string; phone?: string }>;
  my_targets?: Array<{ id?: number; title?: string; target_amount?: number; target_type?: string; product_focus?: string; period_type?: string; bonus_reward?: number; start_date?: string | null; end_date?: string | null }>;
  ceo_kpi?: { total_sales?: number; invoice_count?: number; customer_count?: number; total_collected?: number; total_debt?: number; active_target?: number; achievement_percent?: number | null; sales_source_date?: string | null; debt_snapshot_date?: string | null };
  staff?: { staff?: Array<{ id?: number; name?: string; sales_amount?: number; target?: number; achievement_percent?: number }> };
  inventory?: { product_count?: number; inventory_value?: number; low_stock_count?: number };
  recommendations?: { recommendations?: Array<{ priority?: string; message?: string; title?: string }> };
};
type SalesTrend = { trend?: Array<{ month: string; sales_count?: number; sales_amount?: number }> };
type AiInsights = {
  status?: string;
  metrics?: { sales_amount?: number; invoices_count?: number; target_amount?: number; achievement_percent?: number | null; active_products?: number; low_stock_products?: number; kerman_bases?: number };
  recommendations?: Array<{ type?: string; title?: string; message?: string }>;
};

function formatMoney(value?: number) {
  if (value == null || !Number.isFinite(value)) return "—";
  const magnitude = Math.abs(value);
  if (magnitude >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیارد ریال`;
  }
  if (magnitude >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیون ریال`;
  }
  return `${value.toLocaleString("fa-IR")} ریال`;
}

function formatCount(value?: number) {
  return value == null || !Number.isFinite(value) ? "—" : value.toLocaleString("fa-IR");
}

function formatPercent(value?: number | null) {
  return value == null || !Number.isFinite(value)
    ? "—"
    : `${value.toLocaleString("fa-IR", { maximumFractionDigits: 1 })}٪`;
}

function formatShort(value?: number) {
  if (value == null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 2 })} میلیارد`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toLocaleString("fa-IR", { maximumFractionDigits: 1 })} میلیون`;
  return value.toLocaleString("fa-IR");
}

function faDigits(value: string) {
  return value.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}

function monthLabel(jalali: string) {
  const names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  const parts = jalali.split("-");
  const month = Number(parts[1]);
  return names[month - 1] ?? jalali;
}

/** Bento tile — the single card-like surface of the redesigned dashboard. */
function Tile({ children, className = "", hero = false }: { children: React.ReactNode; className?: string; hero?: boolean }) {
  return (
    <div
      className={`group relative overflow-hidden rounded-[20px] border p-4 backdrop-blur-md transition duration-200 hover:-translate-y-0.5 sm:p-5 ${hero
        ? "border-violet-400/25 bg-gradient-to-br from-violet-500/[0.16] via-violet-500/[0.05] to-white/[0.02] hover:border-violet-400/45 hover:shadow-[0_16px_40px_rgba(91,63,214,.18)]"
        : "border-white/[0.08] bg-white/[0.045] hover:border-violet-400/25 hover:shadow-[0_14px_34px_rgba(0,0,0,.28)]"} ${className}`}
    >
      {children}
    </div>
  );
}

function TileLabel({ icon, label, color }: { icon: string; label: string; color?: string }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-slate-400">
      <span aria-hidden="true" style={color ? { color } : undefined}>{icon}</span>
      {label}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const width = 300;
  const height = 56;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((value, index) => `${(index * step).toFixed(1)},${(height - 6 - ((value - min) / span) * (height - 14)).toFixed(1)}`);
  const path = points.map((point, index) => (index === 0 ? `M${point}` : `L${point}`)).join(" ");
  const last = points[points.length - 1].split(",");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label="روند فروش ماهانه" className="mt-3">
      <defs>
        <linearGradient id="mgSpark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8b7cff" stopOpacity=".4" />
          <stop offset="1" stopColor="#8b7cff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L${width},${height} L0,${height} Z`} fill="url(#mgSpark)" />
      <path d={path} fill="none" stroke="#8b7cff" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="3.6" fill="#8b7cff" stroke="#0d0b16" strokeWidth="2" />
    </svg>
  );
}

function AchievementRing({ percent }: { percent: number | null }) {
  const clamped = Math.max(0, Math.min(percent ?? 0, 100));
  const color = percent == null ? "rgba(255,255,255,.14)" : clamped >= 60 ? "#3ddc97" : clamped >= 30 ? "#ffc857" : "#ff6b81";
  return (
    <div
      className="relative grid h-[64px] w-[64px] shrink-0 place-items-center rounded-full text-sm font-bold"
      role="progressbar"
      aria-label="درصد تحقق هدف ماه"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent == null ? undefined : Math.round(clamped)}
      style={{ background: `conic-gradient(${color} ${clamped}%, rgba(255,255,255,.09) 0)` }}
    >
      <span aria-hidden="true" className="absolute inset-[6px] rounded-full bg-[#12152c]" />
      <span className="relative z-10">{percent == null ? "—" : faDigits(`${Math.round(clamped)}٪`)}</span>
    </div>
  );
}

const periods: Array<{ value: Period; label: string }> = [
  { value: "month", label: "این ماه" },
  { value: "30d", label: "۳۰ روز" },
  { value: "90d", label: "سه ماه" },
];

const tabs = [
  { value: "all", label: "نمای کلی" },
  { value: "sales", label: "فروش و عملکرد" },
  { value: "visitors", label: "کارنامه ویزیتورها" },
  { value: "inventory", label: "انبار و تأمین" },
  { value: "targets", label: "اهداف فروش" },
] as const;

type VisitorKpi = {
  salesperson_id: number;
  name: string;
  achievement_percent: number | null;
  actual_sales: number;
  orders_count: number;
  conversion_rate: number | null;
  sales_period: "target" | "all_time";
  target_start_date: string | null;
  target_end_date: string | null;
};

export default function ManagementDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [trend, setTrend] = useState<SalesTrend | null>(null);
  const [insights, setInsights] = useState<AiInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [period, setPeriod] = useState<Period>("month");
  const [showNotifications, setShowNotifications] = useState(false);
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]["value"]>("all");
  const [visitorKpis, setVisitorKpis] = useState<VisitorKpi[]>([]);
  const [visitorKpiError, setVisitorKpiError] = useState("");
  const [visitorKpiLoading, setVisitorKpiLoading] = useState(false);
  const requestSequence = useRef(0);

  const loadVisitorKpis = useCallback(async () => {
    if (!getToken()) return;
    setVisitorKpiLoading(true);
    setVisitorKpiError("");
    try {
      const response = await authFetch("/operations/visitors/kpis");
      if (!response.ok) throw new Error(`دریافت کارنامهٔ ویزیتورها ناموفق بود (${response.status}).`);
      const body: unknown = await response.json();
      if (!Array.isArray(body)) throw new Error("ساختار دادهٔ ویزیتورها معتبر نیست.");
      setVisitorKpis(body as VisitorKpi[]);
    } catch (cause: unknown) {
      setVisitorKpiError(cause instanceof Error ? cause.message : "دریافت کارنامهٔ ویزیتورها ناموفق بود.");
    } finally {
      setVisitorKpiLoading(false);
    }
  }, []);

  const selectTab = (value: (typeof tabs)[number]["value"]) => {
    setActiveTab(value);
    if (value === "visitors") void loadVisitorKpis();
  };

  const loadDashboard = useCallback(async (selectedPeriod: Period) => {
    const requestId = ++requestSequence.current;
    if (!getToken()) { setLoading(false); return; }

    try {
      const response = await authFetch(`/dashboard/full?range=${selectedPeriod}`);
      if (!response.ok) {
        if (response.status === 401) throw new Error("نشست شما معتبر نیست؛ دوباره وارد شوید.");
        if (response.status === 403) throw new Error("حساب شما به این داشبورد دسترسی ندارد.");
        const body = await response.json().catch(() => null);
        const detail = typeof body?.detail === "string" ? body.detail : `خطای سرویس (${response.status})`;
        throw new Error(detail);
      }

      const result: Dashboard = await response.json();
      if (requestId === requestSequence.current) setData(result);
    } catch (cause: unknown) {
      if (requestId === requestSequence.current) {
        setError(cause instanceof Error ? cause.message : "دریافت اطلاعات داشبورد ناموفق بود.");
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) void loadDashboard(period);
    });
    return () => { cancelled = true; };
  }, [period, loadDashboard]);

  useEffect(()=>{const timer=setInterval(()=>{if(document.visibilityState==="visible")void loadDashboard(period);},60000);return()=>clearInterval(timer);},[period,loadDashboard]);

  // Supporting sources: monthly trend for the sparkline, live assistant insights
  // for the AI tile. Both are optional decorations — failures stay silent.
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await authFetch(`/reports/sales-trend?days=365`);
        if (response.ok && !cancelled) setTrend(await response.json());
      } catch {}
      try {
        const response = await authFetch(`/dashboard/live-ai-insights`);
        if (response.ok && !cancelled) setInsights(await response.json());
      } catch {}
    })();
    return () => { cancelled = true; };
  }, []);

  const isViewer = data?.view_mode === "salesperson";
  const ceo = data?.ceo_kpi ?? {};
  const staffList = data?.staff?.staff ?? [];
  const inventory = data?.inventory ?? {};
  const recommendations = data?.recommendations?.recommendations ?? [];
  const myTargets = data?.my_targets ?? [];
  const myDebtors = data?.my_debtors ?? [];
  const hasActiveTarget = (ceo.active_target ?? 0) > 0;
  const hasValidAchievement = ceo.achievement_percent != null;
  const achievement = ceo.achievement_percent ?? 0;
  const progressWidth = Math.max(0, Math.min(achievement, 100));

  const trendValues = (trend?.trend ?? []).slice(-6).map((row) => row.sales_amount ?? 0);
  const trendLabels = (trend?.trend ?? []).slice(-6).map((row) => monthLabel(row.month));
  const thisMonthSales = trendValues[trendValues.length - 1];
  const prevMonthSales = trendValues[trendValues.length - 2];
  const monthDelta = thisMonthSales != null && prevMonthSales != null && prevMonthSales > 0
    ? Math.round(((thisMonthSales - prevMonthSales) / prevMonthSales) * 100)
    : null;

  const actions = (
    <div className="flex flex-wrap items-center justify-end gap-2" dir="rtl">
      <div className="flex rounded-xl border border-white/10 bg-white/[0.04] p-1" role="group" aria-label="بازهٔ زمانی گزارش">
        {periods.map((item) => (
          <button
            key={item.value}
            type="button"
            aria-pressed={period === item.value}
            onClick={() => {
              setError("");
              setLoading(true);
              if (period === item.value) void loadDashboard(item.value);
              else setPeriod(item.value);
            }}
            className={`rounded-lg px-2.5 py-1.5 text-[11px] font-bold transition ${period === item.value ? "bg-violet-600 text-white shadow-[0_4px_14px_rgba(139,53,245,.28)]" : "text-slate-400 hover:text-white"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <button
        type="button"
        aria-label="به‌روزرسانی داشبورد"
        title="به‌روزرسانی داده‌ها"
        onClick={() => {
          setError("");
          setLoading(true);
          void loadDashboard(period);
        }}
        disabled={loading}
        className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-violet-300 transition hover:bg-violet-500/10 disabled:opacity-50"
      >
        ↻
      </button>

      <div className="relative">
        <button
          type="button"
          aria-label="هشدارها"
          aria-expanded={showNotifications}
          aria-controls="dashboard-notifications"
          onClick={() => setShowNotifications((open) => !open)}
          className="rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-amber-300 transition hover:bg-white/[0.08]"
        >
          🔔
        </button>
        {showNotifications && (
          <div id="dashboard-notifications" className="absolute left-0 top-11 z-50 w-[min(280px,calc(100vw-32px))] rounded-xl border border-white/10 bg-[#151a2a] p-3 shadow-xl">
            <h2 className="mb-2 text-xs font-bold text-white">پیام‌ها و هشدارهای سیستم</h2>
            {recommendations.length > 0 ? recommendations.map((item, index) => (
              <div key={`${item.priority ?? "notice"}-${index}`} className="border-b border-white/[0.07] py-2 text-xs text-slate-300 last:border-0">
                {item.message || item.title || "هشدار تازه"}
              </div>
            )) : (
              <p className="text-xs text-slate-400">هشداری ثبت نشده است.</p>
            )}
          </div>
        )}
      </div>
      {loading && data && <span role="status" className="text-[10px] text-slate-400">در حال به‌روزرسانی…</span>}
    </div>
  );

  const topStaff = [...staffList].sort((a, b) => (b.sales_amount ?? 0) - (a.sales_amount ?? 0)).slice(0, 4);
  const maxStaffSales = Math.max(...topStaff.map((item) => item.sales_amount ?? 0), 1);
  const aiRecs = insights?.recommendations ?? [];
  const aiCritical = aiRecs.filter((item) => item.type === "critical").length;

  return (
    <PortalShell
      title={data ? (isViewer ? "داشبورد من" : "داشبورد جامع مدیرعامل") : "داشبورد"}
      eyebrow="مرکز فرماندهی"
      actions={actions}
    >
      <div dir="rtl">
        {error && <div role="alert" className="mb-4 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
        {loading && !data && <div role="status" className="mb-4 rounded-xl border border-white/[0.08] bg-white/[0.03] p-4 text-sm text-slate-300">در حال دریافت اطلاعات داشبورد…</div>}

        {data?.data_sync && <p className="mb-4 text-xs text-slate-400">همگام‌سازی عملیاتی: <b className={data.data_sync.status === "fresh" ? "font-medium text-emerald-300" : "font-medium text-amber-300"}>{data.data_sync.status === "fresh" ? "تازه" : data.data_sync.status === "stale" ? "کهنه — اتصال را بررسی کنید" : "هنوز تأیید نشده"}</b> · {data.data_sync.finished_at ? formatIranDateTime(data.data_sync.finished_at) : "زمان موجود نیست"}. مبلغ فروش پس از تخفیف و برگشت و بدون مالیات است. {data.period && `بازه: ${formatIranDate(data.period.from_date)} تا ${formatIranDate(data.period.to_date)}`}</p>}

        {data && (
          <>
            <nav aria-label="بخش‌های داشبورد" className="mb-5 flex gap-2 overflow-x-auto pb-1">
              {tabs.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  aria-current={activeTab === tab.value ? "page" : undefined}
                  onClick={() => selectTab(tab.value)}
                  className={`shrink-0 rounded-xl border px-3 py-2 text-xs transition ${activeTab === tab.value ? "border-violet-400/35 bg-violet-500/15 font-medium text-violet-200" : "border-white/[0.08] bg-white/[0.025] text-slate-400 hover:text-white"}`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            {activeTab === "all" && (
              <div className="mb-5 grid grid-cols-12 gap-3">
                {/* Hero: net sales + monthly trend */}
                <Tile hero className="col-span-12 lg:col-span-5">
                  <TileLabel icon="📈" label={isViewer ? "فروش خالص منتسب به شما" : "فروش خالص پس از برگشت"} color="#b7aaff" />
                  <div className="mt-2 text-[clamp(1.4rem,3vw,2rem)] font-extrabold leading-tight tracking-tight text-white" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatMoney(ceo.total_sales)}
                  </div>
                  {!isViewer && monthDelta != null && (
                    <div className={`mt-1.5 text-[11px] ${monthDelta >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                      {monthDelta >= 0 ? "▲" : "▼"} {faDigits(Math.abs(monthDelta).toLocaleString("fa-IR"))}٪ نسبت به ماه قبل · {trendLabels[trendLabels.length - 1] ?? ""}
                    </div>
                  )}
                  <div className="mt-3">
                    <InteractiveChart
                      ariaLabel="?????? ?????? ???? ???? ??????"
                      height={150}
                      labels={trendLabels}
                      series={[
                        {
                          name: "???? (?????? ?????)",
                          color: "#8b7cff",
                          values: trendValues.map((v) => Math.round((v / 10_000_000) * 10) / 10),
                        },
                      ]}
                    />
                  </div>
                </Tile>

                {/* Achievement ring */}
                <Tile className="col-span-12 lg:col-span-3">
                  <TileLabel icon="🎯" label="تحقق هدف ماه" color="#38bdf8" />
                  <div className="mt-3 flex items-center gap-3.5">
                    <AchievementRing percent={hasValidAchievement && hasActiveTarget ? achievement : null} />
                    <div className="min-w-0">
                      <div className="text-[11px] text-slate-400">هدف فعال</div>
                      <div className="truncate text-sm font-bold text-indigo-200">{hasActiveTarget ? formatMoney(ceo.active_target) : "ثبت نشده"}</div>
                      {!hasActiveTarget && !isViewer && (
                        <Link href="/person-targets" className="mt-1 inline-block text-[10px] text-violet-300 hover:text-white">تعریف تارگت ماه ←</Link>
                      )}
                    </div>
                  </div>
                </Tile>

                {/* Collections */}
                <Tile className="col-span-12 sm:col-span-6 lg:col-span-2">
                  <TileLabel icon="💚" label="وصولی" color="#34d399" />
                  <div className="mt-2.5 text-base font-extrabold text-emerald-300" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatShort(ceo.total_collected)}
                  </div>
                  <div className="mt-1 text-[10px] text-slate-500">ریال</div>
                </Tile>

                {/* Receivables */}
                <Tile className="col-span-12 sm:col-span-6 lg:col-span-2">
                  <TileLabel icon="⚠️" label="مطالبات باز" color="#f87171" />
                  <div className="mt-2.5 text-base font-extrabold text-rose-300" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatShort(ceo.total_debt)}
                  </div>
                  {!isViewer && <Link href="/debtors" className="mt-1 inline-block text-[10px] text-slate-400 hover:text-white">جزئیات بدهکاران ←</Link>}
                </Tile>

                {/* Assistant insight */}
                {!isViewer && (
                  <Tile className="col-span-12 lg:col-span-6">
                    <div className="flex items-center justify-between">
                      <TileLabel icon="✨" label="نگاه دستیار" color="#b7aaff" />
                      <Link href="/assistant" className="text-[10px] text-violet-300 hover:text-white">گفت‌وگو با دستیار ←</Link>
                    </div>
                    {insights?.status === "online" ? (
                      <>
                        <p className="mt-2.5 text-xs leading-6 text-slate-300">
                          فروش ۳۰ روز: <b className="text-white">{formatMoney(insights.metrics?.sales_amount)}</b>
                          {" · "}تحقق: <b className="text-white">{formatPercent(insights.metrics?.achievement_percent ?? null)}</b>
                          {aiCritical > 0 && <> · <span className="text-rose-300">{faDigits(aiCritical.toLocaleString("fa-IR"))} هشدار فوری</span></>}
                        </p>
                        <ul className="mt-2 space-y-1.5">
                          {aiRecs.slice(0, 2).map((item, index) => (
                            <li key={index} className="flex gap-2 text-[11px] leading-5 text-slate-400">
                              <span aria-hidden="true" className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${item.type === "critical" ? "bg-rose-400" : "bg-amber-300"}`} />
                              <span>{item.message || item.title}</span>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <p className="mt-2.5 text-xs leading-6 text-slate-400">
                        از دستیار دربارهٔ فروش، خزانه، انبار و تیم بپرس — با دسترسی کامل داشبورد پاسخ می‌دهد.
                      </p>
                    )}
                  </Tile>
                )}

                {/* Team performance bars */}
                {!isViewer && (
                  <Tile className="col-span-12 lg:col-span-6">
                    <div className="flex items-center justify-between">
                      <TileLabel icon="🏆" label="عملکرد تیم — فروش در بازه" color="#3ddc97" />
                      <button type="button" onClick={() => selectTab("visitors")} className="text-[10px] text-violet-300 hover:text-white">گزارش کامل ←</button>
                    </div>
                    <div className="mt-3 space-y-3">
                      {topStaff.length > 0 ? topStaff.map((member) => (
                        <div key={member.id ?? member.name}>
                          <div className="mb-1 flex items-center justify-between text-[11px]">
                            <span className="text-slate-400">{member.name || "—"}</span>
                            <b className="font-medium text-slate-200" style={{ fontVariantNumeric: "tabular-nums" }}>{formatShort(member.sales_amount)}</b>
                          </div>
                          <div aria-hidden="true" className="h-[7px] overflow-hidden rounded-full bg-white/[0.08]">
                            <div
                              className="h-full rounded-full bg-gradient-to-l from-emerald-400 to-violet-500 transition-all duration-700"
                              style={{ width: `${Math.max(4, Math.round(((member.sales_amount ?? 0) / maxStaffSales) * 100))}%` }}
                            />
                          </div>
                        </div>
                      )) : <p className="text-xs text-slate-400">داده‌ای برای نمایش نیست.</p>}
                    </div>
                  </Tile>
                )}

                {/* Compact facts */}
                <Tile className="col-span-12 lg:col-span-3">
                  <TileLabel icon="🧾" label="اسناد فروش و برگشت" />
                  <div className="mt-2.5 text-lg font-extrabold text-white" style={{ fontVariantNumeric: "tabular-nums" }}>{formatCount(ceo.invoice_count)}</div>
                </Tile>
                <Tile className="col-span-12 lg:col-span-3">
                  <TileLabel icon="👥" label="مشتریان فعال" color="#a5b4fc" />
                  <div className="mt-2.5 text-lg font-extrabold text-white" style={{ fontVariantNumeric: "tabular-nums" }}>{formatCount(ceo.customer_count)}</div>
                </Tile>
                <Tile className="col-span-12 lg:col-span-3">
                  <TileLabel icon="📦" label="اقلام در نقطهٔ سفارش" color="#f87171" />
                  <div className="mt-2.5 text-lg font-extrabold text-white" style={{ fontVariantNumeric: "tabular-nums" }}>{formatCount(inventory.low_stock_count)}</div>
                </Tile>
                <Tile className="col-span-12 lg:col-span-3">
                  <TileLabel icon="🏬" label="ارزش موجودی" color="#34d399" />
                  <div className="mt-2.5 text-lg font-extrabold text-white" style={{ fontVariantNumeric: "tabular-nums" }}>{formatShort(inventory.inventory_value)}</div>
                </Tile>
              </div>
            )}

            {(activeTab === "all" || activeTab === "sales") && (
              <Surface className="mb-5 overflow-hidden p-4 sm:p-5">
                <h2 className="mb-3 text-sm font-bold text-cyan-300">جدول تفصیلی عملکرد فروشندگان</h2>
                <p className="mb-3 text-xs text-slate-400">درصد تحقق فقط برای هدفی محاسبه می‌شود که بازهٔ معتبرِ ماه جاری داشته باشد؛ خط تیره یعنی هدف قابل مقایسه ثبت نشده است.</p>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[620px] border-collapse text-right text-xs">
                    <thead>
                      <tr className="border-b border-white/10 text-slate-400">
                        <th className="p-2">نام ویزیتور</th>
                        <th className="p-2">فروش در بازه</th>
                        <th className="p-2">هدف فعال</th>
                        <th className="p-2">تحقق ماه جاری</th>
                      </tr>
                    </thead>
                    <tbody>
                      {staffList.length > 0 ? staffList.map((staff, index) => (
                        <tr key={`${staff.id ?? staff.name ?? "staff"}-${index}`} className="border-b border-white/[0.06] transition-colors last:border-0 hover:bg-white/[0.03]">
                          <td className="p-3 font-bold text-slate-100">{staff.name || "—"}</td>
                          <td className="p-3 text-slate-300" style={{ fontVariantNumeric: "tabular-nums" }}>{formatMoney(staff.sales_amount)}</td>
                          <td className="p-3 text-slate-300" style={{ fontVariantNumeric: "tabular-nums" }}>{formatMoney(staff.target)}</td>
                          <td className={`p-3 ${staff.achievement_percent == null ? "text-slate-400" : staff.achievement_percent >= 50 ? "text-emerald-300" : "text-rose-300"}`} style={{ fontVariantNumeric: "tabular-nums" }}>
                            {formatPercent(staff.achievement_percent)}
                          </td>
                        </tr>
                      )) : (
                        <tr><td colSpan={4} className="p-4 text-center text-slate-400">اطلاعاتی برای نمایش ثبت نشده است.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Surface>
            )}

            {activeTab === "visitors" && (
              <Surface className="mb-5 overflow-hidden p-4 sm:p-5">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-bold text-violet-300">📊 کارنامه و شاخص‌های عملکرد ویزیتورها</h2>
                    <p className="mt-1 text-xs text-slate-400">فروش، تعداد فاکتور و نرخ تبدیل ویزیتورها؛ درصد تحقق فقط برای هدف معتبر در بازهٔ خودش محاسبه می‌شود.</p>
                  </div>
                  <button type="button" onClick={() => void loadVisitorKpis()} disabled={visitorKpiLoading} className="shrink-0 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-violet-300 transition hover:bg-violet-500/10 disabled:opacity-50">
                    {visitorKpiLoading ? "در حال دریافت…" : "تازه‌سازی"}
                  </button>
                </div>
                {visitorKpiError && <div role="alert" className="mb-3 rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-xs text-rose-200">{visitorKpiError}</div>}
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[680px] border-collapse text-right text-xs">
                    <thead>
                      <tr className="border-b border-white/10 text-slate-400">
                        <th className="p-2">رتبه</th>
                        <th className="p-2">نام ویزیتور</th>
                        <th className="p-2">تحقق تارگت</th>
                        <th className="p-2">فروش ثبت‌شده (ریال)</th>
                        <th className="p-2">تعداد سفارش</th>
                        <th className="p-2">نرخ موفقیت</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visitorKpis.map((kpi, index) => (
                        <tr key={`visitor-kpi-${kpi.salesperson_id || index}`} className="border-b border-white/[0.06] transition-colors last:border-0 hover:bg-white/[0.03]">
                          <td className={`p-3 font-bold ${index === 0 ? "text-amber-300" : "text-slate-400"}`}>{faDigits(`#${index + 1}`)}</td>
                          <td className="p-3 font-bold text-slate-100">{kpi.name || "—"}</td>
                          <td className="p-3">
                            {kpi.achievement_percent == null ? <span className="text-slate-400">هدف معتبر ندارد</span> : (
                              <div className="flex items-center gap-2">
                                <div aria-hidden="true" className="h-2 min-w-[60px] flex-1 overflow-hidden rounded-full bg-white/[0.08]">
                                  <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(0, Math.min(kpi.achievement_percent, 100))}%`, background: kpi.achievement_percent >= 80 ? "#10B981" : "#F59E0B" }} />
                                </div>
                                <span className="font-bold" style={{ fontVariantNumeric: "tabular-nums" }}>{faDigits(`${kpi.achievement_percent}٪`)}</span>
                              </div>
                            )}
                          </td>
                          <td className="p-3 text-emerald-300" style={{ fontVariantNumeric: "tabular-nums" }}>
                            {Number(kpi.actual_sales).toLocaleString("fa-IR")}
                            <div className="text-[10px] text-slate-500">{kpi.sales_period === "target" ? `بازهٔ هدف: ${kpi.target_start_date ? formatIranDate(kpi.target_start_date) : "نامشخص"} تا ${kpi.target_end_date ? formatIranDate(kpi.target_end_date) : "نامشخص"}` : "کل دورهٔ ثبت‌شده"}</div>
                          </td>
                          <td className="p-3 text-slate-300">{faDigits(String(kpi.orders_count))} فاکتور</td>
                          <td className="p-3 text-cyan-300">{kpi.conversion_rate == null ? "بازدید ثبت نشده" : `${faDigits(String(kpi.conversion_rate))}٪`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {visitorKpis.length === 0 && !visitorKpiLoading && !visitorKpiError && (
                  <p className="p-6 text-center text-xs text-slate-400">داده‌ای برای ویزیتورها یافت نشد.</p>
                )}
              </Surface>
            )}

            {(activeTab === "all" || activeTab === "inventory") && !isViewer && (
              <Surface className="mb-5 p-4 sm:p-5">
                <h2 className="mb-3 text-sm font-bold text-amber-300">وضعیت انبار و تأمین کالا</h2>
                <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-3">
                    <div className="text-[11px] text-slate-400">تعداد اقلام کالا</div>
                    <div className="mt-1 text-lg font-bold text-white">{formatCount(inventory.product_count)} قلم</div>
                  </div>
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-3">
                    <div className="text-[11px] text-slate-400">اقلام در نقطهٔ سفارش</div>
                    <div className="mt-1 text-lg font-bold text-rose-300">{formatCount(inventory.low_stock_count)} قلم</div>
                  </div>
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-3">
                    <div className="text-[11px] text-slate-400">ارزش موجودی به قیمت فروش</div>
                    <div className="mt-1 text-lg font-bold text-emerald-300">{formatMoney(inventory.inventory_value)}</div>
                  </div>
                </div>
              </Surface>
            )}

            {activeTab === "targets" && (
              <Surface className="mb-5 p-4 sm:p-5">
                <h2 className="mb-4 text-sm font-bold text-cyan-300">{isViewer ? "هدف‌های من" : "هدف فروش فعال"}</h2>
                {isViewer && !hasActiveTarget && myTargets.length > 0 && <p className="mb-3 text-xs text-amber-300">هدف‌های زیر ثبت شده‌اند، اما هیچ‌کدام بازهٔ معتبرِ ماه جاری ندارند؛ درصد تحقق محاسبه نمی‌شود.</p>}
                {isViewer ? (
                  myTargets.length > 0 ? myTargets.map((target, index) => (
                    <div key={`${target.id ?? target.title ?? "target"}-${index}`} className="border-b border-white/[0.07] py-3 last:border-0">
                      <h3 className="mb-2 text-sm font-bold text-white">{target.title || "هدف فروش"}</h3>
                      <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
                        <div><span className="text-slate-400">مبلغ: </span><b className="text-indigo-200">{formatMoney(target.target_amount)}</b></div>
                        <div><span className="text-slate-400">نوع: </span><span>{target.target_type || "—"}</span></div>
                        <div><span className="text-slate-400">دوره: </span><span>{target.period_type || "—"}</span></div>
                        <div><span className="text-slate-400">بازهٔ ثبت‌شده: </span><span>{target.start_date && target.end_date ? `${target.start_date} تا ${target.end_date}` : "ندارد"}</span></div>
                        {target.bonus_reward != null && <div><span className="text-slate-400">پاداش: </span><b className="text-amber-300">{formatMoney(target.bonus_reward)}</b></div>}
                      </div>
                      {target.product_focus && <p className="mt-2 text-xs text-slate-400">کالای هدف: <span className="text-slate-200">{target.product_focus}</span></p>}
                    </div>
                  )) : <p className="text-sm text-slate-400">برای این حساب هدف فعالی ثبت نشده است.</p>
                ) : hasActiveTarget ? (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <div className="text-xs text-slate-400">مبلغ هدف</div>
                      <div className="mt-1 text-lg font-bold text-indigo-200">{formatMoney(ceo.active_target)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">درصد تحقق</div>
                      <div className="mt-1 text-lg font-bold text-cyan-300">{hasValidAchievement ? formatPercent(achievement) : "—"}</div>
                      <p className="mt-1 text-[11px] text-slate-500">{hasValidAchievement ? "محاسبه بر اساس فروش این ماه است." : "بازهٔ معتبرِ ماه جاری برای این هدف ثبت نشده است."}</p>
                      {hasValidAchievement && <div role="progressbar" aria-label="درصد تحقق هدف" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressWidth} className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-cyan-400 transition-all" style={{ width: `${progressWidth}%` }} />
                      </div>}
                    </div>
                  </div>
                ) : <p className="text-sm text-slate-400">برای این بازه هدف فعالی ثبت نشده است.</p>}
              </Surface>
            )}

            {isViewer && (activeTab === "all" || activeTab === "sales") && (
              <Surface className="mb-5 overflow-hidden p-4 sm:p-5">
                <h2 className="mb-3 text-sm font-bold text-rose-300">بدهکاران من ({formatCount(myDebtors.length)})</h2>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[480px] border-collapse text-right text-xs">
                    <thead>
                      <tr className="border-b border-white/10 text-slate-400">
                        <th className="p-2">مشتری</th>
                        <th className="p-2">شهر</th>
                        <th className="p-2">مانده</th>
                      </tr>
                    </thead>
                    <tbody>
                      {myDebtors.length > 0 ? myDebtors.map((debtor, index) => (
                        <tr key={`${debtor.customer_name ?? debtor.name ?? "debtor"}-${index}`} className="border-b border-white/[0.06] last:border-0">
                          <td className="p-3 font-bold text-slate-100">{debtor.customer_name || debtor.name || "—"}</td>
                          <td className="p-3 text-slate-300">{debtor.city || "—"}</td>
                          <td className="p-3 text-rose-300">{formatMoney(debtor.balance)}</td>
                        </tr>
                      )) : <tr><td colSpan={3} className="p-4 text-center text-slate-400">بدهکاری ثبت نشده است.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </Surface>
            )}
          </>
        )}
      </div>
    </PortalShell>
  );
}
