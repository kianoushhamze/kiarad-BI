"use client";

import { useState, type FormEvent } from "react";
import { PortalShell, Surface, fieldClass } from "../../components/portal-shell";
import { saveSession, secureApi, type SessionUser } from "../../lib/secure-api";
import { AppInstall } from "../../components/app-install";

type PasswordResponse = { access_token: string; token_type: string; user: SessionUser };

export default function AccountPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;
    setError("");
    setSuccess("");
    if (newPassword.length < 10 || newPassword.length > 200) {
      setError("رمز جدید باید بین ۱۰ و ۲۰۰ نویسه باشد.");
      return;
    }
    if (newPassword !== confirmation) {
      setError("رمز جدید و تکرار آن یکسان نیستند.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("رمز جدید باید با رمز فعلی تفاوت داشته باشد.");
      return;
    }
    setSaving(true);
    try {
      const session = await secureApi<PasswordResponse>("/auth/password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!session.access_token || !session.user) throw new Error("دریافت نشست جدید ناموفق بود؛ دوباره وارد حساب شوید.");
      saveSession(session.access_token, session.user);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setSuccess("رمز عبور تغییر کرد. ورود فعلی شما برقرار است و برای ورودهای بعدی از رمز جدید استفاده کنید.");
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "تغییر رمز انجام نشد؛ دوباره تلاش کنید.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <PortalShell title="حساب من و تغییر رمز" eyebrow="تنظیمات حساب">
      <AppInstall />
      <Surface className="mx-auto max-w-xl p-5 sm:p-7">
        <h2 className="text-base font-bold text-white">تغییر رمز عبور</h2>
        <p className="mt-2 text-xs leading-6 text-slate-400">رمز فعلی حساب خودتان را وارد کنید و یک رمز جدید با حداقل ۱۰ نویسه انتخاب کنید.</p>
        <form onSubmit={changePassword} className="mt-6 space-y-5" aria-busy={saving}>
          <div>
            <label htmlFor="current-password" className="mb-2 block text-xs text-slate-300">رمز فعلی</label>
            <input id="current-password" name="current_password" type="password" autoComplete="current-password" required minLength={1} maxLength={200} value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} disabled={saving} className={fieldClass} dir="ltr" />
          </div>
          <div>
            <label htmlFor="new-password" className="mb-2 block text-xs text-slate-300">رمز جدید</label>
            <input id="new-password" name="new_password" type="password" autoComplete="new-password" required minLength={10} maxLength={200} value={newPassword} onChange={event => setNewPassword(event.target.value)} disabled={saving} className={fieldClass} dir="ltr" />
          </div>
          <div>
            <label htmlFor="confirm-password" className="mb-2 block text-xs text-slate-300">تکرار رمز جدید</label>
            <input id="confirm-password" name="confirm_password" type="password" autoComplete="new-password" required minLength={10} maxLength={200} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={saving} className={fieldClass} dir="ltr" />
          </div>
          {error && <p role="alert" className="rounded-xl border border-rose-400/20 bg-rose-500/10 p-3 text-xs leading-6 text-rose-200">{error}</p>}
          {success && <p role="status" className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-3 text-xs leading-6 text-emerald-200">{success}</p>}
          <button type="submit" disabled={saving} className="w-full rounded-xl bg-violet-600 px-4 py-3 text-xs font-bold text-white transition hover:bg-violet-500 disabled:cursor-wait disabled:opacity-50">{saving ? "در حال تغییر رمز…" : "ذخیرهٔ رمز جدید"}</button>
        </form>
      </Surface>
    </PortalShell>
  );
}
