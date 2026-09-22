"use client";

import React, { useState, useEffect } from "react";

export default function CompensationModal({ salesperson, onClose }: { salesperson: any; onClose: () => void }) {
  const [hourlyRate, setHourlyRate] = useState(0);
  const [minHours, setMinHours] = useState(176);
  const [settlementPercent, setSettlementPercent] = useState(0);
  const [dailyMission, setDailyMission] = useState(0);
  const [perKmRate, setPerKmRate] = useState(0);
  const [targets, setTargets] = useState<any[]>([]);

  useEffect(() => {
    fetch(`/api/compensation/contract/${salesperson.id}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.configured) {
          setHourlyRate(d.hourly_rate);
          setMinHours(d.min_monthly_hours);
          setSettlementPercent(d.settlement_commission_percent);
          setDailyMission(d.daily_mission_allowance);
          setPerKmRate(d.per_km_rate);
          setTargets(d.targets || []);
        }
      });
  }, [salesperson.id]);

  const addTarget = (type: "brand" | "product") => {
    setTargets([...targets, { target_type: type, item_identifier: "", item_title: "", target_amount: 0, target_quantity: 0, commission_percent: 0 }]);
  };

  const handleSave = async () => {
    await fetch(`/api/compensation/contract/${salesperson.id}`, {
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
    alert("قرارداد با موفقیت ذخیره شد.");
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-900 border border-purple-500/40 w-full max-w-2xl rounded-2xl p-6 text-right space-y-4">
        <div className="flex justify-between border-b border-slate-800 pb-2">
          <h3 className="font-bold text-white">تنظیم فرمول حقوق: {salesperson.full_name}</h3>
          <button onClick={onClose} className="text-slate-400">✕</button>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-300 block mb-1">دستمزد ساعتی قانون کار (ریال):</label>
            <input type="number" value={hourlyRate} onChange={(e) => setHourlyRate(Number(e.target.value))} className="w-full bg-slate-800 p-2 rounded text-white text-sm" />
          </div>
          <div>
            <label className="text-xs text-slate-300 block mb-1">درصد پورسانت تسویه هلو (%):</label>
            <input type="number" value={settlementPercent} onChange={(e) => setSettlementPercent(Number(e.target.value))} className="w-full bg-slate-800 p-2 rounded text-white text-sm" />
          </div>
        </div>
        <div className="flex justify-between items-center pt-2">
          <span className="text-xs text-purple-300 font-bold">تارگت‌های برندی و کالایی</span>
          <button onClick={() => addTarget("brand")} className="bg-purple-600 text-white text-xs px-2 py-1 rounded">+ تارگت برند</button>
        </div>
        {targets.map((t, i) => (
          <div key={i} className="flex gap-2 items-center text-xs">
            <input placeholder="نام برند یا کد کالا" value={t.item_title} onChange={(e) => { const u = [...targets]; u[i].item_title = e.target.value; u[i].item_identifier = e.target.value; setTargets(u); }} className="bg-slate-800 p-1.5 rounded text-white w-1/3" />
            <input type="number" placeholder="مبلغ تارگت" value={t.target_amount} onChange={(e) => { const u = [...targets]; u[i].target_amount = Number(e.target.value); setTargets(u); }} className="bg-slate-800 p-1.5 rounded text-white w-1/3" />
            <input type="number" placeholder="درصد پورسانت %" value={t.commission_percent} onChange={(e) => { const u = [...targets]; u[i].commission_percent = Number(e.target.value); setTargets(u); }} className="bg-slate-800 p-1.5 rounded text-white w-1/4" />
          </div>
        ))}
        <div className="flex justify-end gap-2 pt-4">
          <button onClick={onClose} className="px-3 py-1.5 bg-slate-800 text-white rounded text-sm">انصراف</button>
          <button onClick={handleSave} className="px-4 py-1.5 bg-purple-600 text-white rounded font-bold text-sm">ذخیره</button>
        </div>
      </div>
    </div>
  );
}
