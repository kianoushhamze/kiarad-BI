"use client";
import { useCallback, useEffect, useRef, useState, type ReactElement } from "react";
import { AssistantActionReview } from "../../components/assistant-action-review";
import { PortalShell } from "../../components/portal-shell";
import { authFetch } from "../../lib/secure-api";

type Msg = { id?: number; role: "user" | "assistant"; content: string; created_at?: string; action?: { label: string; href: string } };
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: { results?: ArrayLike<ArrayLike<{ transcript?: string }>> }) => void) | null;
  start: () => void;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

const MANAGER_SUGGESTIONS = [
  "وضعیت کلی شرکت چطوره؟",
  "بدهکارترین مشتری‌ها کیان؟",
  "بهترین فروشنده‌های ۳۰ روز اخیر کیان؟",
  "ارزش انبار چقدره؟",
  "چه تسک‌هایی عقب‌افتاده داریم؟",
  "فروش ۷ روز اخیر چطور بوده؟",
  "چه کالاهایی زیر حد سفارش هستن؟",
  "مطالبات معوق رو چطور وصول کنم؟",
];

const STAFF_SUGGESTIONS = [
  "برای بهتر مذاکره کردن با مشتری چه تمرینی انجام بدهم؟",
  "قیمت و موجودی یک کالا را چطور پیدا کنم؟",
  "ماندهٔ حساب مشتری‌های مرتبط با من چقدر است؟",
  "پیش‌فاکتورهای من چه وضعیتی دارند؟",
  "چطور پیش‌فاکتور جدید ثبت کنم؟",
  "قرارداد و فیش حقوقی خودم را از کجا ببینم؟",
  "برای مسیر ویزیت امروز چه اطلاعاتی ثبت شده؟",
];

