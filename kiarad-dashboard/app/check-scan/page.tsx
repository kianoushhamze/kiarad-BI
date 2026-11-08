"use client";
import { PortalShell } from "../../components/portal-shell";
import { Surface } from "../../components/portal-shell";
import { CheckScanner } from "../../components/check-scanner";

export default function CheckScanPage() {
  return <PortalShell title="ثبت چک با دوربین" eyebrow="خزانه‌داری هوشمند">
    <div className="mx-auto max-w-4xl space-y-5 p-4 lg:p-6">
      <Surface className="space-y-4 p-5">
        <h2 className="text-base font-bold">گرفتن QR چک صیادی</h2>
        <CheckScanner showSummary />
        <p className="text-[10px] text-slate-500">مبالغ و تاریخ سررسید را در فرم خزانه به‌صورت دستی تکمیل کن.</p>
        <a href="/treasury" className="inline-block text-violet-300">ثبت دستی چک در خزانه ←</a>
      </Surface>
      <a href="/treasury" className="block text-violet-300">بازگشت به خزانه‌داری</a>
    </div>
  </PortalShell>;
}
