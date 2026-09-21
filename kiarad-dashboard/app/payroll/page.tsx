"use client";

import React, { useState } from "react";
import Link from "next/link";

export default function PayrollPage() {
  const [selectedVisitor, setSelectedVisitor] = useState<any>(null);

  const [payrollList] = useState([
    {
      id: 1,
      name: "امیرانی",
      region: "سیرجان",
      baseSalary: 12000000,
      grossSales: 65000000,
      returns: 2000000,
      netSales: 63000000,
      target: 50000000,
      achievement: 126,
      rate: 4.5,
      commission: 2835000,
      collectionBonus: 1200000,
      focusBonus: 800000,
      deductions: 1500000,
      netPay: 15335000,
    },
    {
      id: 2,
      name: "کریمی",
      region: "جیرفت و کهنوج",
      baseSalary: 12000000,
      grossSales: 48000000,
      returns: 3000000,
      netSales: 45000000,
      target: 45000000,
      achievement: 100,
      rate: 3.5,
      commission: 1575000,
      collectionBonus: 600000,
      focusBonus: 500000,
      deductions: 1200000,
      netPay: 13475000,
    },
    {
      id: 3,
      name: "محمدی",
      region: "رفسنجان و زرند",
      baseSalary: 12000000,
      grossSales: 59000000,
      returns: 1500000,
      netSales: 57500000,
      target: 50000000,
      achievement: 115,
      rate: 4.0,
      commission: 2300000,
      collectionBonus: 900000,
      focusBonus: 700000,
      deductions: 1400000,
      netPay: 14500000,
    },
    {
      id: 4,
      name: "رضا کرمانی",
      region: "کرمان مرکزی",
      baseSalary: 12000000,
      grossSales: 35000000,
      returns: 1000000,
      netSales: 34000000,
      target: 50000000,
      achievement: 68,
      rate: 2.5,
      commission: 850000,
      collectionBonus: 0,
      focusBonus: 200000,
      deductions: 1200000,
      netPay: 11850000,
    },
  ]);

  const totalPayroll = payrollList.reduce((sum, v) => sum + v.netPay, 0);
  const totalCommission = payrollList.reduce((sum, v) => sum + v.commission + v.collectionBonus + v.focusBonus, 0);

  return (
    <div dir="rtl" className="min-h-screen bg-[#0d0b18] text-white p-6 font-sans">
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-purple-900/40 mb-8 gap-4">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-purple-400 to-indigo-300 bg-clip-text text-transparent">
            سیستم حقوق، دستمزد و پورسانت ویزیتورها (کیاراد بی‌آی)
          </h1>
          <p className="text-xs text-gray-400 mt-1">محاسبه خودکار کارکرد، فروش خالص، پورسانت پلکانی و پاداش شلف</p>
        </div>
        <Link href="/management" className="px-4 py-2 bg-purple-950/60 border border-purple-800/40 text-purple-300 rounded-xl hover:bg-purple-900/50 text-xs transition">
          ← بازگشت به داشبورد مدیرعامل
        </Link>
      </header>

      {/* کارت‌های شاخص‌های کلیدی مالی حقوق */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-[#17142b] p-5 rounded-2xl border border-purple-900/30">
          <h3 className="text-xs text-gray-400">جمع کل حقوق و پورسانت پرداختی</h3>
          <p className="text-2xl font-bold text-emerald-400 mt-2">{totalPayroll.toLocaleString("fa-IR")} تومان</p>
          <span className="text-xs text-gray-400 mt-1 inline-block">۴ ویزیتور فعال استان کرمان</span>
        </div>
        <div className="bg-[#17142b] p-5 rounded-2xl border border-purple-900/30">
          <h3 className="text-xs text-gray-400">کل پورسانت و پاداش‌های تولیدشده</h3>
          <p className="text-2xl font-bold text-purple-400 mt-2">{totalCommission.toLocaleString("fa-IR")} تومان</p>
          <span className="text-xs text-purple-300 mt-1 inline-block">فروش خالص + وصولی مطالبات</span>
        </div>
        <div className="bg-[#17142b] p-5 rounded-2xl border border-purple-900/30">
          <h3 className="text-xs text-gray-400">بالاترین نرخ تحقق تارگت</h3>
          <p className="text-2xl font-bold text-indigo-400 mt-2">۱۲۶٪ (امیرانی - سیرجان)</p>
          <span className="text-xs text-emerald-400 mt-1 inline-block">پورسانت پلکانی سطح طلایی</span>
        </div>
        <div className="bg-[#17142b] p-5 rounded-2xl border border-purple-900/30">
          <h3 className="text-xs text-gray-400">فرمول فعال پورسانت کیاراد</h3>
          <p className="text-base font-bold text-amber-400 mt-2">۲.۵٪ تا ۴.۵٪ پلکانی</p>
          <span className="text-xs text-gray-400 mt-1 inline-block">+ پاداش شلف سوآلین ویرا</span>
        </div>
      </div>

      {/* جدول تفصیلی حقوق و پورسانت */}
      <div className="bg-[#17142b] p-6 rounded-2xl border border-purple-900/30 mb-8">
        <h2 className="text-base font-semibold text-purple-200 mb-4">جدول کارکرد و محاسبه حقوق ماهانه ویزیتورها (شهریور ۱۴۰۵)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-right text-xs md:text-sm">
            <thead className="bg-[#0a0814] text-gray-400 border-b border-purple-900/30">
              <tr>
                <th className="p-3">ویزیتور و منطقه</th>
                <th className="p-3">حقوق پایه</th>
                <th className="p-3">فروش ناخالص</th>
                <th className="p-3">برگشتی</th>
                <th className="p-3">خالص فروش</th>
                <th className="p-3">تحقق تارگت</th>
                <th className="p-3">درصد پورسانت</th>
                <th className="p-3">پورسانت فروش</th>
                <th className="p-3">پاداش وصول و شلف</th>
                <th className="p-3">کسورات</th>
                <th className="p-3 text-emerald-400 font-bold">خالص دریافتی</th>
                <th className="p-3 text-center">فیش حقوقی</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-purple-900/20">
              {payrollList.map((v) => (
                <tr key={v.id} className="hover:bg-purple-950/20 transition">
                  <td className="p-3 font-semibold text-gray-100">{v.name} ({v.region})</td>
                  <td className="p-3 text-gray-300">{v.baseSalary.toLocaleString("fa-IR")}</td>
                  <td className="p-3 text-gray-300">{v.grossSales.toLocaleString("fa-IR")}</td>
                  <td className="p-3 text-red-400">{v.returns > 0 ? `-${v.returns.toLocaleString("fa-IR")}` : "۰"}</td>
                  <td className="p-3 font-bold text-gray-100">{v.netSales.toLocaleString("fa-IR")}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded-lg text-xs ${v.achievement >= 100 ? "bg-emerald-950/60 text-emerald-300 border border-emerald-500/30" : "bg-amber-950/60 text-amber-300 border border-amber-500/30"}`}>
                      {v.achievement}٪
                    </span>
                  </td>
                  <td className="p-3 font-bold text-purple-300">{v.rate}٪</td>
                  <td className="p-3 text-purple-300">{v.commission.toLocaleString("fa-IR")}</td>
                  <td className="p-3 text-indigo-300">{(v.collectionBonus + v.focusBonus).toLocaleString("fa-IR")}</td>
                  <td className="p-3 text-red-400">-{v.deductions.toLocaleString("fa-IR")}</td>
                  <td className="p-3 font-bold text-emerald-400 text-base">{v.netPay.toLocaleString("fa-IR")} تومان</td>
                  <td className="p-3 text-center">
                    <button onClick={() => setSelectedVisitor(v)} className="px-3 py-1 bg-purple-950/70 border border-purple-800 text-purple-300 hover:bg-purple-900/60 rounded-lg text-xs transition">
                      مشاهده فیش
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* مودال مشاهده و چاپ فیش حقوقی */}
      {selectedVisitor && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center p-4 z-50">
          <div className="bg-[#17142b] border border-purple-800/60 rounded-2xl max-w-lg w-full p-6 shadow-2xl">
            <div className="flex justify-between items-center pb-4 border-b border-purple-900/40">
              <h3 className="font-bold text-lg text-purple-300">فیش حقوق و پورسانت: {selectedVisitor.name}</h3>
              <button onClick={() => setSelectedVisitor(null)} className="text-gray-400 hover:text-white">✕</button>
            </div>
            <div className="py-4 space-y-3 text-xs md:text-sm">
              <div className="flex justify-between py-1 border-b border-purple-900/20"><span>منطقه تحت پوشش:</span><span>{selectedVisitor.region}</span></div>
              <div className="flex justify-between py-1 border-b border-purple-900/20"><span>حقوق پایه قانون کار:</span><span>{selectedVisitor.baseSalary.toLocaleString("fa-IR")} تومان</span></div>
              <div className="flex justify-between py-1 border-b border-purple-900/20"><span>خالص فروش محقق‌شده:</span><span>{selectedVisitor.netSales.toLocaleString("fa-IR")} تومان</span></div>
              <div className="flex justify-between py-1 border-b border-purple-900/20"><span>پورسانت فروش ({selectedVisitor.rate}٪):</span><span className="text-purple-300 font-bold">{selectedVisitor.commission.toLocaleString("fa-IR")} تومان</span></div>
              <div className="flex justify-between py-1 border-b border-purple-900/20"><span>پاداش وصول مطالبات:</span><span>{selectedVisitor.collectionBonus.toLocaleString("fa-IR")} تومان</span></div>
              <div className="flex justify-between py-1 border-b border-purple-900/20"><span>پاداش فروش سوآلین ویرا:</span><span>{selectedVisitor.focusBonus.toLocaleString("fa-IR")} تومان</span></div>
              <div className="flex justify-between py-1 border-b border-purple-900/20 text-red-400"><span>کسورات بیمه و مالیات:</span><span>-{selectedVisitor.deductions.toLocaleString("fa-IR")} تومان</span></div>
              <div className="flex justify-between py-3 border-t border-purple-700/50 font-bold text-base text-emerald-400"><span>مبلغ خالص قابل واریز:</span><span>{selectedVisitor.netPay.toLocaleString("fa-IR")} تومان</span></div>
            </div>
            <div className="flex gap-3 pt-4">
              <button onClick={() => window.print()} className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold">چاپ فیش حقوقی</button>
              <button onClick={() => setSelectedVisitor(null)} className="px-5 py-2.5 bg-gray-800 text-gray-300 rounded-xl text-xs">بستن</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}