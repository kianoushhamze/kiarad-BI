"use client";

import { useEffect, useState } from "react";
import { PortalShell } from "../../components/portal-shell";
import ShiftTracker from "../../components/ShiftTracker";
import LocationDiagnostic from "../../components/location-diagnostic";
import { secureApi, type SessionUser } from "../../lib/secure-api";

export default function MapPage() {
  const [user, setUser] = useState<SessionUser | null>(null);
  useEffect(() => {
    let active = true;
    secureApi<SessionUser>("/auth/me").then(value => { if (active) setUser(value); }).catch(() => {});
    return () => { active = false; };
  }, []);

  return <PortalShell title="موقعیت و شیفت کاری" eyebrow="ویزیت و حضور">
    <LocationDiagnostic />
    {user?.salesperson_id ? <ShiftTracker salespersonId={user.salesperson_id} /> : null}
    <p className="mb-3 text-xs leading-6 text-slate-400">نقشه آخرین موقعیت ثبت‌شدهٔ مجاز را نشان می‌دهد و هر ۳۰ ثانیه تازه می‌شود. فقط نقطه‌های یک ساعت اخیر نمایش داده می‌شوند.</p>
    <iframe src="/map_view.html" title="نقشهٔ آخرین موقعیت‌های ثبت‌شده" className="w-full rounded-2xl border border-white/10" style={{ height: "65vh", minHeight: "400px" }} />
  </PortalShell>;
}
