"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { PortalShell, Surface, fieldClass, primaryButton } from "../../components/portal-shell";
import { secureApi } from "../../lib/secure-api";
import { formatIranDateTime, iranDateTimeInputToIso, iranTodayIso } from "../../lib/iran-date";
import { IranDateTimeInput } from "../../components/IranDateTimeInput";

type ContentItem = {
  id: number;
  channel: string;
  title: string;
  body: string;
  scheduled_at: string;
  status: "pending" | "approved" | "rejected";
  review_note?: string;
};
type CalendarResponse = { items: ContentItem[]; can_review: boolean; publishing_enabled: false };

type ChannelInfo = {
  platform: string;
  status: string;
  configured: boolean;
  last_checked_at: string | null;
  credentials: Record<string, string>;
};
type ChannelsResponse = { channels: ChannelInfo[] };

const channels = [
  ["instagram", "اینستاگرام"], ["telegram", "تلگرام"], ["bale", "بله"],
  ["rubika", "روبیکا"], ["whatsapp", "واتس‌اپ"], ["linkedin", "لینکدین"],
  ["youtube", "یوتیوب"], ["tiktok", "تیک‌تاک"],
];

const channelOptions = channels;
const channelsPlaceholder: ChannelInfo[] = channels.map(([key]) => ({
  platform: key, status: "disconnected", configured: false, last_checked_at: null, credentials: {},
}));

const statusBadge = (status: string) => {
  if (status === "connected") return "bg-emerald-500/15 text-emerald-300";
  if (status === "error") return "bg-rose-500/15 text-rose-300";
  if (status === "not_implemented") return "bg-slate-500/15 text-slate-300";
  return "bg-amber-500/15 text-amber-300";
};
const statusLabel = (status: string) => ({
  disconnected: "متصل نشده", connected: "متصل", error: "خطا در اتصال", not_implemented: "بدون API رسمی",
}[status] ?? status);

const channelName = (id: string) => channels.find(([key]) => key === id)?.[1] ?? id;
const statusName = (status: string) => status === "pending" ? "در انتظار بازبینی" : status === "approved" ? "تأییدشده" : "ردشده";

type CredentialRow = { key: string; value: string };

