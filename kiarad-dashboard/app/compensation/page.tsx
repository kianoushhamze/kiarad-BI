"use client";
import { authFetch } from "../../lib/secure-api";

import React, { useState, useEffect } from "react";
import { PortalShell } from "@/components/portal-shell";

export default function CompensationPage() {
  const [salespersons, setSalespersons] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  const [hourlyRate, setHourlyRate] = useState(0);
  const [minHours, setMinHours] = useState(176);
  const [settlementPercent, setSettlementPercent] = useState(0);
  const [dailyMission, setDailyMission] = useState(0);
  const [perKmRate, setPerKmRate] = useState(0);
  const [targets, setTargets] = useState<any[]>([]);

  useEffect(() => {
    fetchVisitors();
  }, []);

  const fetchVisitors = async () => {
    try {
      let res = await authFetch("/salespersons");
      if (!res.ok) res = await authFetch("/salespersons");
      if (res.ok) {
        const data = await res.json();
        setSalespersons(data);
        if (data.length > 0) {
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
      const res = await authFetch(`/api/compensation/contract/${id}`);
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

  const removeTarget = (index: number) => {
    setTargets(targets.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    setMsg("");
    try {
      const res = await authFetch(`/api/compensation/contract/${selectedId}`, {
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
        setMsg("✅ فرمول و قرارداد این ویزیتور با موفقیت ذخیره شد.");
      } else {
        setMsg("❌ خطا در ذخیره‌سازی اطلاعات.");
      }
    } catch (e) {
      setMsg("❌ خطا در برقراری ارتباط با سرور.");
    } finally {
      setSaving(false);
    }
  };

  const selectedVisitor = salespersons.find((s) => s.id === selectedId);

  return (
    <PortalShell>
      <div className="space-y-6 text-right" dir="rtl">
        <div>
          <h1 className="text-2xl font-bold text-white">⚖️ فرمول و قراردادهای اختصاصی ویزیتورها</h1>
          <p className="text-slate-400 text-sm mt-1">
            تعیین و ویرایش فرمول محاسبه حقوق اداره کار، تارگت‌های برندی و کالایی، درصد تسویه هلو و حق ماموریت به تفکیک هر شخص.
          </p>
        </div>

        {/* لیست انتخاب ویزیتورها */}
        <div className="bg-slate-900 border border-purple-900/40 p-4 rounded-2xl">
          <h3 className="text-xs font-bold text-purple-300 mb-3">انتخاب ویزیتور جهت تنظیم فرمول:</h3>
          {loading ? (
            <p className="text-slate-500 text-sm">در حال دریافت لیست ویزیتورها...</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {salespersons.map((sp) => (
                <button
                  key={sp.id}
                  onClick={() => handleSelectVisitor(sp.id)}
                  className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
                    selectedId === sp.id
                      ? "bg-purple-600 text-white shadow-lg shadow-purple-900/40 border border-purple-400"
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
                تنظیم فرمول محاسبه برای: <span className="text-white">{selectedVisitor.full_name}</span>
              </h2>
              {msg && <span className="text-sm font-bold text-emerald-400">{msg}</span>}
            </div>

            {/* بخش ۱: حقوق پایه اداره کار بر اساس ساعت کارکرد */}
            <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/60 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-emerald-400">
                  ۱. حقوق ثابت اداره کار (استخراج خودکار از زمان روشن/خاموش لوکیشن)
                </h3>
                <span className="text-xs text-slate-400">ساعت کارکرد با GPS پنل ویزیتور ثبت می‌شود</span>
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
                  <label className="text-xs text-slate-300 block mb-1">حداقل ساعت موظفی ماهانه:</label>
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

            {/* بخش ۲: تارگت‌های برندی و کالایی */}
            <div className="bg-slate-800/50 p-4 rounded-xl border border-slate-700/60 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-purple-400">
                    ۲. پورسانت فروش برندی و کالاهای خاص (بر اساس فروش خالص هلو)
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    فروش خالص = فاکتورهای فروش منهای برگشت از فروش استخراج‌شده از نرم‌افزار هلو
                  </p>
                </div>
                <div className="space-x-2 space-x-reverse">
                  <button
                    onClick={() => addTarget("brand")}
                    className="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all"
                  >
                    + افزودن تارگت برند کلی
                  </button>
                  <button
                    onClick={() => addTarget("product")}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all"
                  >
                    + افزودن تارگت کالای خاص
                  </button>
                </div>
              </div>

              {targets.length === 0 ? (
                <p className="text-xs text-slate-500 py-2">هنوز تارگتی برای این ویزیتور تعریف نشده است. از دکمه‌های بالا اضافه کنید.</p>
              ) : (
                <div className="space-y-2">
                  <div className="grid grid-cols-12 gap-2 text-xs text-slate-400 px-2 font-bold">
                    <div className="col-span-2">نوع</div>
                    <div className="col-span-3">نام برند / عنوان کالا</div>
                    <div className="col-span-3">مبلغ تارگت (ریال)</div>
                    <div className="col-span-2">تعداد تارگت (موردی)</div>
                    <div className="col-span-1 text-center">درصد %</div>
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
                      <div className="col-span-3">
                        <input
                          placeholder="مثلاً سوآلین ویرا یا شامپو ضدریزش"
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
                          placeholder="مبلغ تارگت ریالی"
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
                          placeholder="تعداد (اختیاری)"
                          value={t.target_quantity}
                          onChange={(e) => {
                            const u = [...targets];
                            u[idx].target_quantity = Number(e.target.value);
                            setTargets(u);
                          }}
                          className="w-full bg-slate-800 border border-slate-700 rounded-lg p-1.5 text-white"
                        />
                      </div>
                      <div className="col-span-1">
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
                        <button onClick={() => removeTarget(idx)} className="text-rose-400 hover:text-rose-300 font-bold">
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* بخش ۳: تسویه و ماموریت */}
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
                    placeholder="شهرهای اقماری استان"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-300 block mb-1">نرخ هر کیلومتر مسافت (ریال):</label>
                  <input
                    type="number"
                    value={perKmRate}
                    onChange={(e) => setPerKmRate(Number(e.target.value))}
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white text-sm"
                    placeholder="سوخت / استهلاک"
                  />
                </div>
              </div>
            </div>

            {/* دکمه ذخیره نهایی فرمول */}
            <div className="flex justify-end gap-4 pt-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="bg-purple-600 hover:bg-purple-700 text-white font-bold px-8 py-3 rounded-xl transition-all shadow-lg shadow-purple-900/40 text-sm"
              >
                {saving ? "در حال ذخیره‌سازی..." : `💾 ذخیره فرمول ${selectedVisitor.full_name}`}
              </button>
            </div>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
