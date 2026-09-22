"use client";
import { authFetch } from "../../lib/secure-api";

import React, { useState, useEffect } from "react";
import { PortalShell } from "@/components/portal-shell";

export default function ManagerPage() {
  const [activeTab, setActiveTab] = useState<"formula" | "list">("formula");
  const [salespersons, setSalespersons] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  // فیلدهای فرمول حقوق و پورسانت
  const [hourlyRate, setHourlyRate] = useState(0);
  const [minHours, setMinHours] = useState(176);
  const [settlementPercent, setSettlementPercent] = useState(0);
  const [dailyMission, setDailyMission] = useState(0);
  const [perKmRate, setPerKmRate] = useState(0);
  const [targets, setTargets] = useState<any[]>([]);

  // فیلدهای ثبت ویزیتور جدید
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [region, setRegion] = useState("");

  useEffect(() => {
    loadSalespersons();
  }, []);

  const loadSalespersons = async () => {
    try {
      let res = await authFetch("/operations/salespersons");
      if (!res.ok) res = await authFetch("/salespersons");
      if (res.ok) {
        const data = await res.json();
        setSalespersons(data);
        if (data.length > 0 && selectedId === null) {
          setSelectedId(data[0].id);
          loadContract(data[0].id);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const loadContract = async (id: number) => {
    setMsg("");
    try {
      const res = await authFetch(`/compensation/contract/${id}`);
      const data = await res.json();
      if (data.configured) {
        setHourlyRate(data.hourly_rate || 0);
        setMinHours(data.min_monthly_hours || 176);
        setSettlementPercent(data.settlement_commission_percent || 0);
        setDailyMission(data.daily_mission_allowance || 0);
        setPerKmRate(data.per_km_rate || 0);
        setTargets(data.targets || []);
      } else {
        setHourlyRate(0);
        setMinHours(176);
        setSettlementPercent(0);
        setDailyMission(0);
        setPerKmRate(0);
        setTargets([]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSelectVisitor = (id: number) => {
    setSelectedId(id);
    loadContract(id);
  };

  const addTarget = (type: "brand" | "product") => {
    setTargets([
      ...targets,
      {
        target_type: type,
        item_identifier: "",
        item_title: "",
        target_amount: 0,
        target_quantity: 0,
        commission_percent: 0,
      },
    ]);
  };

  const removeTarget = (idx: number) => {
    setTargets(targets.filter((_, i) => i !== idx));
  };

  const handleSaveContract = async () => {
    if (!selectedId) return;
    setSaving(true);
    setMsg("");
    try {
      const res = await authFetch(`/compensation/contract/${selectedId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hourly_rate: Number(hourlyRate),
          min_monthly_hours: Number(minHours),
          settlement_commission_percent: Number(settlementPercent),
          daily_mission_allowance: Number(dailyMission),
          per_km_rate: Number(perKmRate),
          targets,
        }),
      });
      if (res.ok) {
        setMsg("✅ فرمول محاسبه این ویزیتور با موفقیت ذخیره شد.");
      } else {
        setMsg("❌ خطا در ذخیره فرمول.");
      }
    } catch (e) {
      setMsg("❌ خطا در ارتباط با سرور.");
    } finally {
      setSaving(false);
    }
  };

  const handleCreateSalesperson = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await authFetch("/operations/salespersons", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName, username, password, region }),
      });
      if (res.ok) {
        alert("ویزیتور جدید ثبت شد.");
        setFullName("");
        setUsername("");
        setPassword("");
        setRegion("");
        loadSalespersons();
      }
    } catch (err) {
      alert("خطا در ثبت ویزیتور");
    }
  };

  const selectedVisitor = salespersons.find((s) => s.id === selectedId);

  return (
    <PortalShell>
      <div className="space-y-6 text-right" dir="rtl">
        {/* هدر صفحه و سوئیچ تب‌ها */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <h1 className="text-2xl font-bold text-white">مدیریت، تعریف و فرمول ویزیتورها</h1>
            <p className="text-slate-400 text-sm mt-1">
              تنظیم اختصاصی فرمول محاسبه حقوق اداره کار، پورسانت برند و کالا از هلو، درصد تسویه و حق ماموریت هر شخص.
            </p>
          </div>

          <div className="flex bg-slate-900 border border-slate-800 p-1.5 rounded-xl gap-2">
            <button
              onClick={() => setActiveTab("formula")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === "formula" ? "bg-purple-600 text-white shadow-lg shadow-purple-900/40" : "text-slate-400 hover:text-white"
              }`}
            >
              ⚙️ تنظیم فرمول و درصد هر ویزیتور
            </button>
            <button
              onClick={() => setActiveTab("list")}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${
                activeTab === "list" ? "bg-purple-600 text-white shadow-lg shadow-purple-900/40" : "text-slate-400 hover:text-white"
              }`}
            >
              ➕ تعریف ویزیتور جدید
            </button>
          </div>
        </div>

        {/* تب ۱: فرمول و درصدهای اختصاصی هر شخص */}
        {activeTab === "formula" && (
          <div className="space-y-6">
            <div className="bg-slate-900 border border-purple-900/40 p-4 rounded-2xl">
              <h3 className="text-xs font-bold text-purple-300 mb-3">یک ویزیتور را انتخاب کنید تا فرمول آن نمایش داده شود:</h3>
              {loading ? (
                <p className="text-slate-500 text-sm">در حال دریافت لیست ویزیتورها...</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {salespersons.map((sp) => (
                    <button
                      key={sp.id}
                      onClick={() => handleSelectVisitor(sp.id)}
                      className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
                        selectedId === sp.id
                          ? "bg-purple-600 text-white border border-purple-400 shadow-md shadow-purple-900/40"
                          : "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
                      }`}
                    >
                      👤 {sp.full_name} ({sp.region || "عمومی"})
                    </button>
                  ))}
                </div>
              )}
            </div>

            {selectedVisitor && (
              <div className="bg-slate-900 border border-purple-900/40 p-6 rounded-2xl space-y-6">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h2 className="text-lg font-bold text-purple-200">
                    فرمول محاسبه اختصاصی برای: <span className="text-white">{selectedVisitor.full_name}</span>
                  </h2>
                  {msg && <span className="text-sm font-bold text-emerald-400">{msg}</span>}
                </div>

                {/* ۱. حقوق ثابت اداره کار بر اساس ساعت کارکرد لوکیشن */}
                <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/60 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-emerald-400">
                      ۱. حقوق ثابت اداره کار (استخراج خودکار ساعات کارکرد از زمان روشن/خاموش لوکیشن)
                    </h3>
                    <span className="text-xs text-slate-400">ساعت کارکرد با GPS پنل پرسنل محاسبه می‌شود</span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs text-slate-300 block mb-1">دستمزد هر ساعت کارکرد (ریال):</label>
                      <input
                        type="number"
                        value={hourlyRate}
                        onChange={(e) => setHourlyRate(Number(e.target.value))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                        placeholder="مثلاً ۳۵۰,۰۰۰"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-300 block mb-1">ساعت موظفی در ماه:</label>
                      <input
                        type="number"
                        value={minHours}
                        onChange={(e) => setMinHours(Number(e.target.value))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                        placeholder="۱۷۶"
                      />
                    </div>
                  </div>
                </div>

                {/* ۲. تارگت‌های برندی و کالایی بر اساس فروش خالص هلو */}
                <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/60 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-purple-400">
                        ۲. پورسانت فروش برندی و کالاهای خاص (بر اساس فروش خالص هلو)
                      </h3>
                      <p className="text-xs text-slate-400 mt-0.5">فروش خالص = فاکتورهای فروش منهای برگشت از فروش هلو</p>
                    </div>
                    <div className="space-x-2 space-x-reverse">
                      <button
                        onClick={() => addTarget("brand")}
                        className="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg"
                      >
                        + تارگت برند کلی
                      </button>
                      <button
                        onClick={() => addTarget("product")}
                        className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg"
                      >
                        + تارگت کالای خاص
                      </button>
                    </div>
                  </div>

                  {targets.length === 0 ? (
                    <p className="text-xs text-slate-500 py-2">هنوز تارگتی برای این ویزیتور تعریف نشده است. از دکمه‌های بالا اضافه کنید.</p>
                  ) : (
                    <div className="space-y-2">
                      <div className="grid grid-cols-12 gap-2 text-xs text-slate-400 px-2 font-bold">
                        <div className="col-span-2">نوع</div>
                        <div className="col-span-4">نام برند یا عنوان کالا</div>
                        <div className="col-span-3">مبلغ تارگت (ریال)</div>
                        <div className="col-span-2 text-center">درصد پورسانت %</div>
                        <div className="col-span-1 text-center">حذف</div>
                      </div>
                      {targets.map((t, idx) => (
                        <div key={idx} className="grid grid-cols-12 gap-2 bg-slate-900 p-2.5 rounded-xl items-center text-xs border border-slate-800">
                          <div className="col-span-2">
                            <span className={`px-2 py-1 rounded text-[11px] font-bold ${
                              t.target_type === "brand" ? "bg-purple-950 text-purple-300 border border-purple-800" : "bg-indigo-950 text-indigo-300 border border-indigo-800"
                            }`}>
                              {t.target_type === "brand" ? "برند کلی" : "کالای خاص"}
                            </span>
                          </div>
                          <div className="col-span-4">
                            <input
                              placeholder="مثلاً سوآلین ویرا یا شامپو کافئین"
                              value={t.item_title}
                              onChange={(e) => {
                                const u = [...targets];
                                u[idx].item_title = e.target.value;
                                u[idx].item_identifier = e.target.value;
                                setTargets(u);
                              }}
                              className="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-white"
                            />
                          </div>
                          <div className="col-span-3">
                            <input
                              type="number"
                              placeholder="مبلغ ریالی"
                              value={t.target_amount}
                              onChange={(e) => {
                                const u = [...targets];
                                u[idx].target_amount = Number(e.target.value);
                                setTargets(u);
                              }}
                              className="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-white"
                            />
                          </div>
                          <div className="col-span-2">
                            <input
                              type="number"
                              placeholder="%"
                              value={t.commission_percent}
                              onChange={(e) => {
                                const u = [...targets];
                                u[idx].commission_percent = Number(e.target.value);
                                setTargets(u);
                              }}
                              className="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-white font-bold text-center"
                            />
                          </div>
                          <div className="col-span-1 text-center">
                            <button onClick={() => removeTarget(idx)} className="text-rose-400 hover:text-rose-300 font-bold">✕</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* ۳. تسویه و ماموریت */}
                <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/60 space-y-3">
                  <h3 className="text-sm font-bold text-amber-400">۳. پورسانت تسویه هلو و ایاب‌ذهاب (ماموریت)</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className="text-xs text-slate-300 block mb-1">درصد پورسانت وصول/تسویه هلو (%):</label>
                      <input
                        type="number"
                        value={settlementPercent}
                        onChange={(e) => setSettlementPercent(Number(e.target.value))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                        placeholder="مثلاً ۱.۵"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-300 block mb-1">حق ماموریت روزانه (ریال):</label>
                      <input
                        type="number"
                        value={dailyMission}
                        onChange={(e) => setDailyMission(Number(e.target.value))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                        placeholder="شهرهای اقماری"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-300 block mb-1">نرخ هر کیلومتر مسافت (ریال):</label>
                      <input
                        type="number"
                        value={perKmRate}
                        onChange={(e) => setPerKmRate(Number(e.target.value))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                        placeholder="سوخت و استهلاک"
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end gap-4 pt-2">
                  <button
                    onClick={handleSaveContract}
                    disabled={saving}
                    className="bg-purple-600 hover:bg-purple-700 text-white font-bold px-8 py-3 rounded-xl transition-all shadow-lg shadow-purple-900/40 text-sm"
                  >
                    {saving ? "در حال ذخیره‌سازی..." : `💾 ذخیره فرمول ${selectedVisitor.full_name}`}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* تب ۲: تعریف ویزیتور جدید */}
        {activeTab === "list" && (
          <div className="bg-slate-900 border border-purple-900/40 p-5 rounded-2xl">
            <h3 className="font-bold text-purple-300 text-sm mb-4">➕ تعریف ویزیتور جدید</h3>
            <form onSubmit={handleCreateSalesperson} className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <input
                placeholder="نام و نام خانوادگی"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                required
              />
              <input
                placeholder="منطقه فعالیت"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                required
              />
              <input
                placeholder="نام کاربری"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                required
              />
              <input
                type="password"
                placeholder="رمز عبور"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                required
              />
              <div className="md:col-span-4 flex justify-end">
                <button
                  type="submit"
                  className="bg-purple-600 hover:bg-purple-700 text-white font-bold px-6 py-2 rounded-xl text-sm"
                >
                  ثبت ویزیتور
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