function ChannelCard({ info, busy, onSaved }: {
  info: ChannelInfo; busy: boolean; onSaved: (msg: string) => void;
}) {
  const [rows, setRows] = useState<CredentialRow[]>(() => {
    const stored = Object.entries(info.credentials ?? {}).map(([key]) => ({ key, value: "" }));
    const defaults: Record<string, string[]> = { telegram: ["bot_token"] };
    const wanted = defaults[info.platform] ?? ["token"];
    const have = new Set(stored.map(r => r.key));
    return [...stored, ...wanted.filter(k => !have.has(k)).map(key => ({ key, value: "" }))];
  });
  const setRow = (index: number, patch: Partial<CredentialRow>) =>
    setRows(prev => prev.map((r, i) => i === index ? { ...r, ...patch } : r));

  const save = async () => {
    const credentials = Object.fromEntries(rows.filter(r => r.key.trim() && r.value.trim()).map(r => [r.key.trim(), r.value.trim()]));
    if (!Object.keys(credentials).length) { onSaved("حداقل یک کلید و مقدار اعتبارنامه وارد کنید."); return; }
    try {
      await secureApi(`/social-connect/channels/${info.platform}`, {
        method: "PUT", body: JSON.stringify({ credentials }),
      });
      onSaved(`اعتبارنامهٔ ${channelName(info.platform)} ذخیره شد (وضعیت: متصل نشده).`);
    } catch (error) {
      onSaved(error instanceof Error ? error.message : "ذخیرهٔ اعتبارنامه انجام نشد.");
    }
  };

  const test = async () => {
    try {
      const result = await secureApi<{ platform: string; status: string; message?: string }>(`/social-connect/channels/${info.platform}/test`, { method: "POST" });
      onSaved(`${channelName(info.platform)}: ${result.message ?? statusLabel(result.status)}`);
    } catch (error) {
      onSaved(error instanceof Error ? error.message : "تست اتصال انجام نشد.");
    }
  };

  return <Surface className="p-5">
    <div className="flex items-center justify-between">
      <h3 className="text-sm font-bold text-white">{channelName(info.platform)}</h3>
      <span className={`rounded-full px-2 py-1 text-[10px] ${statusBadge(info.status)}`}>{statusLabel(info.status)}</span>
    </div>
    <div className="mt-3 grid gap-2">
      {rows.map((row, index) => <div key={index} className="flex gap-2">
        <input value={row.key} onChange={(e) => setRow(index, { key: e.target.value })} dir="ltr"
          placeholder="کلید (مثل bot_token)" className={`${fieldClass} w-1/2 text-left`} />
        <input value={row.value} onChange={(e) => setRow(index, { value: e.target.value })} dir="ltr" type="password"
          placeholder={info.credentials?.[row.key] ?? "مقدار"} className={`${fieldClass} w-1/2 text-left`} />
      </div>)}
      <button type="button" onClick={() => setRows(prev => [...prev, { key: "", value: "" }])}
        className="text-right text-[10px] text-violet-300">+ افزودن کلید</button>
      {info.last_checked_at && <div className="text-[10px] text-slate-500">آخرین تست: {formatIranDateTime(info.last_checked_at)}</div>}
      <div className="mt-1 flex gap-2">
        <button type="button" disabled={busy} onClick={() => void save()} className={primaryButton}>ذخیره</button>
        <button type="button" disabled={busy} onClick={() => void test()}
          className="rounded-xl border border-white/10 bg-white/[0.06] px-4 py-2 text-xs font-bold text-slate-200">تست اتصال</button>
      </div>
    </div>
  </Surface>;
}

