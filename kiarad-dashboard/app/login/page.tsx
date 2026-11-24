"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { saveSession } from "../../lib/secure-api";
import { API_URL } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        throw new Error("نام کاربری یا کلمه عبور اشتباه است.");
      }

      const data = await res.json();
      saveSession(data.access_token, data.user);

      if (data.user?.role === "salesperson" || data.user?.role === "visitor") {
        router.push("/my-plan");
      } else if (data.user?.role === "finance") {
        router.push("/treasury");
      } else {
        router.push("/management");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "خطا در اتصال به سرور");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div dir="rtl" className="min-h-screen flex items-center justify-center bg-[#0d0b18] text-white p-4 font-sans">
      <div className="w-full max-w-md bg-[#17142b] border border-purple-900/40 rounded-2xl p-8 shadow-2xl">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-indigo-300 bg-clip-text text-transparent">
            شرکت پخش کیاراد شفا اندیش
          </h1>
          <p className="text-gray-400 text-sm mt-2">سامانه یکپارچه هوش تجاری و عملیات ویزیت</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-950/60 border border-red-500/50 rounded-xl text-red-300 text-sm text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs text-gray-300 mb-2 font-medium">نام کاربری</label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="مثال: kianoush یا visitor1"
              className="w-full px-4 py-3 bg-[#0a0814] border border-purple-900/50 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 transition"
            />
          </div>

          <div>
            <label className="block text-xs text-gray-300 mb-2 font-medium">کلمه عبور</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-4 py-3 pl-12 bg-[#0a0814] border border-purple-900/50 rounded-xl text-white placeholder-gray-600 focus:outline-none focus:border-purple-500 transition"
              />
              <button
                type="button"
                onClick={() => setShowPassword((visible) => !visible)}
                aria-label={showPassword ? "پنهان کردن کلمه عبور" : "نمایش کلمه عبور"}
                aria-pressed={showPassword}
                className="absolute inset-y-0 left-0 flex w-12 items-center justify-center text-gray-400 transition hover:text-purple-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-purple-500"
              >
                {showPassword ? (
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 3l18 18" />
                    <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                    <path d="M9.9 4.2A10.8 10.8 0 0 1 12 4c5.2 0 9 4.7 9 8a7.7 7.7 0 0 1-1.2 3.3" />
                    <path d="M6.6 6.6C4.3 8 3 10.3 3 12c0 3.3 3.8 8 9 8a10.7 10.7 0 0 0 4.1-.8" />
                  </svg>
                ) : (
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12c0-3.3 3.8-8 9-8s9 4.7 9 8-3.8 8-9 8-9-4.7-9-8Z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-semibold rounded-xl shadow-lg shadow-purple-900/30 transition duration-200 disabled:opacity-50"
          >
            {loading ? "در حال اعتبارسنجی..." : "ورود به سامانه"}
          </button>
        </form>
      </div>
    </div>
  );
}
