"use client";

import Image from "next/image";
import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { authFetch, secureApi, getSavedUser } from "../../lib/secure-api";
import { PortalShell } from "../../components/portal-shell";

type Message = {
  id: number;
  sender: string;
  message: string;
  created_at?: string;
  attachment_name?: string | null;
  attachment_type?: string | null;
};

function ChatAttachment({ message }: { message: Message }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let alive = true;
    let objectUrl = "";
    authFetch("/chat/attachments/" + message.id).then(async (response) => {
      if (!response.ok) throw new Error("دریافت فایل ناموفق بود");
      objectUrl = URL.createObjectURL(await response.blob());
      if (alive) setUrl(objectUrl);
      else URL.revokeObjectURL(objectUrl);
    }).catch(() => {});
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [message.id]);

  if (!url) return <div style={{ color: "#c4b5fd", fontSize: 12, marginTop: 8 }}>در حال دریافت پیوست…</div>;
  if (message.attachment_type?.startsWith("image/")) {
    return <a href={url} download={message.attachment_name || "image"} style={{ display: "block", marginTop: 8 }}>
      <Image src={url} alt={message.attachment_name || "تصویر پیوست‌شده"} width={300} height={220} unoptimized style={{ maxWidth: 300, maxHeight: 220, width: "auto", height: "auto", objectFit: "contain", borderRadius: 8 }} />
    </a>;
  }
  return <a href={url} download={message.attachment_name || "file"} style={{ display: "inline-block", marginTop: 8, color: "#ddd6fe", textDecoration: "underline" }}>
    📎 {message.attachment_name || "دریافت فایل"}
  </a>;
}

export default function TeamChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState("");
  const me = getSavedUser();
  const myName = me?.full_name || "کاربر";
  const isFieldUser = me?.role === "salesperson" || me?.role === "visitor";
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  const fetchMessages = useCallback(async () => {
    try {
      const data = await secureApi<Message[]>("/chat/messages?room=general", { method: "GET" });
      setMessages(Array.isArray(data) ? data : []);
      setError("");
    } catch (err: unknown) {
      setMessages([]);
      const message = err instanceof Error ? err.message : "خطای ناشناخته";
      setError(message.includes("Authentication") ? "ابتدا وارد سامانه شوید." : "دریافت پیام‌ها ناموفق بود: " + message);
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    let interval = 0;
    void Promise.resolve().then(() => {
      if (!active) return;
      void fetchMessages();
      interval = window.setInterval(() => { if (active) void fetchMessages(); }, 5000);
    });
    return () => { active = false; if (interval) window.clearInterval(interval); };
  }, [fetchMessages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if ((!text.trim() && !file) || loading) return;
    setLoading(true);
    try {
      const body = new FormData();
      body.set("message", text.trim());
      body.set("room", "general");
      if (file) body.set("file", file);
      await secureApi("/chat/send", { method: "POST", body });
      setText("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      if (cameraRef.current) cameraRef.current.value = "";
      await fetchMessages();
    } catch (err: unknown) {
      setError("ارسال ناموفق بود: " + (err instanceof Error ? err.message : "خطای ناشناخته"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <PortalShell title="چت تیمی کیاراد" eyebrow="گفت‌وگوی مشترک کارکنان و ویزیتورها" actions={
      <Link href={isFieldUser ? "/newdash_online.html" : "/management"} className="rounded-lg border border-violet-800/70 bg-violet-950/60 px-3.5 py-2 text-xs font-bold text-violet-200">بازگشت به داشبورد</Link>
    }>
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: 16, color: "#f0f3ff", direction: "rtl" }}>

      {error ? <div role="alert" style={{ background: "#351321", border: "1px solid #7f1d3c", color: "#fda4af", padding: 12, borderRadius: 10, marginBottom: 12, fontSize: 13 }}>
        {error} <button type="button" onClick={() => void fetchMessages()} style={{ marginRight: 8, background: "transparent", color: "inherit", border: "1px solid currentColor", padding: "4px 10px", borderRadius: 6, cursor: "pointer" }}>تلاش دوباره</button>
      </div> : null}

      <div aria-live="polite" style={{ height: 460, overflowY: "auto", padding: 14, background: "#14131b", borderRadius: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        {fetching ? <div style={{ textAlign: "center", color: "#94a3b8", marginTop: 180 }}>در حال دریافت پیام‌ها…</div> : null}
        {!fetching && messages.length === 0 && !error ? <div style={{ textAlign: "center", color: "#94a3b8", marginTop: 180 }}>هنوز پیامی نیست؛ گفت‌وگو را شروع کنید.</div> : null}
        {messages.map((message) => {
          const mine = message.sender === myName;
          return <article key={message.id} style={{ alignSelf: mine ? "flex-end" : "flex-start", background: mine ? "#34205a" : "#262431", border: "1px solid #393548", padding: "9px 14px", borderRadius: 12, maxWidth: "78%", overflowWrap: "anywhere" }}>
            <div style={{ fontSize: 11, color: "#c4b5fd", marginBottom: 4 }}>{message.sender}{message.created_at ? " • " + String(message.created_at).slice(11, 16) : ""}</div>
            {message.message ? <div style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{message.message}</div> : null}
            {message.attachment_name ? <ChatAttachment message={message} /> : null}
          </article>;
        })}
        <div ref={endRef} />
      </div>

      <form onSubmit={send} style={{ display: "flex", gap: 9, marginTop: 14, alignItems: "center", flexWrap: "wrap" }}>
        <input type="text" value={text} maxLength={4000} onChange={(event) => setText(event.target.value)} placeholder="پیام خود را بنویسید…" style={{ flex: "1 1 300px", background: "#17161f", color: "#fff", border: "1px solid #393548", borderRadius: 9, padding: "11px 14px", outline: "none" }} />
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.docx,.xlsx,.csv,.txt" hidden onChange={(event) => setFile(event.target.files?.[0] || null)} />
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={(event) => setFile(event.target.files?.[0] || null)} />
        <button type="button" title="گرفتن عکس با دوربین" aria-label="گرفتن عکس با دوربین" onClick={() => cameraRef.current?.click()} style={{ background: "#201a30", color: "#c4b5fd", border: "1px solid #493080", padding: "10px 13px", borderRadius: 9, cursor: "pointer", fontSize: 16, lineHeight: 1 }}>📷</button>
        <button type="button" onClick={() => fileRef.current?.click()} style={{ background: "#201a30", color: "#c4b5fd", border: "1px solid #493080", padding: "10px 13px", borderRadius: 9, cursor: "pointer" }}>پیوست عکس یا فایل</button>
        <button type="submit" disabled={loading || (!text.trim() && !file)} style={{ background: loading ? "#42305d" : "#752cf2", color: "#fff", border: 0, padding: "10px 20px", borderRadius: 9, cursor: "pointer", fontWeight: 700 }}>{loading ? "در حال ارسال…" : "ارسال"}</button>
        {file ? <span style={{ flexBasis: "100%", color: "#c4b5fd", fontSize: 12 }}>پیوست: {file.name} ({(file.size / 1024 / 1024).toFixed(1)} مگابایت) <button type="button" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ""; if (cameraRef.current) cameraRef.current.value = ""; }} style={{ color: "#fda4af", background: "transparent", border: 0, cursor: "pointer" }}>حذف</button></span> : null}
      </form>
      <div style={{ color: "#64748b", fontSize: 11, marginTop: 8 }}>تصویر، پی‌دی‌اف، ورد، اکسل، سی‌اس‌وی و متن؛ حداکثر ۱۰ مگابایت برای هر فایل.</div>
    </div>
    </PortalShell>
  );
}
