"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type Destination = { label: string; href: string; icon: string; group: string };

const DESTINATIONS: Destination[] = [
  { label: "مرکز فرماندهی", href: "/management", icon: "⚡", group: "عمومی" },
  { label: "برنامهٔ من", href: "/my-plan", icon: "📅", group: "عمومی" },
  { label: "برنامهٔ ماهانهٔ ویزیت", href: "/monthly-plans", icon: "🗓️", group: "عمومی" },
  { label: "ورود و منبع اطلاعات", href: "/data-entry", icon: "📥", group: "عمومی" },
  { label: "عملکرد ویزیتورها (تب داشبورد مدیریت)", href: "/management", icon: "📊", group: "رشد و فروش" },
  { label: "تارگت فردی", href: "/person-targets", icon: "🎯", group: "رشد و فروش" },
  { label: "اطلاعات مشتریان", href: "/customers", icon: "👥", group: "رشد و فروش" },
  { label: "بدهکاران", href: "/debtors", icon: "🧾", group: "رشد و فروش" },
  { label: "پایگاه‌های کرمان", href: "/kerman-bases", icon: "📍", group: "رشد و فروش" },
  { label: "پیش‌فاکتورها", href: "/proformas", icon: "📄", group: "رشد و فروش" },
  { label: "پرسنل", href: "/personnel", icon: "💼", group: "تیم" },
  { label: "عملکرد تیم فروش", href: "/visitors", icon: "📋", group: "تیم" },
  { label: "حقوق و قرارداد", href: "/compensation", icon: "💵", group: "تیم" },
  { label: "فیش حقوقی", href: "/payroll", icon: "🧾", group: "تیم" },
  { label: "نقشه و ویزیت‌ها", href: "/map", icon: "🗺️", group: "تیم" },
  { label: "گزارش شبانه", href: "/daily-reports", icon: "🌙", group: "تیم" },
  { label: "CRM", href: "/crm", icon: "🤝", group: "CRM و کمپین" },
  { label: "کمپین‌ها", href: "/campaigns", icon: "🎯", group: "CRM و کمپین" },
  { label: "کالا و کانال‌ها", href: "/catalog", icon: "📦", group: "CRM و کمپین" },
  { label: "خزانه‌داری", href: "/treasury", icon: "💰", group: "مالی" },
  { label: "مدیریت کانال‌های آنلاین", href: "/online-sales", icon: "🛒", group: "فروش آنلاین" },
  { label: "مدیریت شبکه‌های اجتماعی", href: "/social", icon: "📡", group: "فضای مجازی" },
  { label: "دستیار هوشمند", href: "/assistant", icon: "🤖", group: "هوش مصنوعی" },
  { label: "اتوماسیون‌های دستیار", href: "/assistant-automations", icon: "⏱️", group: "هوش مصنوعی" },
  { label: "تسک‌ها", href: "/tasks", icon: "☑", group: "همکاری" },
  { label: "چت تیم", href: "/team-chat", icon: "💬", group: "همکاری" },
  { label: "حساب من و تغییر رمز", href: "/account", icon: "🔐", group: "همکاری" },
];

type Row = { key: string; label: string; href: string; icon: string; hint: string };

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
        setQuery("");
        setSelected(0);
      } else if (event.key === "Escape") {
        setOpen(false);
      }
    };
    const onOpenEvent = () => { setOpen(true); setQuery(""); setSelected(0); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("kiarad:command-palette", onOpenEvent);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("kiarad:command-palette", onOpenEvent);
    };
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const rows = useMemo<Row[]>(() => {
    const result: Row[] = [];
    const q = query.trim();
    if (q) {
      result.push({ key: "ask-ai", label: `پرسیدن از دستیار: «${q}»`, href: "/assistant", icon: "✨", hint: "AI" });
    }
    const needle = q.replace(/[\u200c\s]/g, "");
    for (const item of DESTINATIONS) {
      const haystack = (item.label + item.group).replace(/[\u200c\s]/g, "").toLowerCase();
      if (!needle || haystack.includes(needle.toLowerCase())) {
        result.push({ key: item.href, label: item.label, href: item.href, icon: item.icon, hint: item.group });
      }
    }
    return result.slice(0, 9);
  }, [query]);


  if (!open) return null;

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center bg-black/60 px-4 pt-[14vh] backdrop-blur-sm"
      onClick={(event) => { if (event.target === event.currentTarget) setOpen(false); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="پالت فرمان کیاراد"
        className="w-full max-w-[560px] overflow-hidden rounded-2xl border border-violet-400/30 bg-[#141830]/95 shadow-[0_30px_90px_rgba(0,0,0,.6)] backdrop-blur-2xl"
      >
        <div className="flex items-center gap-3 border-b border-white/[0.08] px-4 py-3.5">
          <span aria-hidden="true" className="text-violet-300">🔎</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => { setQuery(event.target.value); setSelected(0); }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") { event.preventDefault(); setSelected((v) => Math.min(v + 1, rows.length - 1)); }
              else if (event.key === "ArrowUp") { event.preventDefault(); setSelected((v) => Math.max(v - 1, 0)); }
              else if (event.key === "Enter" && rows[selected]) { event.preventDefault(); go(rows[selected].href); }
            }}
            placeholder="برو به، جست‌وجو کن، یا از دستیار بپرس…"
            aria-label="جست‌وجو در پنل"
            className="w-full bg-transparent text-sm text-white placeholder:text-slate-500 focus:outline-none"
          />
          <kbd className="rounded-lg border border-white/15 px-2 py-0.5 text-[10px] text-slate-400">Esc</kbd>
        </div>
        <div role="listbox" aria-label="نتایج" className="max-h-[340px] overflow-y-auto py-1">
          {rows.map((row, index) => (
            <button
              key={row.key}
              type="button"
              role="option"
              aria-selected={index === selected}
              onMouseEnter={() => setSelected(index)}
              onClick={() => go(row.href)}
              className={`flex w-full items-center gap-3 px-4 py-2.5 text-right text-[13px] transition ${index === selected ? "bg-violet-500/15 text-white" : "text-slate-400"}`}
            >
              <span aria-hidden="true">{row.icon}</span>
              <span className="truncate">{row.label}</span>
              <span className="mr-auto text-[10px] text-slate-500">{row.hint}</span>
            </button>
          ))}
          {rows.length === 0 && <p className="px-4 py-6 text-center text-xs text-slate-500">نتیجه‌ای پیدا نشد.</p>}
        </div>
        <div className="flex gap-4 border-t border-white/[0.07] px-4 py-2 text-[10px] text-slate-500">
          <span>↑↓ حرکت</span><span>↵ انتخاب</span><span>Esc بستن</span>
        </div>
      </div>
    </div>
  );
}
