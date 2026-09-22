"use client";
import { authFetch } from "../../lib/secure-api";

import React, { useState, useEffect } from "react";
import Link from "next/link";

export default function KermanBasesPage() {
  const [bases, setBases] = useState([]);
  const [filtered, setFiltered] = useState([]);
  const [activeTab, setActiveTab] = useState("all");
  const [search, setSearch] = useState("");
  const [cityFilter, setCityFilter] = useState("all");

  useEffect(() => {
    authFetch("/operations/customers-list")
      .then(r => r.json())
      .then(data => {
        const list = Array.isArray(data) ? data : (data.customers || []);
        setBases(list);
        setFiltered(list);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    let res = bases;
    if (activeTab !== "all") {
      res = res.filter(b => b.customer_type === activeTab);
    }
    if (cityFilter !== "all") {
      res = res.filter(b => b.city === cityFilter);
    }
    if (search.trim()) {
      res = res.filter(b => b.name?.includes(search) || b.city?.includes(search) || b.phone?.includes(search));
    }
    setFiltered(res);
  }, [activeTab, cityFilter, search, bases]);

  const cities = Array.from(new Set(bases.map(b => b.city).filter(Boolean)));

  return (
    <div style={{ minHeight: "100vh", background: "#0F172A", color: "#F8FAFC", padding: "24px", direction: "rtl", fontFamily: "tahoma" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      <div style={{ maxWidth: "1100px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: "bold", color: "#38BDF8", margin: 0 }}>🏢 کل پایگاه‌های تحت پوشش استان کرمان</h1>
            <p style={{ fontSize: "13px", color: "#94A3B8", marginTop: "4px" }}>داروخانه‌ها، متخصصین پوست و زیبایی و فروشگاه‌های آرایشی بهداشتی استان</p>
          </div>
          <Link href="/management" style={{ background: "#334155", color: "#F8FAFC", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px" }}>
            ← بازگشت به داشبورد
          </Link>
        </div>

        {/* فیلترها و سرچ */}
        <div style={{ background: "#1E293B", padding: "16px", borderRadius: "12px", display: "flex", gap: "12px", flexWrap: "wrap", alignItems: "center", marginBottom: "20px" }}>
          <input
            type="text"
            placeholder="🔍 جستجوی نام داروخانه، پزشک یا فروشگاه..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ flex: 1, minWidth: "220px", background: "#0F172A", border: "1px solid #475569", borderRadius: "8px", padding: "8px 14px", color: "#fff", fontSize: "13px" }}
          />
          <select
            value={cityFilter}
            onChange={e => setCityFilter(e.target.value)}
            style={{ background: "#0F172A", border: "1px solid #475569", borderRadius: "8px", padding: "8px 14px", color: "#fff", fontSize: "13px" }}
          >
            <option value="all">📍 همه شهرهای استان کرمان</option>
            {cities.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {/* جدول مراکز */}
        <div style={{ background: "#1E293B", borderRadius: "12px", overflow: "hidden", border: "1px solid #334155" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead>
              <tr style={{ background: "#0F172A", color: "#94A3B8", textAlign: "right", borderBottom: "1px solid #334155" }}>
                <th style={{ padding: "12px 16px" }}>ردیف</th>
                <th style={{ padding: "12px 16px" }}>نام پایگاه / مرکز</th>
                <th style={{ padding: "12px 16px" }}>شهرستان</th>
                <th style={{ padding: "12px 16px" }}>تلفن تماس</th>
                <th style={{ padding: "12px 16px" }}>سقف اعتبار (ریال)</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, idx) => (
                <tr key={item.id || idx} style={{ borderBottom: "1px solid #334155" }}>
                  <td style={{ padding: "12px 16px", color: "#64748B" }}>{idx + 1}</td>
                  <td style={{ padding: "12px 16px", fontWeight: "bold", color: "#F1F5F9" }}>{item.name}</td>
                  <td style={{ padding: "12px 16px", color: "#38BDF8" }}>{item.city || "کرمان"}</td>
                  <td style={{ padding: "12px 16px", color: "#94A3B8", direction: "ltr", textAlign: "right" }}>{item.phone || "---"}</td>
                  <td style={{ padding: "12px 16px", color: "#34D399" }}>{Number(item.credit_limit || 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div style={{ padding: "30px", textAlign: "center", color: "#94A3B8" }}>مرکزی با این مشخصات یافت نشد.</div>
          )}
        </div>
      </div>
    </div>
  );
}
