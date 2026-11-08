"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** «نقشهٔ قابلیت‌ها» از منو و دسترسی خارج شد؛ لینک‌های قدیمی به مرکز فرماندهی می‌روند. */
export default function CapabilityCenterRedirect() {
  const router = useRouter();
  useEffect(function () {
    router.replace("/management");
  }, [router]);
  return (
    <div className="flex min-h-screen items-center justify-center p-6 text-sm text-slate-400">
      در حال انتقال به مرکز فرماندهی…
    </div>
  );
}
