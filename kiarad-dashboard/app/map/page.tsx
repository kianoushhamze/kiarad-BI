"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { PortalShell, Surface } from "../../components/portal-shell";
import ShiftTracker from "../../components/ShiftTracker";
import { TraccarPanel } from "../live-tracking/traccar-panel";
import LocationDiagnostic from "../../components/location-diagnostic";
import { secureApi, type SessionUser } from "../../lib/secure-api";

const Bases = dynamic(() => import("../kerman-bases/workspace"));
const LiveTracking = dynamic(() => import("../live-tracking/workspace"));
type View = "shift" | "bases" | "team";
const labels: Record<View, string> = { shift: "شیفت و موقعیت من", bases: "پایگاه‌ها و ثبت حضور", team: "موقعیت زندهٔ تیم" };

export default function MapPage() {
  const [access, setAccess] = useState<{ user: SessionUser; modules: string[] }>();
  const [view, setView] = useState<View>("shift");
  const [showGps, setShowGps] = useState(false);
  const [showPersonalMap, setShowPersonalMap] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const requested = new URLSearchParams(window.location.search).get("view");
    Promise.all([secureApi<SessionUser>("/auth/me"), secureApi<{modules: string[]}>("/auth/permissions")])
      .then(([user, permissions]) => {
        if (!active) return;
        setAccess({ user, modules: permissions.modules });
        if (requested === "bases" || requested === "team") setView(requested);
      }).catch(() => { if (active) setError("دسترسی نقشه بررسی نشد."); });
    return () => { active = false; };
  }, []);
  const allowed = (name: string) => Boolean(access?.modules.some(module => module === name || module === "*"));
  const available: View[] = [];
  if (allowed("map")) available.push("shift");
  if (allowed("kerman-bases")) available.push("bases");
  if (allowed("map") && ["ceo","sales_manager"].includes(access?.user.role ?? "")) available.push("team");
  const activeView = available.includes(view) ? view : available[0];

  return <PortalShell title="نقشه و ویزیت" eyebrow="پایگاه‌ها، شیفت و موقعیت">
    {error && <p role="alert">{error}</p>}
    {!access && !error && <p role="status">در حال بررسی دسترسی…</p>}
    {access && !activeView && <p>نمای نقشه برای این حساب مجاز نیست.</p>}
    {activeView && <div className="space-y-4">
      <nav aria-label="نمای نقشه" className="flex flex-wrap gap-2">
        {available.map(item => <button type="button" key={item} aria-pressed={activeView === item} onClick={() => setView(item)}
          className={`rounded-lg border border-white/10 px-3 py-2 text-sm ${activeView === item ? "bg-violet-600 text-white" : "text-slate-300"}`}>{labels[item]}</button>)}
        {allowed("tasks") && <Link href="/my-plan" className="px-3 py-2 text-sm text-violet-300">برنامهٔ مسیر من</Link>}
      </nav>
      {activeView === "shift" && <Surface className="space-y-3 p-4">
        {access?.user.salesperson_id ? <ShiftTracker salespersonId={access.user.salesperson_id} /> : <p>برای این حساب شیفت ویزیتور تعریف نشده است.</p>}
        <button type="button" aria-expanded={showPersonalMap} onClick={() => setShowPersonalMap(value => !value)} className="text-sm text-violet-300">{showPersonalMap ? "بستن نقشهٔ آخرین موقعیت" : "نمایش نقشهٔ آخرین موقعیت"}</button>
        {showPersonalMap && <iframe src="/map_view.html" title="نقشهٔ آخرین موقعیت‌های ثبت‌شده" className="h-[60vh] min-h-80 w-full rounded-xl border border-white/10" />}
        <button type="button" aria-expanded={showGps} onClick={() => setShowGps(value => !value)} className="block text-sm text-violet-300">تنظیم GPS گوشی</button>
        {showGps && <TraccarPanel />}
        <details><summary className="cursor-pointer text-sm">بررسی اتصال موقعیت</summary><LocationDiagnostic /></details>
      </Surface>}
      {activeView === "bases" && <Bases />}
      {activeView === "team" && <LiveTracking />}
    </div>}
  </PortalShell>;
}