export default function SocialPage() {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [canReview, setCanReview] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [channelInfos, setChannelInfos] = useState<ChannelInfo[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await secureApi<CalendarResponse>("/integrations/content-calendar");
      setItems(result.items ?? []);
      setCanReview(Boolean(result.can_review));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "دریافت تقویم محتوا انجام نشد.");
    } finally {
      setLoading(false);
    }
    try {
      const chan = await secureApi<ChannelsResponse>("/social-connect/channels");
      setChannelInfos(chan.channels ?? []);
    } catch {
      setChannelInfos([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void load(); });
    return () => { active = false; };
  }, [load]);

  const createDraft = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const scheduledAt = iranDateTimeInputToIso(String(form.get("scheduled_at") ?? ""));
    if (!scheduledAt) { setMessage("تاریخ و ساعت معتبر وارد کنید."); return; }
    setBusy(true);
    try {
      await secureApi("/integrations/content-calendar", {
        method: "POST",
        body: JSON.stringify({ channel: form.get("channel"), title: form.get("title"), body: form.get("body"), scheduled_at: scheduledAt }),
      });
      formElement.reset();
      setMessage("پیش‌نویس برای بازبینی ثبت شد.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ثبت پیش‌نویس انجام نشد.");
    } finally { setBusy(false); }
  };

  const review = async (itemId: number, decision: "approved" | "rejected") => {
    setBusy(true);
    try {
      await secureApi(`/integrations/content-calendar/${itemId}/review`, {
        method: "POST", body: JSON.stringify({ decision, note: "" }),
      });
      setMessage(decision === "approved" ? "پیش‌نویس تأیید شد؛ انتشار همچنان دستی است." : "پیش‌نویس رد شد.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "بازبینی انجام نشد.");
    } finally { setBusy(false); }
  };

  return <PortalShell title="تقویم شبکه‌های اجتماعی" eyebrow="پیش‌نویس و بازبینی محتوا">
    <div className="mb-4 rounded-xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs leading-6 text-amber-100">
      این بخش فقط برای برنامه‌ریزی، پیش‌نویس و بازبینی داخلی است. اتصال به حساب‌ها و انتشار خودکار فعال نیست.
    </div>
    {message && <div className="mb-4 rounded-xl border border-violet-400/20 bg-violet-500/10 p-3 text-xs text-violet-200">{message}</div>}
    <div className="grid gap-4 xl:grid-cols-[.8fr_1.2fr]">
      <Surface className="p-5">
        <h2 className="text-sm font-bold text-white">ثبت پیش‌نویس محتوا</h2>
        <form onSubmit={createDraft} className="mt-4 grid gap-3">
          <label className="text-xs text-slate-400">کانال<select name="channel" className={`${fieldClass} mt-1`} required>{channelOptions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <input name="title" required maxLength={200} placeholder="عنوان محتوا" className={fieldClass}/>
          <textarea name="body" required maxLength={10000} rows={6} placeholder="متن پیشنهادی" className={fieldClass}/>
          <label className="text-xs text-slate-400">زمان پیشنهادی انتشار<IranDateTimeInput name="scheduled_at" minDate={iranTodayIso()} required className={`${fieldClass} mt-1`}/></label>
          <button disabled={busy} className={primaryButton}>{busy ? "در حال ثبت…" : "ثبت برای بازبینی"}</button>
        </form>
      </Surface>
      <Surface className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-white/[0.06] p-4">
          <h2 className="text-sm font-bold text-white">فهرست محتوا</h2>
          <button onClick={() => void load()} className="text-xs text-violet-300">به‌روزرسانی</button>
        </div>
        {loading ? <div className="p-8 text-center text-xs text-slate-500">در حال دریافت…</div> : <div className="divide-y divide-white/[0.06]">
          {items.map(item => <article key={item.id} className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-bold text-white">{item.title}</div>
              <span className={`rounded-full px-2 py-1 text-[10px] ${item.status === "approved" ? "bg-emerald-500/10 text-emerald-300" : item.status === "rejected" ? "bg-rose-500/10 text-rose-300" : "bg-amber-500/10 text-amber-300"}`}>{statusName(item.status)}</span>
            </div>
            <div className="mt-2 text-[10px] text-slate-500">{channelName(item.channel)} · {formatIranDateTime(item.scheduled_at)}</div>
            <p className="mt-3 whitespace-pre-wrap text-xs leading-6 text-slate-300">{item.body}</p>
            {item.review_note && <p className="mt-2 text-[10px] text-slate-500">یادداشت بازبینی: {item.review_note}</p>}
            {canReview && item.status === "pending" && <div className="mt-3 flex gap-2"><button disabled={busy} onClick={() => void review(item.id, "approved")} className="rounded-lg bg-emerald-500/15 px-3 py-2 text-[10px] text-emerald-300">تأیید</button><button disabled={busy} onClick={() => void review(item.id, "rejected")} className="rounded-lg bg-rose-500/15 px-3 py-2 text-[10px] text-rose-300">رد</button></div>}
          </article>)}
          {!items.length && <div className="p-8 text-center text-xs text-slate-500">هنوز محتوایی ثبت نشده است.</div>}
        </div>}
      </Surface>
    </div>
    <div className="mt-6">
      <h2 className="mb-1 text-sm font-bold text-white">اتصال پلتفرم‌ها</h2>
      <p className="mb-4 text-xs text-slate-400">اعتبارنامهٔ هر کانال را ذخیره و تست کنید. مقدارهای ذخیره‌شده هرگز نمایش داده نمی‌شوند — فقط نام کلیدها و پیش‌نمایش پوشانده‌شده. انتشار خودکار هنوز فعال نیست.</p>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {(channelInfos.length ? channelInfos : channelsPlaceholder).map(info => (
          <ChannelCard key={info.platform} info={info} busy={busy} onSaved={setMessage} />
        ))}
      </div>
    </div>
  </PortalShell>;
}
