"use client";
import React, { useState, useEffect } from "react";

interface Message {
  id?: number;
  sender: string;
  role?: string;
  message?: string;
  content?: string;
  created_at?: string;
}

export default function TeamChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [sender, setSender] = useState("مدیریت");
  const [loading, setLoading] = useState(false);

  const fetchMessages = async () => {
    try {
      const res = await fetch("http://localhost:8000/chat/messages");
      if (res.ok) {
        const data = await res.json();
        setMessages(Array.isArray(data) ? data : data.messages || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchMessages();
    const interval = setInterval(fetchMessages, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/chat/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender, message: text, room: "general" }),
      });
      if (res.ok) {
        setText("");
        fetchMessages();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "900px", margin: "20px auto", padding: "20px", background: "#0F172A", borderRadius: "12px", color: "#fff", border: "1px solid #334155" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #334155", paddingBottom: "12px", marginBottom: "16px" }}>
        <h2 style={{ margin: 0, fontSize: "18px" }}>💬 اتاق چت تیمی و هماهنگی توزیع کیاراد</h2>
        <a href="/management" style={{ color: "#38BDF8", textDecoration: "none", fontSize: "14px" }}>← بازگشت به داشبورد</a>
      </div>
      
      <div style={{ height: "450px", overflowY: "auto", padding: "12px", background: "#1E293B", borderRadius: "8px", display: "flex", flexDirection: "column", gap: "10px" }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: "center", color: "#94A3B8", marginTop: "180px" }}>پیامی در این اتاق وجود ندارد. اولین پیام را ارسال کنید.</div>
        ) : (
          messages.map((m, idx) => (
            <div key={idx} style={{ alignSelf: m.sender === sender ? "flex-end" : "flex-start", background: m.sender === sender ? "#2563EB" : "#334155", padding: "8px 14px", borderRadius: "8px", maxWidth: "75%" }}>
              <div style={{ fontSize: "11px", color: "#CBD5E1", marginBottom: "4px" }}>{m.sender}</div>
              <div style={{ fontSize: "14px" }}>{m.message || m.content}</div>
            </div>
          ))
        )}
      </div>

      <form onSubmit={handleSend} style={{ display: "flex", gap: "10px", marginTop: "14px" }}>
        <select value={sender} onChange={(e) => setSender(e.target.value)} style={{ background: "#1E293B", color: "#fff", border: "1px solid #475569", borderRadius: "6px", padding: "8px 12px" }}>
          <option value="مدیریت">مدیریت (کیانوش)</option>
          <option value="فروشنده تست">فروشنده تست</option>
          <option value="حسابداری">حسابداری</option>
          <option value="انباردار">انباردار</option>
        </select>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="پیام یا گزارش خود را بنویسید..."
          style={{ flex: 1, background: "#1E293B", color: "#fff", border: "1px solid #475569", borderRadius: "6px", padding: "8px 14px", outline: "none" }}
        />
        <button type="submit" disabled={loading} style={{ background: "#10B981", color: "#fff", border: "none", padding: "8px 20px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold" }}>
          ارسال
        </button>
      </form>
    </div>
  );
}