function renderMarkdown(text: string) {
  // Simple markdown-ish renderer for chat
  const lines = text.split("\n");
  const out: ReactElement[] = [];
  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      out.push(<div key={idx} style={{ height: "6px" }} />);
      return;
    }
    // Bold replacement: **text**
    const renderBold = (s: string): (string | ReactElement)[] => {
      const parts: (string | ReactElement)[] = [];
      const re = /\*\*(.+?)\*\*/g;
      let last = 0;
      let m: RegExpExecArray | null;
      let k = 0;
      while ((m = re.exec(s)) !== null) {
        if (m.index > last) parts.push(s.slice(last, m.index));
        parts.push(<b key={k++} style={{ color: "#e8eaf6" }}>{m[1]}</b>);
        last = m.index + m[0].length;
      }
      if (last < s.length) parts.push(s.slice(last));
      return parts;
    };
    if (/^\d+\.\s/.test(trimmed) || /^[-•]\s/.test(trimmed)) {
      out.push(<div key={idx} style={{ paddingRight: "12px", marginBottom: "3px" }}>{renderBold(trimmed)}</div>);
    } else if (trimmed.startsWith("#")) {
      out.push(<div key={idx} style={{ fontWeight: "bold", marginTop: "8px", color: "#a5b4fc" }}>{renderBold(trimmed.replace(/^#+\s/, ""))}</div>);
    } else {
      out.push(<div key={idx} style={{ marginBottom: "3px" }}>{renderBold(trimmed)}</div>);
    }
  });
  return out;
}

export default function AssistantPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [role, setRole] = useState("");
  const [listening, setListening] = useState(false);
  const [voiceReply, setVoiceReply] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  const scrollDown = () => {
    setTimeout(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, 60);
  };

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const r = await authFetch("/assistant/history?limit=50");
      if (r.ok) {
        const data = await r.json();
        const hist = Array.isArray(data.messages) ? data.messages : [];
        setMessages(hist.filter((message: unknown): message is Msg => {
          if (typeof message !== "object" || message === null) return false;
          const candidate = message as Partial<Msg>;
          return (candidate.role === "user" || candidate.role === "assistant") && typeof candidate.content === "string";
        }));
      }
    } catch {
      // ignore
    }
    setLoading(false);
    scrollDown();
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => { if (active) void loadHistory(); });
    authFetch("/auth/me").then(async (r) => {
      if (r.ok) {
        const data = await r.json();
        if (active) setRole(String(data.role || ""));
      }
    }).catch(() => {});
    return () => { active = false; };
  }, [loadHistory]);

  const isManager = role === "ceo" || role === "sales_manager";

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    setInput("");
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    scrollDown();
    setSending(true);
    try {
      const r = await authFetch("/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg }),
      });
      const data = await r.json();
      if (r.ok && data.answer) {
        setMessages((prev) => [...prev, { role: "assistant", content: data.answer, action: data.action }]);
        if (voiceReply && typeof window !== "undefined" && "speechSynthesis" in window) {
          window.speechSynthesis.cancel();
          const utterance = new SpeechSynthesisUtterance(String(data.answer).replace(/[*#•]/g, ""));
          utterance.lang = "fa-IR";
          const faVoice = window.speechSynthesis.getVoices().find(v => v.lang.toLowerCase().startsWith("fa"));
          if (faVoice) utterance.voice = faVoice;
          window.speechSynthesis.speak(utterance);
        }
      } else {
        const detail = typeof data.detail === "string" ? data.detail : "سرویس تحلیل آزاد پاسخ نداد. پرسش‌های فروش، بدهکاران، انبار و تسک‌های عقب‌افتاده را امتحان کنید.";
        setError(detail);
        setMessages((prev) => [...prev, { role: "assistant", content: detail }]);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "خطای شبکه");
      setMessages((prev) => [...prev, { role: "assistant", content: "خطای شبکه. اتصال اینترنت رو چک کن." }]);
    }
    setSending(false);
    scrollDown();
  };

  const startVoiceQuestion = () => {
    const w = window as Window & { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor };
    const Recognition = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Recognition) { setError("تشخیص گفتار در این مرورگر پشتیبانی نمی‌شود؛ مرورگر کروم یا اج را امتحان کنید."); return; }
    const recognition = new Recognition();
    recognition.lang = "fa-IR";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onstart = () => { setListening(true); setError(""); };
    recognition.onerror = () => { setListening(false); setError("صدای شما دریافت نشد یا دسترسی میکروفون داده نشد."); };
    recognition.onend = () => setListening(false);
    recognition.onresult = (event) => {
      const transcript = String(event.results?.[0]?.[0]?.transcript || "").trim();
      if (transcript) { setInput(transcript); void send(transcript); }
    };
    recognition.start();
  };

  const clearAll = async () => {
    if (!confirm("همه‌ی تاریخچه چت پاک شود؟")) return;
    try {
      await authFetch("/assistant/history", { method: "DELETE" });
      setMessages([]);
    } catch {}
  };

  return (
    <PortalShell title="دستیار هوشمند" eyebrow="تحلیل‌گر کسب‌وکار">
      <div className="kskin">
        <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
          {/* ===== CHAT PANEL ===== */}
          <div className="rounded-2xl border border-white/[0.07] bg-[#0f1222]">
            <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-indigo-700 text-sm font-black text-white">ک</span>
                <div>
                  <b className="block text-sm text-white">دستیار ارشد هوش تجاری کیاراد</b>
                  <small className="text-[10px] text-slate-500">تحلیل از گزارش‌های مجاز؛ نام فارسی یا لاتین؛ تارگت با پیش‌نویس و تأیید شما</small>
                </div>
              </div>
              <button
                onClick={clearAll}
                className="rounded-lg border border-rose-400/20 px-3 py-1.5 text-[10px] text-rose-300 hover:bg-rose-500/10"
              >
                🗑️ پاک کردن
              </button>
            </div>

            <div ref={logRef} className="h-[520px] overflow-y-auto px-5 py-4 text-[13px] leading-6">
              {loading ? (
                <div className="py-10 text-center text-xs text-slate-500">در حال بارگذاری...</div>
              ) : messages.length === 0 ? (
                <div className="py-10 text-center text-xs text-slate-500">
                  سلام! سؤال کاری یا آموزشی‌ات را بپرس؛ دربارهٔ داده‌های سامانه هم در محدودهٔ دسترسی‌ات پاسخ می‌دهم.
                  <br />
                  <span className="text-[10px] text-slate-600">یا از پیشنهادهای سمت چپ استفاده کن</span>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div key={i} className={`mb-4 flex ${m.role === "user" ? "justify-start" : "justify-end"}`}>
                    <div
                      className={
                        "max-w-[85%] rounded-2xl px-4 py-3 " +
                        (m.role === "user"
                          ? "bg-violet-600/20 text-violet-100 ring-1 ring-violet-400/20"
                          : "bg-white/[0.04] text-slate-200 ring-1 ring-white/[0.06]")
                      }
                    >
                      {m.role === "assistant" ? renderMarkdown(m.content) : m.content}
                      {m.role === "assistant" && m.action && /^\/(catalog|person-targets|compensation|assistant-actions|data-entry)(\?|$)/.test(m.action.href) ? <a href={m.action.href} className="mt-3 block text-sky-300 underline">{m.action.label}</a> : null}
                    </div>
                  </div>
                ))
              )}
              {sending && (
                <div className="mb-4 flex justify-end">
                  <div className="rounded-2xl bg-white/[0.04] px-4 py-3 text-slate-400">
                    <span className="inline-block animate-pulse">در حال تحلیل...</span>
                  </div>
                </div>
              )}
            </div>

            <div className="border-t border-white/[0.07] p-3">
              {error && <div className="mb-2 rounded-lg bg-rose-500/10 px-3 py-2 text-[10px] text-rose-300">{error}</div>}
              <div className="flex items-end gap-2">
                <button type="button" onClick={startVoiceQuestion} disabled={sending || listening} title="پرسش صوتی" className={(listening ? "bg-rose-600 " : "bg-white/[0.06] ") + "rounded-xl px-4 py-3 text-xs text-white disabled:opacity-40"}>{listening ? "در حال شنیدن…" : "🎙️"}</button>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder="مثلاً: چطور با اعتراض مشتری به قیمت برخورد کنم؟"
                  rows={1}
                  className="max-h-32 flex-1 resize-none rounded-xl border border-white/[0.08] bg-black/30 px-4 py-3 text-xs text-white outline-none placeholder:text-slate-600 focus:border-violet-400/40"
                />
                <button
                  onClick={() => send()}
                  disabled={sending || !input.trim()}
                  className="rounded-xl bg-gradient-to-br from-violet-500 to-indigo-700 px-5 py-3 text-xs font-bold text-white disabled:opacity-40"
                >
                  ارسال
                </button>
              </div>
              {(role === "ceo" || role === "sales_manager") && !sending && messages.at(-1)?.role === "assistant" && <AssistantActionReview key={messages.length} answer={messages.at(-1)!.content}/>}
              <label className="mt-2 flex items-center gap-2 text-[10px] text-slate-500"><input type="checkbox" checked={voiceReply} onChange={e => setVoiceReply(e.target.checked)} /> پاسخ دستیار با صدا خوانده شود</label>
            </div>
          </div>

          {/* ===== SUGGESTIONS PANEL ===== */}
          <div className="space-y-3">
            <div className="rounded-2xl border border-white/[0.07] bg-[#0f1222] p-4">
              <b className="mb-3 block text-xs text-violet-300">💡 پیشنهادهای سریع</b>
              <div className="space-y-2">
                {(isManager ? MANAGER_SUGGESTIONS : STAFF_SUGGESTIONS).map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    disabled={sending}
                    className="w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-right text-[10px] text-slate-300 hover:border-violet-400/30 hover:bg-violet-500/[0.06] hover:text-white disabled:opacity-40"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-white/[0.07] bg-[#0f1222] p-4 text-[10px] leading-5 text-slate-500">
              <b className="mb-2 block text-xs text-white">🎯 چی می‌تونم بپرسم؟</b>
              <div>💬 پرسش‌های آزاد و آموزش مهارت‌ها</div>
              <div>📦 قیمت و موجودی ثبت‌شدهٔ کالا</div>
              <div>🧾 حساب مشتری و پیش‌فاکتور مجاز</div>
              <div>☑ کارها و هدف‌های خودتان</div>
              {isManager && <div>📊 گزارش‌های مدیریتی مجاز</div>}
              {isManager && <div>🎯 پیش‌نویس تارگت و بازبینی در فرم</div>}
              <div>🗓 مسیر، پیگیری مشتری و گزارش روزانهٔ مجاز</div>
              <div className="mt-2 text-slate-600">نبود اطلاعات ثبت‌شده، به معنی صفر بودن آن نیست.</div>
            </div>
          </div>
        </div>
      </div>
    </PortalShell>
  );
}
