"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { secureApi } from "../lib/secure-api";

type Message = { id?: number; role: "user" | "assistant"; content: string; intent?: string | null; created_at?: string };
type HistoryResponse = { messages: Message[]; suggested_questions: string[]; mode: string };
type ChatResponse = { answer: string; intent: string; confidence: string; suggested_questions: string[] };

export function AssistantChat({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setError("");
    secureApi<HistoryResponse>("/assistant/chat", { method: "POST" })
      .then((result) => {
        if (!active) return;
        setMessages(result.messages);
        setSuggestions(result.suggested_questions);
      })
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "دریافت سابقه گفتگو ناموفق بود."));
    return () => { active = false; };
  }, [open]);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  async function send(question?: string) {
    const content = (question ?? input).trim();
    if (!content || loading) return;
    setInput("");
    setError("");
    setMessages((current) => [...current, { role: "user", content }]);
    setLoading(true);
    try {
      const result = await secureApi<ChatResponse>("/assistant/chat", {
        method: "POST",
        body: JSON.stringify({ message: content }),
      });
      setMessages((current) => [...current, { role: "assistant", content: result.answer, intent: result.intent }]);
      setSuggestions(result.suggested_questions);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "پاسخ دستیار دریافت نشد.");
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send();
  }

  async function clear() {
    try {
      await secureApi("/assistant/chat", { method: "DELETE" });
      setMessages([]);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "پاک‌کردن گفتگو ناموفق بود.");
    }
  }

  if (!open) return null;

  return <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/70 p-2 backdrop-blur-sm sm:items-center sm:p-4" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <section dir="rtl" className="flex h-[min(760px,92vh)] w-full max-w-2xl flex-col overflow-hidden rounded-[28px] border border-violet-400/20 bg-[#0b0d17] text-slate-200 shadow-[0_32px_120px_rgba(0,0,0,.8)]">
      <header className="flex items-center justify-between border-b border-white/[0.07] bg-white/[0.025] px-4 py-4 sm:px-5">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-700 text-xl text-white shadow-[0_0_32px_rgba(139,92,246,.4)]">✦</span>
          <div><h2 className="text-sm font-extrabold text-white">دستیار هوشمند کیاراد</h2><p className="mt-1 text-[9px] text-emerald-400">● تحلیل داخلی امن · بدون هزینه API</p></div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={clear} className="rounded-xl px-3 py-2 text-[10px] text-slate-500 hover:bg-white/5 hover:text-rose-300">پاک‌کردن</button>
          <button onClick={onClose} aria-label="بستن" className="grid h-9 w-9 place-items-center rounded-xl text-xl text-slate-500 hover:bg-white/5 hover:text-white">×</button>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-5">
        {!messages.length && <div className="mx-auto max-w-lg rounded-2xl border border-violet-400/10 bg-violet-500/[0.06] p-4 text-xs leading-7 text-slate-300">
          سلام! من داده‌های ثبت‌شده کیاراد را با توجه به سطح دسترسی شما تحلیل می‌کنم. می‌توانید درباره فروش، پیش‌بینی، تارگت، تسک‌ها، گزارش‌ها و امور مالی مجاز سؤال کنید.
          <div className="mt-2 text-[9px] text-slate-500">پاسخ‌ها تحلیلی هستند؛ هیچ اقدام عملیاتی بدون تأیید مدیر اجرا نمی‌شود.</div>
        </div>}
        {messages.map((message, index) => <div key={message.id ?? index} className={"flex " + (message.role === "user" ? "justify-start" : "justify-end")}>
          <div className={"max-w-[88%] rounded-2xl px-4 py-3 text-xs leading-7 " + (message.role === "user" ? "rounded-tr-md bg-violet-600 text-white" : "rounded-tl-md border border-white/[0.07] bg-white/[0.045] text-slate-200")}>
            {message.role === "assistant" && <div className="mb-1 text-[9px] font-bold text-violet-400">✦ تحلیل کیاراد</div>}
            <div className="whitespace-pre-wrap">{message.content}</div>
          </div>
        </div>)}
        {loading && <div className="flex justify-end"><div className="rounded-2xl rounded-tl-md border border-white/[0.07] bg-white/[0.045] px-4 py-3 text-xs text-slate-500"><span className="animate-pulse">در حال تحلیل داده‌ها…</span></div></div>}
        <div ref={endRef} />
      </div>

      <footer className="border-t border-white/[0.07] bg-[#090b14] p-3 sm:p-4">
        {error && <div className="mb-3 rounded-xl border border-rose-500/20 bg-rose-500/10 px-3 py-2 text-[10px] text-rose-300">{error}</div>}
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          {suggestions.map((question) => <button key={question} onClick={() => void send(question)} disabled={loading} className="shrink-0 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-[9px] text-slate-400 transition hover:border-violet-400/30 hover:text-white disabled:opacity-40">{question}</button>)}
        </div>
        <form onSubmit={submit} className="flex gap-2 rounded-2xl border border-white/[0.09] bg-black/25 p-2 focus-within:border-violet-400/35">
          <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); }
          }} rows={1} placeholder="سؤال خود را درباره کسب‌وکار بپرسید…" className="max-h-28 min-h-10 min-w-0 flex-1 resize-none bg-transparent px-3 py-2 text-xs text-white outline-none placeholder:text-slate-700" />
          <button disabled={loading || !input.trim()} className="self-end rounded-xl bg-violet-600 px-5 py-3 text-[10px] font-bold text-white hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-40">ارسال</button>
        </form>
      </footer>
    </section>
  </div>;
}


