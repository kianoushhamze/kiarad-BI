"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { clearSession, getSavedUser, getToken, secureApi, type SessionUser } from "../lib/secure-api";
import { AssistantChat } from "./assistant-chat";

const links = [
  ["نمای کلی", "/management", "📊"],
  ["گزارش عملکرد و فیش‌ها", "/visitors", "📈"],
  ["تعریف و فرمول ویزیتورها", "/manager", "👥"],
  ["تسک‌ها", "/tasks", "☑"],
  ["گزارش شبانه", "/daily-reports", "📰"],
  ["خزانه‌داری", "/treasury", "◈"],
  ["کالا و کانال‌ها", "/catalog", "⊞"],
  ["پنل عملیات ویزیتور", "/personnel", "💼"]
];

export function PortalShell({ title, eyebrow, actions, children }: { title: string; eyebrow: string; actions?: ReactNode; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);

  useEffect(() => {
    setUser(getSavedUser());
    if (!getToken()) {
      setReady(true);
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    secureApi<SessionUser>("/auth/me")
      .then(setUser)
      .catch(() => router.replace("/login"))
      .finally(() => setReady(true));
  }, [pathname, router]);

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  const visibleLinks = user?.role === "finance"
    ? links.filter(([, href]) => href === "/treasury")
    : user?.role === "salesperson"
      ? links.filter(([, href]) => ["/visitors", "/manager", "/tasks", "/daily-reports", "/personnel"].includes(href))
      : links;

  if (!ready) return <div dir="rtl" className="grid min-h-screen place-items-center bg-[#070810] text-sm text-slate-500">در حال بررسی دسترسی…</div>;

  return <div dir="rtl" className="min-h-screen bg-[#070810] text-slate-200">
    <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_78%_-10%,rgba(124,58,237,.18),transparent_32%),radial-gradient(circle_at_8%_95%,rgba(34,211,238,.07),transparent_24%)]" />
    <aside className="fixed inset-y-0 right-0 z-40 hidden w-[245px] flex-col border-l border-white/[0.07] bg-[#0b0d17]/95 lg:flex">
      <Link href="/management" className="flex h-[76px] items-center gap-3 border-b border-white/[0.07] px-5">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-700 font-black text-white">K</span>
        <span><b className="block text-sm text-white">کیاراد BI</b><small className="text-[10px] text-slate-500">مرکز فرماندهی کسب‌وکار</small></span>
      </Link>
      <nav className="flex-1 space-y-1 p-3">{visibleLinks.map(([label, href, icon]) => {
        const active = pathname === href;
        return <Link key={href} href={href} className={`flex items-center gap-3 rounded-xl px-3 py-3 text-xs transition ${active ? "bg-violet-500/15 text-violet-300 ring-1 ring-violet-400/15" : "text-slate-500 hover:bg-white/5 hover:text-white"}`}><span className="w-5 text-center text-base">{icon}</span>{label}</Link>;
      })}</nav>
      <div className="border-t border-white/[0.06] p-4"><div className="text-xs font-bold text-white">{user?.full_name}</div><div className="mt-1 text-[10px] text-slate-500">{user?.role}</div><button onClick={logout} className="mt-3 text-[10px] text-rose-300">خروج از حساب</button></div>
    </aside>
    <div className="relative lg:mr-[245px]">
      <header className="sticky top-0 z-30 flex min-h-[76px] items-center justify-between border-b border-white/[0.07] bg-[#070810]/90 px-4 backdrop-blur-xl sm:px-7">
        <div><div className="text-[10px] text-violet-400">{eyebrow}</div><h1 className="mt-1 text-lg font-extrabold text-white">{title}</h1></div>
        <div className="flex items-center gap-2">{actions}<button onClick={logout} className="rounded-xl border border-white/10 px-3 py-2 text-[10px] text-slate-400 lg:hidden">خروج</button></div>
      </header>
      <div className="border-b border-white/[0.06] bg-[#0b0d17] p-2 lg:hidden"><div className="flex gap-2 overflow-x-auto">{visibleLinks.map(([label, href]) => <Link key={href} href={href} className={`shrink-0 rounded-lg px-3 py-2 text-[10px] ${pathname === href ? "bg-violet-600 text-white" : "text-slate-500"}`}>{label}</Link>)}</div></div>
      <main className="mx-auto max-w-[1500px] p-4 sm:p-6 lg:p-7">{children}</main>
    </div>
    <button onClick={() => setAssistantOpen(true)} className="fixed bottom-5 left-5 z-40 flex items-center gap-2 rounded-2xl border border-violet-300/20 bg-violet-600 px-4 py-3 text-xs font-bold text-white shadow-[0_0_40px_rgba(124,58,237,.4)] hover:bg-violet-500"><span className="text-base">✦</span><span className="hidden sm:inline">از دستیار کیاراد بپرس</span></button>
    <AssistantChat open={assistantOpen} onClose={() => setAssistantOpen(false)} />
  </div>;
}

export function Surface({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-white/[0.07] bg-white/[0.035] ${className}`}>{children}</section>;
}

export const fieldClass = "w-full rounded-xl border border-white/[0.08] bg-black/20 px-3 py-2.5 text-xs text-white outline-none placeholder:text-slate-700 focus:border-violet-400/40";
export const primaryButton = "rounded-xl bg-violet-600 px-4 py-2.5 text-xs font-bold text-white hover:bg-violet-500 disabled:opacity-50";


export default PortalShell;
