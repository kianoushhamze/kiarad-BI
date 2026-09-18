"use client";

import React, { useState, useEffect, useRef } from "react";

export function AssistantChat() {
  const [messages, setMessages] = useState<Array<{ sender: "user" | "ai"; text: string; elapsed?: number }>>([
    { sender: "ai", text: "سلام کیانوش عزیز! من مغز متفکر و دستیار هوشمند کیاراد BI هستم. می‌توانید هر کالا، داروخانه، فاکتور، تارگت، سناریوهای بازاریابی یا سوالات تحلیلی را از من بپرسید." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // تایمر ثانیه‌شمار زنده در زمان تفکر هوش مصنوعی
  useEffect(() => {
    let timer: any;
    if (loading) {
      setElapsedSeconds(0);
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => clearInterval(timer);
  }, [loading]);

  const [isFullScreen, setIsFullScreen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // بستن حالت تمام‌صفحه با دکمه Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isFullScreen) {
        setIsFullScreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullScreen]);

  const sendMessage = async (queryText?: string) => {
    const textToSend = (queryText || input).trim();
    if (!textToSend || loading) return;

    setMessages((prev) => [...prev, { sender: "user", text: textToSend }]);
    if (!queryText) setInput("");
    setLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/assistant/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: textToSend }),
      });
      if (res.ok) {
        const data = await res.json();
        const reply = data.reply || data.answer || "اطلاعات دریافت شد.";
        setMessages((prev) => [...prev, { sender: "ai", text: reply, elapsed: data.elapsed }]);
      } else {
        setMessages((prev) => [...prev, { sender: "ai", text: "خطا در دریافت پاسخ از سرور هوش مصنوعی." }]);
      }
    } catch {
      setMessages((prev) => [...prev, { sender: "ai", text: "عدم دسترسی به سرویس هوش مصنوعی." }]);
    } finally {
      setLoading(false);
    }
  };

  const quickQuestions = [
    "چه خبر ؟",
    "گزارش کلی وضعیت شرکت",
    "سناریوی ریلز برای درمالیست",
    "آمار پایگاه‌های کرمان"
  ];

  // استایل در حالت عادی یا تمام‌صفحه
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
      {/* هدر چت با دکمه تمام‌صفحه و عنوان */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "12px", marginBottom: "14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "16px" }}>🤖</span>
          <span style={{ fontWeight: "bold", fontSize: "14px", color: "#38BDF8" }}>
            دستیار هوشمند و مغز متفکر کیاراد BI
          </span>
          <span style={{ fontSize: "11px", background: "#065F46", color: "#6EE7B7", padding: "2px 8px", borderRadius: "10px" }}>
            ● مدل اولاما qwen2.5 (جامع)
          </span>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            type="button"
            onClick={() => setIsFullScreen(!isFullScreen)}
            style={{
              background: "#1E293B",
              border: "1px solid #334155",
              color: "#F8FAFC",
              padding: "6px 12px",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "12px",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px"
            }}
          >
            {isFullScreen ? (
              <>
                <span>🗗</span><span>خروج از تمام‌صفحه (Esc)</span>
              </>
            ) : (
              <>
                <span>⛶</span><span>بزرگ‌نمایی / تمام‌صفحه</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* ناحیه نمایش پیام‌ها (در حالت تمام‌صفحه کل صفحه را پر می‌کند) */}
      <div
        style={{
          flex: isFullScreen ? 1 : "unset",
          height: isFullScreen ? "unset" : "320px",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "14px",
          padding: "16px",
          background: "#090E1A",
          borderRadius: "10px",
          border: "1px solid #1E293B",
          marginBottom: "14px"
        }}
      >
        {messages.map((m, idx) => (
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
              lineHeight: "1.8",
              border: m.sender === "ai" ? "1px solid #1E293B" : "none",
              whiteSpace: "pre-wrap",
              userSelect: "text"
            }}
          >
                        {m.text}
            {m.sender === "ai" && m.elapsed !== undefined && m.elapsed > 0 && (
              <div style={{ marginTop: "8px", paddingTop: "6px", borderTop: "1px solid rgba(255,255,255,0.1)", fontSize: "11px", color: "#FBBF24", display: "flex", alignItems: "center", gap: "5px" }}>
                <span>⏱️ زمان تفکر و تولید پاسخ:</span>
                <strong>{m.elapsed} ثانیه</strong>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ alignSelf: "flex-end", background: "#131E3A", color: "#38BDF8", padding: "10px 18px", borderRadius: "10px", fontSize: "12px", display: "inline-flex", alignItems: "center", gap: "10px", border: "1px solid #1E293B" }}>
            <span>🧠 هوش مصنوعی در حال تفکر و تنظیم پاسخ...</span>
            <span style={{ background: "#0F172A", color: "#FBBF24", padding: "3px 8px", borderRadius: "6px", fontWeight: "bold", fontSize: "11px", border: "1px solid #334155" }}>
              ⏱️ {elapsedSeconds} ثانیه
            </span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* چیپ‌های سوالات آماده */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }}>
        {quickQuestions.map((q, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => sendMessage(q)}
            style={{ background: "#111C35", border: "1px solid #334155", color: "#94A3B8", padding: "5px 12px", borderRadius: "14px", fontSize: "11px", cursor: "pointer" }}
          >
            {q}
          </button>
        ))}
      </div>

      {/* اینپوت تایپ پیام */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage();
        }}
        style={{ display: "flex", gap: "10px" }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="هر سوالی، سناریوی ریلز، تحلیل فروش یا نکته جدیدی دارید بنویسید..."
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
