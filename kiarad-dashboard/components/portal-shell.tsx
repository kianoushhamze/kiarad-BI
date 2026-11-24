"use client";


import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ApiError, clearSession, getToken, secureApi, type SessionUser, authFetch } from "../lib/secure-api";
import { CommandPalette } from "./command-palette";

const menuGroups: { label: string; icon: string; href?: string; children?: string[][] }[] = [
  { label: "داشبورد مدیریت", icon: "📊", href: "/management" },
  { label: "برنامهٔ من", icon: "📅", href: "/my-plan" },
  { label: "مشتریان و پیگیری", icon: "👥", href: "/crm" },
  { label: "فروش", icon: "📈", children: [
    ["پیش‌فاکتورها", "/proformas", "📄"],
    ["فهرست مشتریان", "/customers", "👥"],
    ["اهداف فروش و تسویه", "/person-targets", "🎯"],
    ["عملکرد تیم فروش", "/visitors", "📋"],
    ["کالا و موجودی", "/catalog", "📦"],
  ]},
  { label: "عملیات ویزیت", icon: "🗺️", children: [
    ["برنامهٔ ماهانهٔ ویزیت", "/monthly-plans", "🗓️"],
    ["نقشه و ویزیت‌ها", "/map", "🗺️"],
    ["پایگاه‌های کرمان", "/kerman-bases", "📍"],
    ["گزارش روزانه", "/daily-reports", "🌙"],
  ]},
  { label: "مالی", icon: "💰", children: [
    ["بدهکاران", "/debtors", "🧾"],
    ["خزانه‌داری", "/treasury", "💰"],
    ["اسکن QR چک", "/check-scan", "📷"],
  ]},
  { label: "دستیار", icon: "🤖", href: "/assistant" },
  { label: "کارهای تیم", icon: "☑", href: "/tasks" },
  { label: "تیم و حقوق", icon: "💼", children: [
    ["پرسنل", "/personnel", "💼"],
    ["حقوق و قرارداد", "/compensation", "💵"],
    ["فیش حقوقی", "/payroll", "🧾"],
    ["چت تیم", "/team-chat", "💬"],
    ["آموزش و آزمون", "/training", "🎓"],
  ]},
  { label: "امکانات پیشرفته", icon: "⋯", children: [
    ["پیشنهاد مسیر", "/route-builder", "🧭"],
    ["موقعیت زندهٔ تیم", "/live-tracking", "📡"],
    ["ورود و منبع اطلاعات", "/data-entry", "📥"],
    ["مدیریت سایت و فروشگاه", "/site-cms", "🖥️"],
    ["مدیریت کانال‌های آنلاین", "/online-sales", "🛒"],
    ["مدیریت سکوهای فروش", "/platforms", "🏬"],
    ["نگاشت دیجی‌کالا", "/digikala-mapping", "🧩"],
    ["کمپین‌ها", "/campaigns", "🎯"],
    ["مارکتینگ و برندینگ", "/marketing", "📈"],
    ["مدیریت شبکه‌های اجتماعی", "/social", "📡"],
    ["مرکز فرمان تخصصی", "/agent-center", "✨"],
    ["برنامه‌های دوره‌ای و لید", "/automation-hub", "🔁"],
    ["پیام مشتری و رسید", "/outbound", "✉️"],
    ["تحلیل تخصصی و قرارداد", "/specialists", "📐"],
    ["اتوماسیون‌های دستیار", "/assistant-automations", "⏱️"],
  ]},
  { label: "حساب من و تغییر رمز", icon: "🔐", href: "/account" },
];

type NotificationItem = { key:string; title:string; message:string; href:string; severity:string; read:boolean };

