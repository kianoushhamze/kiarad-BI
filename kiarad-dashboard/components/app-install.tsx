"use client";
import { useEffect, useState } from "react";
type InstallEvent = Event & { prompt(): Promise<void>; userChoice: Promise<{ outcome: string }> };
export function AppInstall() {
  const [prompt, setPrompt] = useState<InstallEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const ready = (event: Event) => { event.preventDefault(); setPrompt(event as InstallEvent); };
    const done = () => { setInstalled(true); setPrompt(null); };
    const media = window.matchMedia("(display-mode: standalone)");
    const changed = () => setInstalled(media.matches);
    void Promise.resolve().then(changed);
    media.addEventListener("change", changed);
    window.addEventListener("beforeinstallprompt", ready); window.addEventListener("appinstalled", done);
    return () => { media.removeEventListener("change", changed); window.removeEventListener("beforeinstallprompt", ready); window.removeEventListener("appinstalled", done); };
  }, []);
  async function install() {
    if (!prompt) return;
    try { await prompt.prompt(); const choice = await prompt.userChoice; setMessage(choice.outcome === "accepted" ? "درخواست نصب پذیرفته شد؛ تکمیل نصب را روی دستگاه بررسی کنید." : "نصب انجام نشد؛ بعداً از منوی مرورگر می‌توانید نصب کنید."); }
    catch { setMessage("نصب از این مرورگر انجام نشد؛ از منوی مرورگر افزودن به صفحهٔ اصلی را بزنید."); }
    finally { setPrompt(null); }
  }
  return <section className="mx-auto mb-5 max-w-xl rounded-2xl border border-white/10 p-5 text-xs leading-7 text-slate-300">
    <h2 className="text-sm font-bold text-white">وب‌اپ کیاراد روی گوشی</h2>
    <p>{installed ? "پنل در حالت برنامهٔ مستقل باز است." : "با نشانی امن تیل‌اسکیل، در منوی کروم یا اج «نصب برنامه / افزودن به صفحهٔ اصلی» را بزنید. در سافاری آیفون از اشتراک‌گذاری، «افزودن به صفحهٔ اصلی» را انتخاب کنید."}</p>
    {!installed && prompt && <button type="button" onClick={()=>void install()} className="mt-3 rounded-xl bg-violet-600 px-4 py-2 text-white">نصب وب‌اپ کیاراد</button>}
    <p className="mt-2 text-slate-500">این نسخه برای دریافت و ثبت اطلاعات به اینترنت و تیل‌اسکیل نیاز دارد؛ نصب، دقت یک‌متری یا ردیابی پیوسته در پس‌زمینه را تضمین نمی‌کند. اطلاعات مالی برای استفادهٔ آفلاین ذخیره نمی‌شود.</p>
    {message && <p role="status">{message}</p>}
  </section>;
}
