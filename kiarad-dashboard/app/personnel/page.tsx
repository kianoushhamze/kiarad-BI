"use client";

import React, { useState } from "react";
import Link from "next/link";

export default function ManagerControlPage() {
  const [visitors, setVisitors] = useState([
    { id: 1, name: "امیرانی", username: "amirani", region: "سیرجان", status: "active" },
    { id: 2, name: "کریمی", username: "karimi", region: "جیرفت و کهنوج", status: "active" },
    { id: 3, name: "محمدی", username: "mohammadi", region: "رفسنجان و زرند", status: "active" },
    { id: 4, name: "نماینده علمی تست", username: "visitor1", region: "کرمان مرکزی", status: "active" },
  ]);

  const [newName, setNewName] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRegion, setNewRegion] = useState("کرمان مرکزی");
  const [msg, setMsg] = useState("");

  const handleAddVisitor = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName || !newUsername || !newPassword) return;

    setVisitors([...visitors, {
      id: visitors.length + 1,
      name: newName,
      username: newUsername.trim().toLowerCase(),
      region: newRegion,
      status: "active"
    }]);

    setMsg(`ویزیتور «${newName}» با موفقیت افزوده شد.`);
    setNewName("");
    setNewUsername("");
    setNewPassword("");
    setTimeout(() => setMsg(""), 4000);
  };

  return (
    <div dir="rtl" className="min-h-screen bg-[#0d0b18] text-white p-6 font-sans">
      <header className="flex justify-between items-center pb-6 border-b border-purple-900/40 mb-8">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-indigo-300 bg-clip-text text-transparent">
            مدیریت پرسنل و ویزیتورهای کیاراد بی‌آی
          </h1>
          <p className="text-xs text-gray-400 mt-1">تعریف دسترسی و مناطق ویزیت علمی و بازاریابی استان کرمان</p>
        </div>
        <Link href="/" className="px-4 py-2 bg-purple-950/60 border border-purple-800/40 text-purple-300 rounded-xl hover:bg-purple-900/50 text-xs transition">
          ← بازگشت به داشبورد اصلی
        </Link>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="bg-[#17142b] p-6 rounded-2xl border border-purple-900/30 h-fit">
          <h2 className="text-base font-semibold text-purple-200 mb-4">تعریف ویزیتور جدید</h2>
          {msg && <div className="mb-4 p-3 bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-emerald-300 text-xs text-center">{msg}</div>}
          <form onSubmit={handleAddVisitor} className="space-y-4">
            <div>
              <label className="block text-xs text-gray-300 mb-1">نام و نام خانوادگی</label>
              <input type="text" required value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="مثال: مهدی حسینی" className="w-full px-3 py-2.5 bg-[#0a0814] border border-purple-900/50 rounded-xl text-sm text-white" />
            </div>
            <div>
              <label className="block text-xs text-gray-300 mb-1">نام کاربری (جهت ورود)</label>
              <input type="text" required value={newUsername} onChange={(e) => setNewUsername(e.target.value)} placeholder="مثال: hosseini" className="w-full px-3 py-2.5 bg-[#0a0814] border border-purple-900/50 rounded-xl text-sm text-white" />
            </div>
            <div>
              <label className="block text-xs text-gray-300 mb-1">کلمه عبور</label>
              <input type="password" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="••••••••" className="w-full px-3 py-2.5 bg-[#0a0814] border border-purple-900/50 rounded-xl text-sm text-white" />
            </div>
            <div>
              <label className="block text-xs text-gray-300 mb-1">منطقه فعالیت</label>
              <select value={newRegion} onChange={(e) => setNewRegion(e.target.value)} className="w-full px-3 py-2.5 bg-[#0a0814] border border-purple-900/50 rounded-xl text-sm text-white">
                <option value="کرمان مرکزی">کرمان مرکزی</option>
                <option value="سیرجان">سیرجان</option>
                <option value="رفسنجان">رفسنجان</option>
                <option value="جیرفت و کهنوج">جیرفت و کهنوج</option>
                <option value="بم">بم</option>
                <option value="زرند و راور">زرند و راور</option>
              </select>
            </div>
            <button type="submit" className="w-full mt-2 py-3 bg-purple-600 hover:bg-purple-500 text-white font-medium rounded-xl text-sm transition">
              افزودن ویزیتور به سیستم
            </button>
          </form>
        </div>

        <div className="lg:col-span-2 bg-[#17142b] p-6 rounded-2xl border border-purple-900/30">
          <h2 className="text-base font-semibold text-purple-200 mb-4">ویزیتورهای فعال</h2>
          <table className="w-full text-right text-sm">
            <thead className="bg-[#0a0814] text-gray-400 border-b border-purple-900/30">
              <tr>
                <th className="p-3">نام ویزیتور</th>
                <th className="p-3">نام کاربری</th>
                <th className="p-3">منطقه</th>
                <th className="p-3">وضعیت</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-purple-900/20">
              {visitors.map((v) => (
                <tr key={v.id} className="hover:bg-purple-950/20">
                  <td className="p-3 font-medium">{v.name}</td>
                  <td className="p-3 text-purple-300 font-mono text-xs">{v.username}</td>
                  <td className="p-3 text-gray-300">{v.region}</td>
                  <td className="p-3"><span className="px-2.5 py-1 bg-emerald-950/60 border border-emerald-500/30 text-emerald-300 rounded-lg text-xs">فعال</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}