export function PortalShell({ title, eyebrow, actions, children }: { title: string; eyebrow: string; actions?: ReactNode; children: ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [sessionRetry, setSessionRetry] = useState(0);
  const [allowedModules, setAllowedModules] = useState<string[] | null>(null);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [embedded, setEmbedded] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => typeof window !== "undefined" && window.localStorage.getItem("kiarad:rail") === "1");
  const setCollapsedPersist = (value: boolean) => {
    setCollapsed(value);
    try { window.localStorage.setItem("kiarad:rail", value ? "1" : "0"); } catch {}
  };
  const activeGroup = menuGroups.find((g) => g.children?.some((c) => c[1] === pathname))?.label;
  const homeHref = "/management";
  const isGroupOpen = (label: string) => openGroups[label] ?? activeGroup === label;
  const toggleGroup = (label: string) => setOpenGroups((prev) => ({
    ...prev,
    [label]: !(prev[label] ?? activeGroup === label),
  }));

  useEffect(() => {
    Promise.resolve().then(() => setEmbedded(window.self !== window.top));
  }, []);

  useEffect(() => {
    if (!user) return;
    authFetch("/auth/permissions")
      .then((r) => (r.ok ? r.json() : { modules: [] }))
      .then((d) => setAllowedModules(d.modules || []))
      .catch(() => setAllowedModules([]));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    const load = () => secureApi<{items:NotificationItem[]}>("/notifications")
      .then(data => { if (active) setNotifications(Array.isArray(data.items) ? data.items : []); })
      .catch((reason: unknown) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 401 && !getToken()) {
          setReady(false);
          setSessionError("نشست شما پایان یافته یا معتبر نیست؛ برای ورود دوباره، تلاش مجدد را بزنید.");
          return;
        }
        setNotifications([]);
      });
    void load();
    const timer = window.setInterval(load, 60_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [user]);

  const markRead = async (item: NotificationItem) => {
    if (item.read) return;
    setNotifications(current => current.map(row => row.key === item.key ? {...row, read:true} : row));
    try {
      await secureApi(`/notifications/${encodeURIComponent(item.key)}/read`, {method:"POST"});
    } catch {
      setNotifications(current => current.map(row => row.key === item.key ? {...row, read:false} : row));
    }
  };

  const goLogin = useCallback((withNext: boolean) => {
    // /login.html does not exist in the standalone build; /login does. Inside an
    // iframe the cross-origin top navigation fails silently — fall back to the
    // frame itself so the user never stays stuck on the loading state.
    const target = withNext ? `/login?next=${encodeURIComponent(pathname)}` : "/login";
    if (window.self !== window.top) {
      try {
        window.top?.location.replace(target);
        return;
      } catch {}
    }
    window.location.replace(target);
  }, [pathname]);
  useEffect(() => {
    if (!getToken()) {
      if (typeof window !== "undefined") goLogin(true);
      return;
    }
    let active = true;
    const controller = new AbortController();
    const requestToken = getToken();
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    secureApi<SessionUser>("/auth/me", {signal:controller.signal})
      .then((session) => {
        if (!active) return;
        setSessionError("");
        setUser(session);
        setReady(true);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        if (typeof window === "undefined") return;
        if (!(reason instanceof ApiError) || ![401,403].includes(reason.status)) {
          setSessionError("دریافت اطلاعات حساب به مشکل موقت سرور یا شبکه خورد. دوباره تلاش کنید.");
          return;
        }
        if (getToken() && getToken() !== requestToken) {
          setSessionRetry(value => value + 1);
          return;
        }
        clearSession();
        goLogin(false);
      }).finally(() => window.clearTimeout(timeout));
    return () => {active=false;controller.abort();window.clearTimeout(timeout);};
  }, [pathname, sessionRetry, goLogin]);

  const logout = () => {
    clearSession();
    window.location.replace("/login");
  };

  const isAllowed = (href: string) => {
    if (href === "/account" || href === "/training") return Boolean(user);
    if (["/automation-hub","/outbound","/specialists"].includes(href)) return user?.role === "ceo";
    if (href === "/agent-center") return user?.role === "ceo";
    if (href === "/assistant-automations") return user?.role === "ceo";
    if (href === "/route-builder") return user?.role === "ceo";
    if (href === "/digikala-mapping") return user?.role === "ceo";
    if (href === "/platforms") return user?.role === "ceo";
    if (href === "/site-cms") return user?.role === "ceo";
    if (href === "/check-scan") return ["ceo","finance"].includes(user?.role||"");
    if (href === "/marketing") return ["ceo","sales_manager"].includes(user?.role||"");
    if (href === "/data-entry" && !["ceo","sales_manager","finance"].includes(user?.role||"")) return false;
    if (!allowedModules) return false;
    if (href === "/personnel" && (user?.role === "salesperson" || user?.role === "visitor")) return false;
    if (allowedModules.includes("*")) return true;
    const rawModule = href.replace(/^\//, "");
    const mod = rawModule === "live-tracking" ? "map" : rawModule === "data-entry" ? "catalog" : rawModule === "monthly-plans" ? "map" : rawModule === "my-plan" ? "tasks" : rawModule === "person-targets" ? "personnel" : rawModule === "capability-center" ? "management" : rawModule;
    return allowedModules.includes(mod);
  };
  const visibleGroups = menuGroups.map((g) => {
    if (g.href) return isAllowed(g.href) ? g : null;
    const kids = (g.children || []).filter((c: string[]) => isAllowed(c[1]));
    return kids.length > 0 ? { ...g, children: kids } : null;
  }).filter((x): x is NonNullable<typeof x> => x !== null);
  const unreadCount = notifications.filter(item => !item.read).length;

  if (!ready) return <div dir="rtl" className="grid min-h-screen place-items-center bg-[#08070b] p-6 text-sm text-slate-400"><div role={sessionError ? "alert" : "status"}>{sessionError || "در حال بررسی دسترسی…"}{sessionError && <button onClick={()=>{setSessionError("");setSessionRetry(n=>n+1);}} className="mr-3 rounded-lg bg-violet-600 px-4 py-2 text-white">تلاش مجدد</button>}</div></div>;
  return <div dir="rtl" className={`kiarad-module-shell min-h-screen bg-[#08070b] text-slate-200${embedded ? " kiarad-module-embedded" : ""}`}>
    <CommandPalette destinations={visibleGroups.flatMap(group => group.href
      ? [{ label: group.label, href: group.href, icon: group.icon, group: "عمومی" }]
      : (group.children ?? []).map(([label, href, icon]) => ({ label, href, icon, group: group.label })))} />
    <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(640px_360px_at_84%_-8%,rgba(139,124,255,.22),transparent_62%),radial-gradient(520px_300px_at_6%_106%,rgba(94,197,255,.1),transparent_60%),radial-gradient(460px_280px_at_50%_55%,rgba(61,220,151,.04),transparent_65%)]" />
    {!embedded && <aside aria-label="منوی اصلی" className={`kiarad-rail fixed inset-y-0 right-0 z-40 hidden ${collapsed ? "w-[76px]" : "w-[245px]"} flex-col border-l border-white/[0.06] bg-[#0d0b16]/85 backdrop-blur-2xl lg:flex`}>
      <Link href={homeHref} title="کیاراد BI" className={`flex h-[76px] items-center gap-3 border-b border-white/[0.06] ${collapsed ? "justify-center px-0" : "px-5"}`}>
        <span className="grid h-10 w-10 place-items-center rounded-[13px] bg-gradient-to-br from-violet-400 via-violet-600 to-purple-800 font-black text-white shadow-[0_10px_26px_rgba(139,124,255,.4),inset_0_1px_0_rgba(255,255,255,.35)]">K</span>
        <span className={collapsed ? "hidden" : ""}><b className="block text-sm text-white">کیاراد BI</b><small className="text-[10px] text-slate-500">{user?.role === "salesperson" || user?.role === "visitor" ? "پنل ویزیتور" : "مرکز فرماندهی"}</small></span>
      </Link>
      <nav className={`flex-1 space-y-1 overflow-y-auto overflow-x-hidden ${collapsed ? "p-2" : "p-3"}`}>{visibleGroups.map((g) => {
        if (g.href) {
          const active = pathname === g.href;
          return <Link key={g.label} href={g.href} title={collapsed ? g.label : undefined} aria-label={g.label} className={`relative flex items-center ${collapsed ? "justify-center" : "gap-3"} rounded-xl px-3 py-3 text-xs transition duration-150 ${active ? "bg-gradient-to-l from-violet-500/20 to-violet-500/[0.06] font-medium text-violet-200" : "text-slate-500 hover:bg-white/[0.06] hover:text-white"}`}>{active && <span aria-hidden="true" className="absolute inset-y-[22%] right-0 w-[3px] rounded-full bg-violet-400 shadow-[0_0_12px_rgba(139,124,255,.9)]"/>}<span className="w-5 text-center text-base">{g.icon}</span>{!collapsed && g.label}</Link>;
        }
        const isOpen = isGroupOpen(g.label);
        const hasActive = (g.children || []).some((c: string[]) => c[1] === pathname);
        return <div key={g.label}>
          <button type="button" title={collapsed ? g.label : undefined} aria-label={g.label} onClick={() => { if (collapsed) { setCollapsedPersist(false); setOpenGroups((prev) => ({ ...prev, [g.label]: true })); } else toggleGroup(g.label); }} className={`flex w-full items-center ${collapsed ? "justify-center" : "justify-between"} rounded-xl px-3 py-3 text-xs transition ${hasActive ? "text-violet-300" : "text-slate-500 hover:bg-white/5 hover:text-white"}`}>
            <span className="flex items-center gap-3"><span className="w-5 text-center text-base">{g.icon}</span>{!collapsed && g.label}</span>
            {!collapsed && <span className="text-[10px]">{isOpen ? "▾" : "▸"}</span>}
          </button>
          {isOpen && !collapsed && <div className="mr-3 mt-1 space-y-1 border-r border-white/[0.06] pr-3">
            {(g.children || []).map((c: string[]) => {
              const active = pathname === c[1];
              return <Link key={c[1]} href={c[1]} className={`flex items-center gap-2 rounded-lg px-2 py-2 text-[11px] transition duration-150 ${active ? "bg-violet-500/15 font-medium text-violet-200" : "text-slate-500 hover:bg-white/[0.06] hover:text-white"}`}><span className="w-4 text-center">{c[2]}</span>{c[0]}</Link>;
            })}
          </div>}
        </div>;
      })}</nav>
      <div className={`border-t border-white/[0.06] ${collapsed ? "p-2" : "p-4"}`}>
        <button type="button" onClick={() => setCollapsedPersist(!collapsed)} aria-expanded={!collapsed} aria-label={collapsed ? "باز کردن منو" : "جمع کردن منو"} title={collapsed ? "باز کردن منو" : "جمع کردن منو"} className="mb-2 flex w-full items-center justify-center gap-2 rounded-lg border border-white/10 py-2 text-[11px] text-slate-400 transition hover:border-violet-400/30 hover:text-white"><span aria-hidden="true">{collapsed ? "»" : "«"}</span>{!collapsed && "جمع کردن منو"}</button>
        <Link href="/tasks" title={user?.full_name} className={`${collapsed ? "hidden" : "block"} rounded-lg px-2 py-1 hover:bg-white/5`}>
          <div className="text-xs font-bold text-white">{user?.full_name}</div>
          <div className="mt-1 text-[10px] text-slate-500">{user?.role}</div>
          <div className="mt-1 text-[9px] text-violet-400">مشاهده تسک‌های من ←</div>
        </Link>
        <button onClick={logout} title="خروج از حساب" aria-label="خروج از حساب" className={`${collapsed ? "mx-auto block" : "mt-3"} text-[10px] text-rose-300`}>{collapsed ? "⎋" : "خروج از حساب"}</button>
      </div>
    </aside>}
    <div className={`kiarad-main relative${embedded ? "" : collapsed ? " lg:mr-[76px]" : " lg:mr-[245px]"}`}>
      <header className="sticky top-0 z-30 flex min-h-[76px] flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] bg-[#0a0814]/70 px-4 backdrop-blur-2xl sm:px-7">
        <div><nav aria-label="مسیر صفحه" className="mb-2 flex flex-wrap gap-3 text-xs"><Link href={homeHref} target={embedded ? "_top" : undefined} className="text-violet-300 hover:text-white">🏠 صفحهٔ اصلی</Link>{["/payroll","/compensation","/person-targets","/visitors"].includes(pathname) && isAllowed("/personnel") && <Link href="/personnel" target={embedded ? "_top" : undefined} className="text-slate-400 hover:text-white">← پرسنل</Link>}</nav><div className="text-[10px] text-violet-400">{eyebrow}</div><h1 className="mt-1 text-lg font-extrabold text-white">{title}</h1></div>
        <div className="flex items-center gap-2">{actions}<button type="button" onClick={()=>window.dispatchEvent(new CustomEvent("kiarad:command-palette"))} aria-label="جست‌وجو و پرش سریع" className="hidden items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-[11px] text-slate-400 transition hover:border-violet-400/30 hover:text-white sm:flex">🔎 جست‌وجو… <kbd className="rounded-md border border-white/15 px-1.5 text-[9px]">Ctrl K</kbd></button><Link href="/account" target={embedded ? "_top" : undefined} aria-current={pathname === "/account" ? "page" : undefined} className="rounded-xl border border-violet-400/20 bg-violet-500/10 px-3 py-2 text-[10px] text-violet-200">🔐 تغییر رمز</Link><div className="relative"><button type="button" aria-label="اعلان‌ها" aria-expanded={notificationOpen} onClick={()=>setNotificationOpen(open=>!open)} className="relative rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 text-amber-300">🔔{unreadCount>0&&<span className="absolute -left-1 -top-1 min-w-4 rounded-full bg-rose-500 px-1 text-center text-[9px] text-white">{unreadCount.toLocaleString("fa-IR")}</span>}</button>{notificationOpen&&<div className="absolute left-0 top-11 z-50 w-[min(340px,calc(100vw-24px))] rounded-2xl border border-white/10 bg-[#15131a] p-3 shadow-2xl"><div className="mb-2 flex items-center justify-between"><b className="text-xs text-white">اعلان‌های پیگیری</b><span className="text-[10px] text-slate-500">{unreadCount.toLocaleString("fa-IR")} خوانده‌نشده</span></div><div className="max-h-80 space-y-1 overflow-y-auto">{notifications.map(item=><Link key={item.key} href={item.href} onClick={()=>{void markRead(item);setNotificationOpen(false);}} className={`block rounded-xl border p-3 ${item.read?"border-white/[0.05] bg-white/[0.02]":"border-violet-400/15 bg-violet-500/[0.07]"}`}><div className="flex items-center justify-between gap-2"><b className="text-xs text-white">{item.title}</b>{!item.read&&<span className="h-2 w-2 rounded-full bg-violet-400"/>}</div><p className="mt-1 text-[10px] leading-5 text-slate-400">{item.message}</p></Link>)}{notifications.length===0&&<p className="p-4 text-center text-xs text-slate-500">اعلان فعالی وجود ندارد.</p>}</div></div>}</div>{!embedded && <button onClick={logout} className="rounded-xl border border-white/10 px-3 py-2 text-[10px] text-slate-400 lg:hidden">خروج</button>}</div>
      </header>
      {!embedded && <div className="border-b border-white/[0.06] bg-[#0e0c12] p-2 lg:hidden"><button type="button" onClick={() => setMobileMenuOpen(true)} className="flex w-full items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-xs text-white"><span>☰ منو</span><span className="text-[10px] text-slate-400">{title}</span></button></div>}
      {mobileMenuOpen && <div className="fixed inset-0 z-50 overflow-y-auto bg-black/70 p-3 lg:hidden" onClick={() => setMobileMenuOpen(false)}>
        <div className="rounded-2xl border border-white/[0.07] bg-[#111015] p-3" onClick={(e) => e.stopPropagation()}>
          <div className="mb-2 flex items-center justify-between"><b className="text-sm text-white">منو</b><button type="button" onClick={() => setMobileMenuOpen(false)} className="rounded-lg border border-white/10 px-3 py-1 text-xs text-slate-400">بستن</button></div>
          <nav className="space-y-1">{visibleGroups.map((g) => {
            if (g.href) {
              const active = pathname === g.href;
              return <Link key={g.label} href={g.href} onClick={() => setMobileMenuOpen(false)} className={`flex items-center gap-3 rounded-xl px-3 py-3 text-xs transition ${active ? "bg-violet-500/15 text-violet-300" : "text-slate-400"}`}><span className="w-5 text-center text-base">{g.icon}</span>{g.label}</Link>;
            }
            const isOpen = isGroupOpen(g.label);
            const hasActive = (g.children || []).some((c: string[]) => c[1] === pathname);
            return <div key={g.label}>
              <button type="button" onClick={() => toggleGroup(g.label)} className={`flex w-full items-center justify-between rounded-xl px-3 py-3 text-xs ${hasActive ? "text-violet-300" : "text-slate-400"}`}>
                <span className="flex items-center gap-3"><span className="w-5 text-center text-base">{g.icon}</span>{g.label}</span>
                <span className="text-[10px]">{isOpen ? "▾" : "▸"}</span>
              </button>
              {isOpen && <div className="mr-3 mt-1 space-y-1 border-r border-white/[0.06] pr-3">
                {(g.children || []).map((c: string[]) => {
                  const active = pathname === c[1];
                  return <Link key={c[1]} href={c[1]} onClick={() => setMobileMenuOpen(false)} className={`flex items-center gap-2 rounded-lg px-2 py-2 text-[11px] ${active ? "bg-violet-500/15 text-violet-200" : "text-slate-400"}`}><span className="w-4 text-center">{c[2]}</span>{c[0]}</Link>;
                })}
              </div>}
            </div>;
          })}</nav>
          <div className="mt-3 border-t border-white/[0.06] pt-3"><Link href="/tasks" onClick={() => setMobileMenuOpen(false)} className="block rounded-lg px-2 py-1"><div className="text-xs font-bold text-white">{user?.full_name}</div><div className="mt-1 text-[10px] text-slate-500">{user?.role}</div></Link><button onClick={logout} className="mt-3 text-[10px] text-rose-300">خروج از حساب</button></div>
        </div>
      </div>}
      <main className={`mx-auto max-w-[1500px] ${embedded ? "p-3 sm:p-5" : "p-4 sm:p-6 lg:p-7"}`}>{children}</main>
    </div>
  </div>;
}

export function Surface({ children, className = "" }: { children: ReactNode; className?: string }) {
  // Kiarad 2030 shared glass surface — every module page inherits the visual
  // identity through this component plus the global tokens in globals.css.
  return <section className={`rounded-[20px] border border-white/[0.08] bg-white/[0.045] shadow-[0_10px_35px_rgba(0,0,0,.14)] backdrop-blur-md transition-colors kiarad-glass ${className}`}>{children}</section>;
}

export const fieldClass = "w-full rounded-xl border border-white/[0.08] bg-black/20 px-3 py-2.5 text-xs text-white outline-none placeholder:text-slate-600 transition-colors focus:border-violet-400/50 focus:bg-black/30";
export const primaryButton = "rounded-xl bg-gradient-to-br from-violet-500 to-purple-700 px-4 py-2.5 text-xs font-bold text-white shadow-[0_6px_18px_rgba(139,124,255,.28)] transition hover:from-violet-400 hover:to-purple-600 disabled:opacity-50";


export default PortalShell;
