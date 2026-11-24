"use client";

import { useEffect, useState } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { getSavedUser, secureApi } from "../../lib/secure-api";
import DigikalaStock from "./digikala-stock";

export default function OnlineSalesPage() {
  const [ceo, setCeo] = useState(false);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [telegram, setTelegram] = useState("");
  const [website, setWebsite] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setCeo(getSavedUser()?.role === "ceo"), 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function checkWebsite() {
    setWebsite("در حال بررسی…");
    try {
      const response = await secureApi<{ products: { stock: number }[] }>("/public/catalog");
      if (!Array.isArray(response.products) || !response.products.every(item => Number.isFinite(item.stock))) {
        throw new Error("پاسخ موجودی فروشگاه معتبر نیست.");
      }
      setWebsite(`موجودی ${response.products.length.toLocaleString("fa-IR")} کالا در کاتالوگ فروشگاه قابل دریافت است.`);
    } catch (err) {
      setWebsite(err instanceof Error ? err.message : "بررسی موجودی فروشگاه انجام نشد.");
    }
  }

  async function checkTelegram(saveToken: boolean) {
    setBusy(true);
    setTelegram("");
    try {
      if (saveToken) {
        await secureApi("/social-connect/channels/telegram", {
          method: "PUT",
          body: JSON.stringify({ credentials: { bot_token: token.trim() } }),
        });
        setToken("");
      }
      const result = await secureApi<{ message: string }>("/social-connect/channels/telegram/test", { method: "POST" });
      setTelegram(result.message);
    } catch (err) {
      setTelegram(err instanceof Error ? err.message : "بررسی اتصال تلگرام انجام نشد.");
    } finally {
      setBusy(false);
    }
  }

  return <PortalShell title="فروش آنلاین" eyebrow="کیاراد BI">
    <div className="mx-auto max-w-6xl space-y-4 p-4 lg:p-6">
      <Surface className="space-y-3 p-5">
        <h2 className="font-bold">موجودی فروشگاه سایت</h2>
        <p className="text-sm text-slate-300">موجودی فروشگاه از موجودی داشبورد پس از کسر رزروها محاسبه می‌شود.</p>
        <div className="flex flex-wrap gap-3">
          <button className={primaryButton} onClick={() => void checkWebsite()}>بررسی موجودی کاتالوگ</button>
          <a className="self-center text-sm text-violet-300" href="https://shop.kiaradhealer.ir/buy/">باز کردن فروشگاه</a>
        </div>
        {website && <p role="status" className="text-sm">{website}</p>}
      </Surface>
      <section id="telegram">
        <Surface className="space-y-3 p-5">
          <h2 className="font-bold">تلگرام</h2>
          <form className="flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); void checkTelegram(true); }}>
            <input className={fieldClass} aria-label="توکن ربات تلگرام" placeholder="توکن ربات تلگرام" type="password" autoComplete="off" dir="ltr" value={token} onChange={event => setToken(event.target.value)} />
            <button className={primaryButton} disabled={busy || !token.trim()}>ذخیره و بررسی</button>
            <button type="button" className={primaryButton} disabled={busy} onClick={() => void checkTelegram(false)}>بررسی اتصال فعلی</button>
          </form>
          {telegram && <p role="status" className="text-sm">{telegram}</p>}
        </Surface>
      </section>
      {ceo && <section id="digikala" className="space-y-3">
        <h2 className="text-lg font-bold">موجودی دیجی‌کالا</h2>
        <DigikalaStock />
      </section>}
    </div>
  </PortalShell>;
}
