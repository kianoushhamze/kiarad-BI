import type { RefObject } from "react";
import { fieldClass } from "../../components/portal-shell";

const labels: Record<string, string> = {
  open: "باز", cleared: "پاس‌شده", spent: "خرج‌شده", bounced: "برگشتی", cancelled: "لغوشده",
};
const fields = {
  account_holder: "صاحب حساب", national_id: "کد ملی صاحب حساب", bank_name: "نام بانک",
  branch_name: "شعبه", sayad_id: "شناسهٔ ۱۶ رقمی صیاد", spent_for: "محل مصرف چک خرج‌شده",
};
export type CheckDetails = Partial<Record<keyof typeof fields, string>> & { sayad_registration?: string; visitor_user_id?: number | null };

export function checkPayload(form: FormData) {
  const check_details = Object.fromEntries(Object.keys(fields).map(name => [name, String(form.get(name) ?? "").trim()]));
  check_details.sayad_registration = String(form.get("sayad_registration") || "unknown");
  return { status: String(form.get("check_status") || "open"), check_details };
}

export function checkStatusLabel(status: string) {
  return labels[status] ?? (status === "settled" ? labels.cleared : status);
}

export function CheckFields({ details, status, sayadRef }: {
  details?: CheckDetails; status?: string; sayadRef?: RefObject<HTMLInputElement | null>;
}) {
  const statuses = { ...labels };
  if (status === "overdue") statuses.overdue = "سررسیدگذشته";
  if (status === "settled") statuses.settled = "تسویه‌شده";
  return <fieldset className="grid gap-2 rounded-xl border border-white/10 p-3 sm:grid-cols-2">
    <legend className="px-2 text-xs">مشخصات چک</legend>
    <label className="text-xs">وضعیت چک
      <select name="check_status" defaultValue={status && status in statuses ? status : "open"} className={fieldClass}>
        {Object.entries(statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
    <label className="text-xs">وضعیت ثبت در صیاد
      <select name="sayad_registration" defaultValue={details?.sayad_registration || "unknown"} className={fieldClass}>
        <option value="unknown">نامشخص</option><option value="registered">ثبت‌شده</option><option value="unregistered">ثبت‌نشده</option>
      </select>
    </label>
    {Object.entries(fields).map(([name, label]) => {
      const numeric = name === "national_id" || name === "sayad_id";
      return <label key={name} className="text-xs">{label}
        <input name={name} ref={name === "sayad_id" ? sayadRef : undefined}
          defaultValue={details?.[name as keyof typeof fields] ?? ""} className={fieldClass}
          inputMode={numeric ? "numeric" : undefined} dir={numeric ? "ltr" : undefined}
          maxLength={name === "national_id" ? 10 : name === "sayad_id" ? 16 : name === "account_holder" ? 200 : name === "spent_for" ? 300 : 120} />
      </label>;
    })}
  </fieldset>;
}
