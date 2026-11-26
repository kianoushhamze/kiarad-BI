import { useEffect, useState } from "react";
import { Surface } from "../../components/portal-shell";
import { formatIranDate } from "../../lib/iran-date";
import { secureApi } from "../../lib/secure-api";

type AssignedCheck = {
  id: number;
  counterparty: string;
  amount: number;
  due_date: string;
  status: "open" | "overdue" | "bounced";
  document_type: string;
};

const statuses = { open: "باز", overdue: "سررسیدگذشته", bounced: "برگشتی" };

export function AssignedChecks() {
  const [checks, setChecks] = useState<AssignedCheck[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    void secureApi<AssignedCheck[]>("/treasury/my-checks").then(items => {
      if (active) setChecks(items);
    }).catch(() => {
      if (active) setFailed(true);
    });
    return () => { active = false; };
  }, []);

  return <Surface className="p-4">
    <h2 className="font-bold">چک‌های باز من</h2>
    {failed ? <p role="alert">دریافت فهرست چک‌ها ناموفق بود.</p>
      : checks === null ? <p role="status">در حال دریافت چک‌ها…</p>
      : checks.length === 0 ? <p>چک بازی به شما اختصاص داده نشده است.</p>
      : <ul className="mt-2 divide-y divide-white/10">
        {checks.map(check => <li key={check.id} className="flex flex-wrap justify-between gap-2 py-2 text-sm">
          <span>{check.counterparty} · {check.document_type.startsWith("receivable") ? "دریافتنی" : "پرداختنی"}</span>
          <span>{Number(check.amount).toLocaleString("fa-IR")} ریال · {formatIranDate(check.due_date)} · {statuses[check.status]}</span>
        </li>)}
      </ul>}
  </Surface>;
}
