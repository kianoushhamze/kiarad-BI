"use client";
import { authFetch } from "../../lib/secure-api";

import React, { useState, useEffect, useRef } from "react";

export default function VoiceReportPage() {
  const [recording, setRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [parsed, setParsed] = useState(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [history, setHistory] = useState([]);
  
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => { loadHistory(); }, []);

  const loadHistory = () => {
    authFetch("/operations/daily-reports-recent")
      .then(r => r.json()).then(d => setHistory(Array.isArray(d) ? d : [])).catch(() => {});
  };

  const startRecord = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setAudioUrl(URL.createObjectURL(blob));
        sendAudioToWhisper(blob);
      };

      mediaRecorderRef.current.start();
      setRecording(true);
      setMsg("🎙️ در حال ضبط صدای شما... (پس از اتمام صحبت، دکمه قرمز را بزنید)");
    } catch {
      alert("دسترسی به میکروفون داده نشد.");
    }
  };

  const stopRecord = () => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
      setMsg("در حال ارسال صوت به هوش مصنوعی faster-whisper برای تبدیل دقیق گفتار به متن...");
    }
  };

  const sendAudioToWhisper = (blob) => {
    setLoading(true);
    const reader = new FileReader();
    reader.readAsDataURL(blob);
    reader.onloadend = async () => {
      const base64Audio = reader.result.split(",");
      try {
        const res = await authFetch("/operations/transcribe-audio", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audio_base64: base64Audio })
        });
        const data = await res.json();
        setParsed(data);
        setMsg("✓ صوت با هوش مصنوعی محلی با موفقیت پیاده‌سازی و استخراج شد.");
      } catch {
        setMsg("خطا در پردازش با سرور هوش مصنوعی.");
      }
      setLoading(false);
    };
  };

  const submitFinal = async () => {
    if (!parsed) return;
    setLoading(true);
    try {
      const res = await authFetch("/operations/submit-daily-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed)
      });
      const data = await res.json();
      if (res.ok) {
        setMsg(`✓ گزارش #${data.report_id} با موفقیت ثبت شد ${data.task_created ? 'و تسک پیگیری در کارتابل ایجاد گردید.' : '.'}`);
        setParsed(null);
        setAudioUrl(null);
        loadHistory();
      }
    } catch {
      setMsg("خطا در ثبت نهایی.");
    }
    setLoading(false);
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0F172A", padding: "24px", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      <div style={{ maxWidth: "860px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h1 style={{ fontSize: "22px", fontWeight: "bold", color: "#A855F7" }}>🎙️ ثبت صوتی گزارش با هوش مصنوعی faster-whisper</h1>
          <div style={{ display: "flex", gap: "10px" }}>
            <a href="/map" style={{ color: "#94A3B8", textDecoration: "none" }}>🗺️ نقشه</a>
            <a href="/proformas" style={{ color: "#94A3B8", textDecoration: "none" }}>📄 پیش‌فاکتور</a>
            <a href="/login" style={{ color: "#94A3B8", textDecoration: "none" }}>📊 داشبورد</a>
          </div>
        </div>

        <div style={{ background: "#1E293B", borderRadius: "14px", padding: "28px", border: "1px solid #334155", textAlign: "center", marginBottom: "20px" }}>
          <button
            onClick={recording ? stopRecord : startRecord}
            style={{
              width: "80px", height: "80px", borderRadius: "50%",
              background: recording ? "#EF4444" : "#7C3AED",
              color: "#FFF", fontSize: "32px", border: "none", cursor: "pointer",
              boxShadow: recording ? "0 0 24px #EF4444" : "0 4px 14px rgba(0,0,0,0.4)"
            }}
          >
            {recording ? "⏹" : "🎙"}
          </button>
          <div style={{ fontWeight: "bold", color: recording ? "#EF4444" : "#A855F7", marginTop: "14px", fontSize: "15px" }}>
            {recording ? "در حال ضبط... (صحبت کنید و برای اتمام دکمه را لمس کنید)" : "برای شروع ضبط صدا دکمه میکروفون را لمس کنید"}
          </div>

          {audioUrl && (
            <div style={{ marginTop: "16px" }}>
              <audio src={audioUrl} controls style={{ width: "100%", maxWidth: "420px" }} />
            </div>
          )}

          {msg && <div style={{ marginTop: "14px", color: "#FDE047", fontSize: "14px" }}>{msg}</div>}
        </div>

        {parsed && (
          <div style={{ background: "#1E293B", borderRadius: "14px", padding: "20px", border: "1px solid #7C3AED", marginBottom: "24px" }}>
            <h3 style={{ fontSize: "16px", color: "#A855F7", marginBottom: "14px" }}>✨ خروجی دقیق استخراج‌شده توسط هوش مصنوعی:</h3>
            
            <div style={{ background: "#0F172A", padding: "14px", borderRadius: "8px", marginBottom: "14px", borderRight: "4px solid #10B981" }}>
              <div style={{ fontSize: "13px", color: "#94A3B8" }}>متن تشخیص‌داده‌شده از ویس:</div>
              <div style={{ fontSize: "15px", color: "#FFF", marginTop: "4px", fontWeight: "bold" }}>{parsed.raw_text}</div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "14px" }}>
              <div style={{ background: "#0F172A", padding: "12px", borderRadius: "8px" }}>
                <span style={{ fontSize: "12px", color: "#94A3B8" }}>مرکز / مشتری شناسایی‌شده:</span>
                <div style={{ fontWeight: "bold", color: "#38BDF8", fontSize: "15px", marginTop: "4px" }}>{parsed.customer_name}</div>
              </div>
              <div style={{ background: "#0F172A", padding: "12px", borderRadius: "8px" }}>
                <span style={{ fontSize: "12px", color: "#94A3B8" }}>خلاصه اقدام انجام‌شده:</span>
                <div style={{ fontWeight: "bold", color: "#FFF", fontSize: "14px", marginTop: "4px" }}>{parsed.summary}</div>
              </div>
            </div>

            {parsed.followup_task && (
              <div style={{ background: "#0F172A", padding: "14px", borderRadius: "8px", marginBottom: "14px", borderRight: "4px solid #F59E0B" }}>
                <span style={{ fontSize: "12px", color: "#F59E0B", fontWeight: "bold" }}>📌 تسک پیگیری خودکار (در کارتابل ثبت می‌شود):</span>
                <div style={{ fontSize: "14px", color: "#FFF", marginTop: "4px" }}>{parsed.followup_task}</div>
              </div>
            )}

            <button onClick={submitFinal} disabled={loading} style={{ width: "100%", background: "#10B981", color: "#FFF", border: "none", borderRadius: "8px", padding: "12px", fontWeight: "bold", cursor: "pointer", fontSize: "15px" }}>
              {loading ? "در حال ذخیره‌سازی..." : "✓ تأیید و ثبت نهایی گزارش در سیستم"}
            </button>
          </div>
        )}

        {/* سوابق */}
        <div style={{ background: "#1E293B", borderRadius: "14px", padding: "20px", border: "1px solid #334155" }}>
          <h3 style={{ fontSize: "15px", color: "#CBD5E1", marginBottom: "12px" }}>گزارش‌های شبانه اخیر</h3>
          <table style={{ width: "100%", textAlign: "right", fontSize: "13px", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #475569", color: "#94A3B8" }}>
                <th style={{ padding: "8px" }}>ویزیتور</th>
                <th style={{ padding: "8px" }}>شرح و خلاصه ویس</th>
                <th style={{ padding: "8px" }}>تسک پیگیری</th>
              </tr>
            </thead>
            <tbody>
              {history.map(h => (
                <tr key={h.id} style={{ borderBottom: "1px solid #334155" }}>
                  <td style={{ padding: "8px" }}>{h.salesperson_name}</td>
                  <td style={{ padding: "8px" }}>{h.notes}</td>
                  <td style={{ padding: "8px", color: "#F59E0B" }}>{h.tomorrow_plan}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
