
"use client";

import React, { useState, useEffect, useRef } from "react";
import { secureApi } from "../lib/secure-api";

type Msg = {
  sender: "user" | "ai";
  text: string;
  elapsed?: number;
};

type HistoryItem = {
  role: string;
  content: string;
};

type HistoryReply = {
  messages?: Array<HistoryItem>;
  mode?: string;
};

type ChatReply = {
  answer?: string;
  mode?: string;
};

const QUICK_QUESTIONS = new Array(
  "گزارش کلی وضعیت شرکت",
  "تحلیل فروش ماه و پیشنهاد عملی",
  "وضعیت نقدینگی و چک‌های در جریان",
  "برنامه محتوای اینستاگرام این هفته"
);

function makeWelcome(): Array<Msg> {
  const out: Array<Msg> = new Array();
  out.push({
    sender: "ai",
    text: "سلام کیانوش! من دستیار ارشد هوش تجاری کیاراد هستم و به داده‌های زنده‌ی شرکت وصل‌ام. هر سوالی داری بپرس: از تحلیل فروش و نقدینگی تا سناریوی ریلز و برنامه‌ریزی تیم."
  });
  return out;
}

export function AssistantChat() {
  const [messages, setMessages] = useState<Array<Msg>>(makeWelcome());
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const [mode, setMode] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(
    function () {
      let timer: any;
      if (loading) {
        setElapsedSeconds(0);
        timer = setInterval(function () {
          setElapsedSeconds(function (prev: number) {
            return prev + 1;
          });
        }, 1000);
      } else {
        setElapsedSeconds(0);
      }
      return function () {
        clearInterval(timer);
      };
    },
    new Array(loading)
  );

  const scrollToBottom = function () {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(function () {
    scrollToBottom();
  }, new Array(messages, loading));

  useEffect(
    function () {
      const handleKeyDown = function (e: KeyboardEvent) {
        if (e.key === "Escape" && isFullScreen) {
          setIsFullScreen(false);
        }
      };
      window.addEventListener("keydown", handleKeyDown);
      return function () {
        window.removeEventListener("keydown", handleKeyDown);
      };
    },
    new Array(isFullScreen)
  );

  useEffect(function () {
    const run = async function () {
      try {
        const data = (await secureApi("/assistant/history?limit=30", {
          method: "GET"
        })) as HistoryReply;
        if (data.messages && data.messages.length > 0) {
          const loaded: Array<Msg> = new Array();
          data.messages.forEach(function (m: HistoryItem) {
            loaded.push({
              sender: m.role === "assistant" ? "ai" : "user",
              text: m.content
            });
          });
          setMessages(function (prev) {
            const head = prev.slice(0, 1);
            return head.concat(loaded);
          });
        }
        if (data.mode) setMode(data.mode);
      } catch {
        // بدون لاگین یا سرور خاموش - سکوت
      }
    };
    run();
  }, new Array());

  const sendMessage = async function (queryText?: string) {
    const textToSend = (queryText || input).trim();
    if (!textToSend || loading) return;
    const userMsg: Msg = { sender: "user", text: textToSend };
    setMessages(function (prev) {
      const next = prev.slice();
      next.push(userMsg);
      return next;
    });
    if (!queryText) setInput("");
    setLoading(true);
    const started = Date.now();
    try {
      const data = (await secureApi("/assistant/chat", {
        method: "POST",
        body: JSON.stringify({ message: textToSend })
      })) as ChatReply;
      const elapsed = Math.round((Date.now() - started) / 1000);
      const aiMsg: Msg = {
        sender: "ai",
        text: data.answer || "پاسخی دریافت نشد.",
        elapsed: elapsed
      };
      setMessages(function (prev) {
        const next = prev.slice();
        next.push(aiMsg);
        return next;
      });
      if (data.mode) setMode(data.mode);
    } catch (err: any) {
      let detail = err && err.message ? String(err.message) : "خطای ناشناخته";
      if (detail.indexOf("Authentication") !== -1) {
        detail = "ابتدا از صفحه ورود وارد سیستم شوید.";
      }
      const errMsg: Msg = { sender: "ai", text: "⚠️ " + detail };
      setMessages(function (prev) {
        const next = prev.slice();
        next.push(errMsg);
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  const containerStyle: React.CSSProperties = isFullScreen
    ? {
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 99999,
        background: "rgba(9, 14, 26, 0.98)",
        backdropFilter: "blur(12px)",
        padding: "24px 40px",
        display: "flex",
        flexDirection: "column",
        direction: "rtl",
        fontFamily: "tahoma, sans-serif"
      }
    : {
        background: "#0D1527",
        border: "1px solid #1E293B",
        borderRadius: "12px",
        padding: "18px",
        direction: "rtl",
        fontFamily: "tahoma, sans-serif",
        position: "relative",
        zIndex: 10
      };

  return (
    <div style={containerStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "12px", marginBottom: "14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "16px" }}>🤖</span>
          <span style={{ fontWeight: "bold", fontSize: "14px", color: "#38BDF8" }}>
            دستیار ارشد هوش تجاری کیاراد
          </span>
          <span style={{ fontSize: "11px", background: "#065F46", color: "#6EE7B7", padding: "2px 8px", borderRadius: "10px" }}>
            {mode === "gpt_free_v2" ? "● GPT زنده + داده‌های BI" : "● آماده"}
          </span>
        </div>
        <button
          type="button"
          onClick={function () { setIsFullScreen(!isFullScreen); }}
          style={{ background: "#1E293B", border: "1px solid #334155", color: "#F8FAFC", padding: "6px 12px", borderRadius: "6px", cursor: "pointer", fontSize: "12px" }}
        >
          {isFullScreen ? "خروج (Esc)" : "تمام‌صفحه"}
        </button>
      </div>

      <div style={{ flex: isFullScreen ? 1 : "unset", height: isFullScreen ? "unset" : "320px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "14px", padding: "16px", background: "#090E1A", borderRadius: "10px", border: "1px solid #1E293B", marginBottom: "14px" }}>
        {messages.map(function (m, idx) {
          return (
            <div
              key={idx}
              style={{
                alignSelf: m.sender === "user" ? "flex-start" : "flex-end",
                background: m.sender === "user" ? "#2563EB" : "#131E3A",
                color: "#F8FAFC",
                padding: "12px 18px",
                borderRadius: "12px",
                maxWidth: isFullScreen ? "75%" : "85%",
                fontSize: "13.5px",
                lineHeight: 1.8,
                border: m.sender === "ai" ? "1px solid #1E293B" : "none",
                whiteSpace: "pre-wrap",
                userSelect: "text"
              }}
            >
              {m.text}
              {m.sender === "ai" && m.elapsed && m.elapsed > 0 ? (
                <div style={{ marginTop: "8px", paddingTop: "6px", borderTop: "1px solid rgba(255,255,255,0.1)", fontSize: "11px", color: "#FBBF24" }}>
                  ⏱ زمان پاسخ: {m.elapsed} ثانیه
                </div>
              ) : null}
            </div>
          );
        })}
        {loading ? (
          <div style={{ alignSelf: "flex-end", background: "#131E3A", color: "#38BDF8", padding: "10px 18px", borderRadius: "10px", fontSize: "12px" }}>
            🧠 در حال فکر کردن... {elapsedSeconds} ثانیه
          </div>
        ) : null}
        <div ref={messagesEndRef} />
      </div>

      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }}>
        {QUICK_QUESTIONS.map(function (q, idx) {
          return (
            <button
              key={idx}
              type="button"
              onClick={function () { sendMessage(q); }}
              style={{ background: "#111C35", border: "1px solid #334155", color: "#94A3B8", padding: "5px 12px", borderRadius: "14px", fontSize: "11px", cursor: "pointer" }}
            >
              {q}
            </button>
          );
        })}
      </div>

      <form
        onSubmit={function (e) { e.preventDefault(); sendMessage(); }}
        style={{ display: "flex", gap: "10px" }}
      >
        <input
          type="text"
          value={input}
          onChange={function (e) { setInput(e.target.value); }}
          placeholder="هر سوالی داری بنویس: تحلیل فروش، نقدینگی، سناریو، برنامه‌ریزی..."
          style={{ flex: 1, background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "12px 16px", borderRadius: "8px", fontSize: "13px", outline: "none" }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{ background: "#10B981", color: "#fff", border: "none", padding: "12px 28px", borderRadius: "8px", cursor: "pointer", fontWeight: "bold", fontSize: "13px" }}
        >
          ارسال
        </button>
      </form>
    </div>
  );
}
