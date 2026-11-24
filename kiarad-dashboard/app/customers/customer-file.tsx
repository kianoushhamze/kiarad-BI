"use client";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { IranDateInput } from "../../components/IranDateInput";
import { formatIranDate } from "../../lib/iran-date";
import { secureApi } from "../../lib/secure-api";

type Contact = { name: string; code?: string; city?: string; phone?: string };
type FileData = {
  customer: Contact;
  can_edit: boolean;
  can_write_cards: boolean;
  can_archive_cards: boolean;
  finance?: {
    holoo_balance?: { signed_balance_irr: number; report_date: string };
    last_sale?: { date: string; total_amount: number };
  };
};
type Card = { id: number; status: string; notes?: string; visitor_name?: string; followup_date?: string; followup_time?: string };
const stages = ["در انتظار تماس", "پیگیری شد", "نیاز به پیش‌فاکتور", "سفارش ثبت شد", "عدم تمایل فعلی"];
const toman = (value: number) => (Math.abs(Number(value))/10).toLocaleString("fa-IR", { maximumFractionDigits: 1 }) + " تومان";
const emptyDraft = { notes: "", followup_date: "", followup_time: "" };

export function CustomerFile({ id, onClose, onUpdate }: { id: number; onClose: () => void; onUpdate: (contact?: Contact) => void }) {
  const [file, setFile] = useState<FileData>();
  const [cards, setCards] = useState<Card[]>([]);
  const [error, setError] = useState("");
  const [crmError, setCrmError] = useState("");
  const [busy, setBusy] = useState(false);
  const [contact, setContact] = useState<Contact | null>(null);
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [archive, setArchive] = useState<number | null>(null);
  const path = `/directory/customers/${id}`;
  const crmPath = `/crm/interactions?customer_id=${id}`;
  useEffect(() => {
    let active = true;
    void secureApi<FileData>(path).then(data => { if (active) setFile(data); })
      .catch(reason => { if (active) setError(reason.message); });
    void secureApi<Card[]>(crmPath).then(data => { if (active) setCards(data); })
      .catch(reason => { if (active) setCrmError(reason.message); });
    return () => { active = false; };
  }, [path, crmPath]);

  async function update(run: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try { await run(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "تغییر ذخیره نشد."); }
    finally { setBusy(false); }
  }

  function saveCard(event: FormEvent) {
    event.preventDefault();
    void update(async () => {
      const creating = editing === "new";
      await secureApi(creating ? "/crm/interactions" : `/crm/interactions/${editing}`, {
        method: creating ? "POST" : "PATCH",
        body: JSON.stringify(creating
          ? { customer_id: id, visitor_name: "", notes: draft.notes, next_followup_date: draft.followup_date, followup_time: draft.followup_time }
          : draft),
      });
      setEditing(null);
      setCards(await secureApi<Card[]>(crmPath));
    });
  }

  return <div className="space-y-4">
    <button onClick={onClose} className="text-sm text-violet-300">بازگشت به فهرست مشتریان</button>
    {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
    {!file ? (!error && <p>در حال دریافت پرونده…</p>) : <>
      <Surface className="space-y-3 p-4">
        <h2 className="text-lg font-bold">{file.customer.name}</h2>
        <p className="text-sm text-slate-300">کد {file.customer.code || "—"} · {file.customer.city || "شهر نامشخص"} · <bdi>{file.customer.phone || "بدون شماره"}</bdi></p>
        <div className="flex flex-wrap gap-3 text-sm text-violet-300">
          <Link href={`/proformas#customer=${encodeURIComponent(file.customer.name)}`}>پیش‌فاکتور</Link>
          {file.can_edit && <button onClick={() => setContact(file.customer)}>ویرایش مشخصات</button>}
        </div>
        {contact && <form className="grid gap-2 sm:grid-cols-3" onSubmit={event => {
          event.preventDefault();
          void update(async () => {
            const values = { name: contact.name, city: contact.city || "", phone: contact.phone || "" };
            await secureApi(path, { method: "PATCH", body: JSON.stringify(values) });
            setFile({ ...file, customer: { ...file.customer, ...values } });
            onUpdate(values);
            setContact(null);
          });
        }}>
          <label>نام<input className={fieldClass} required maxLength={150} value={contact.name} onChange={e => setContact({...contact, name:e.target.value})}/></label>
          <label>شهر<input className={fieldClass} maxLength={100} value={contact.city ?? ""} onChange={e => setContact({...contact, city:e.target.value})}/></label>
          <label>تماس<input className={fieldClass} maxLength={30} value={contact.phone ?? ""} onChange={e => setContact({...contact, phone:e.target.value})}/></label>
          <button className={primaryButton} disabled={busy}>ذخیرهٔ مشخصات</button>
          <button type="button" onClick={() => setContact(null)}>انصراف</button>
        </form>}
      </Surface>
      {file.finance && <Surface className="space-y-2 p-4">
        <h2 className="font-bold">مالی</h2>
        {file.finance.holoo_balance ? <p className="text-sm">
          ماندهٔ هلو {toman(file.finance.holoo_balance.signed_balance_irr)} · {file.finance.holoo_balance.signed_balance_irr > 0 ? "بدهکار" : file.finance.holoo_balance.signed_balance_irr < 0 ? "بستانکار" : "صفر"}
          {" · "}{formatIranDate(file.finance.holoo_balance.report_date)}
        </p> : <p className="text-sm">ماندهٔ معتبر هلو در آخرین همگام‌سازی پیدا نشد.</p>}
        {file.finance.last_sale && <p className="text-sm">آخرین فروش ثبت‌شده · {formatIranDate(file.finance.last_sale.date)} · {toman(file.finance.last_sale.total_amount)}</p>}
      </Surface>}
      <Surface className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold">کانبان پیگیری مشتری</h2>
          {file.can_write_cards && !crmError && <button className={primaryButton} onClick={() => { setDraft(emptyDraft); setEditing("new"); }}>افزودن پیگیری</button>}
        </div>
        {crmError && <p className="text-sm text-amber-300">{crmError}</p>}
        {editing !== null && <form onSubmit={saveCard} className="grid gap-2 rounded-lg bg-white/5 p-3 sm:grid-cols-2">
          <label className="sm:col-span-2">یادداشت<textarea className={fieldClass} maxLength={5000} value={draft.notes} onChange={e => setDraft({...draft, notes:e.target.value})}/></label>
          <IranDateInput aria-label="تاریخ پیگیری" className={fieldClass} value={draft.followup_date} onChange={value => setDraft({...draft, followup_date:value})}/>
          <input aria-label="ساعت پیگیری" type="time" className={fieldClass} value={draft.followup_time} onChange={e => setDraft({...draft, followup_time:e.target.value})}/>
          <button className={primaryButton} disabled={busy || (!draft.notes.trim() && !draft.followup_date)}>ذخیرهٔ پیگیری</button>
          <button type="button" disabled={busy} onClick={() => setEditing(null)}>انصراف</button>
        </form>}
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {[...stages, ...new Set(cards.map(card => card.status).filter(status => !stages.includes(status)))].map(stage =>
            <section key={stage} className="min-w-0 rounded-xl bg-white/5 p-2">
              <h3 className="mb-2 text-xs font-bold">{stage}</h3>
              {cards.filter(card => card.status === stage).map(card => <article key={card.id} className="mb-2 space-y-2 break-words rounded-lg border border-white/10 p-2 text-xs">
                <p>{card.notes || "یادآوری"}</p>
                <p className="text-slate-400">{card.visitor_name}{card.followup_date ? " · " + formatIranDate(card.followup_date) : ""} {card.followup_time}</p>
                <select aria-label="وضعیت پیگیری" className={fieldClass} disabled={busy || !file.can_write_cards} value={card.status} onChange={e => {
                  const status = e.target.value;
                  void update(async () => {
                    await secureApi(`/crm/interactions/${card.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
                    setCards(current => current.map(item => item.id === card.id ? {...item, status} : item));
                  });
                }}>{!stages.includes(card.status) && <option value={card.status}>{card.status}</option>}{stages.map(value => <option key={value}>{value}</option>)}</select>
                {file.can_write_cards && <button disabled={busy} className="text-violet-300" onClick={() => {setEditing(card.id);setDraft({notes:card.notes ?? "", followup_date:card.followup_date ?? "", followup_time:card.followup_time ?? ""});}}>ویرایش</button>}
                {file.can_archive_cards && (archive === card.id ? <div className="flex flex-wrap gap-2">
                  <button disabled={busy} className="text-rose-300" onClick={() => void update(async () => {
                    await secureApi(`/crm/interactions/${card.id}`, {method:"DELETE"});
                    setCards(items => items.filter(item => item.id !== card.id));
                    if (editing === card.id) setEditing(null);
                    setArchive(null);
                  })}>تأیید بایگانی</button>
                  <button onClick={() => setArchive(null)}>انصراف</button>
                </div> : <button className="mr-3 text-rose-300" onClick={() => setArchive(card.id)}>بایگانی</button>)}
              </article>)}
            </section>)}
        </div>
      </Surface>
    </>}
  </div>;
}
