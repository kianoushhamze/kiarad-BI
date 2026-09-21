"use client";
import React, { useState } from "react";

export default function ShiftTracker({ salespersonId }: { salespersonId: number }) {
  const [isActive, setIsActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState("شیفت کاری خاموش است");

  const toggleShift = () => {
    if (!navigator.geolocation) {
      alert("مرورگر از GPS پشتیبانی نمی کند.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const endpoint = isActive ? "/api/compensation/attendance/stop" : "/api/compensation/attendance/start";
        try {
          const res = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              salesperson_id: salespersonId,
              lat: pos.coords.latitude,
              lng: pos.coords.longitude,
            }),
          });
          if (res.ok) {
            setIsActive(!isActive);
            setStatusText(isActive ? "شیفت خاتمه یافت و ساعات کارکرد ذخیره شد." : "شیفت فعال شد و موقعیت ثبت گردید.");
          }
        } catch (err) {
          alert("خطا در ارتباط با سرور");
        } finally {
          setLoading(false);
        }
      },
      () => {
        alert("دسترسی به موقعیت مکانی داده نشد.");
        setLoading(false);
      }
    );
  };

  return (
    <div className="bg-slate-900 border border-purple-900/50 p-4 rounded-xl flex items-center justify-between">
      <div>
        <h4 className="font-bold text-white text-sm">وضعیت کاری و موقعیت مکانی (GPS)</h4>
        <p className="text-xs text-slate-400 mt-1">{statusText}</p>
      </div>
      <button
        onClick={toggleShift}
        disabled={loading}
        className={`px-4 py-2 rounded-lg font-bold text-sm transition-all ${
          isActive ? "bg-rose-600 text-white" : "bg-emerald-600 text-white"
        }`}
      >
        {loading ? "در حال ثبت..." : isActive ? "پایان شیفت کاری" : "روشن کردن لوکیشن و شروع کار"}
      </button>
    </div>
  );
}
