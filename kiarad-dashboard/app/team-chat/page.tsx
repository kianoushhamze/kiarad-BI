
"use client";
import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { secureApi, getSavedUser } from "../../lib/secure-api";

type Message = {
  id?: number; sender?: string; message?: string; created_at?: string;
};

export default function TeamChatPage() {
  const listInit: Array<Message> = new Array();
  const emptyList: Array<Message> = new Array();
  const [messages, setMessages] = useState<Array<Message>>(listInit);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState("");
  const me = getSavedUser();
  const myName = me && me.full_name ? me.full_name : "کاربر";
  const endRef = useRef<HTMLDivElement>(null);
  const setEmpty = function () { setMessages(emptyList); };

  const fetchMessages = useCallback(async function () {
    try {
      const data = (await secureApi("/chat/messages?room=general", { method: "GET" })) as any;
      const fresh: Array<Message> = new Array();
      const raw = Array.isArray(data) ? data : data && data.messages;
      if (raw) raw.forEach(function (m: Message) { fresh.push(m); });
      setMessages(fresh);
      setError("");
    } catch (err: any) {
      const msg = err && err.message ? String(err.message) : "خطای ناشناخته";
      setEmpty();
      setError(msg.indexOf("Authentication") !== -1
        ? "ابتدا از صفحه ورود وارد سیستم شوید."
        : "دریافت پیام‌ها ناموفق بود: " + msg);
    } finally { setFetching(false); }
  }, new Array());

  useEffect(function () {
    fetchMessages();
    const interval = setInterval(fetchMessages, 3000);
    return function () { clearInterval(interval); };
  }, new Array(fetchMessages));

  useEffect(function () {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, new Array(messages));

  const send = async function (e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    setLoading(true);
    try {
      await secureApi("/chat/send", {
        method: "POST",
        body: JSON.stringify({ sender: myName, message: text, room: "general" })
      });
      setText("");
      await fetchMessages();
    } catch (err: any) {
      const msg = err && err.message ? String(err.message) : "خطای ناشناخته";
      setError("ارسال ناموفق بود: " + msg);
    } finally { setLoading(false); }
  };

  return (
    <div style={{ maxWidth: "900px", margin: "20px auto", padding: "20px", background: "#0F172A", borderRadius: "12px", color: "#fff", border: "1px solid #334155", direction: "rtl", fontFamily: "tahoma, sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #334155", paddingBottom: "12px", marginBottom: "16px" }}>
        <h2 style={{ margin: 0, fontSize: "18px" }}>💬 اتاق چت تیمی کیاراد</h2>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <span style={{ fontSize: "12px", color: "#94A3B8" }}>به‌عنوان: <strong style={{ color: "#38BDF8" }}>{myName}</strong></span>
          <Link href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "6px 14px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold" }}>← داشبورد اصلی</Link>
        </div>
      </div>

      {error ? (
        <div style={{ background: "#450A0A", border: "1px solid #7F1D1D", color: "#FCA5A5", padding: "12px 16px", borderRadius: "10px", marginBottom: "14px", fontSize: "13px" }}>
          ⚠️ {error} <button type="button" onClick={function(){fetchMessages();}} style={{ marginRight: "8px", background: "#7F1D1D", color: "#FCA5A5", border: "none", padding: "3px 12px", borderRadius: "6px", cursor: "pointer" }}>تلاش مجدد</button>
        </div>
      ) : null}

      <div style={{ height: "450px", overflowY: "auto", padding: "12px", background: "#1E293B", borderRadius: "8px", display: "flex", flexDirection: "column", gap: "10px" }}>
        {fetching ? <div style={{ textAlign: "center", color: "#94A3B8", marginTop: "180px" }}>در حال دریافت پیام‌ها...</div> : null}
        {!fetching && messages.length === 0 && !error ? (
          <div style={{ textAlign: "center", color: "#94A3B8", marginTop: "180px" }}>هنوز پیامی در این اتاق نیست — اولین پیام را بفرست.</div>
        ) : null}
        {messages.map(function (m, idx) {
          const mine = m.sender === myName;
          return (
            <div key={idx} style={{ alignSelf: mine ? "flex-end" : "flex-start", background: mine ? "#2563EB" : "#334155", padding: "8px 14px", borderRadius: "8px", maxWidth: "75%" }}>
              <div style={{ fontSize: "11px", color: "#CBD5E1", marginBottom: "4px" }}>{m.sender}{m.created_at ? " • " + String(m.created_at).slice(11, 16) : ""}</div>
              <div style={{ fontSize: "14px" }}>{m.message}</div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      <form onSubmit={send} style={{ display: "flex", gap: "10px", marginTop: "14px" }}>
        <input type="text" value={text} onChange={function(e){setText(e.target.value);}}
          placeholder="پیام خود را بنویسید..."
          style={{ flex: 1, background: "#1E293B", color: "#fff", border: "1px solid #475569", borderRadius: "6px", padding: "8px 14px", outline: "none" }} />
        <button type="submit" disabled={loading}
          style={{ background: loading ? "#065F46" : "#10B981", color: "#fff", border: "none", padding: "8px 20px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold" }}>
          {loading ? "..." : "ارسال"}
        </button>
      </form>
    </div>
  );
}
