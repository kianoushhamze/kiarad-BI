"use client";
import { authFetch } from "../../lib/secure-api";

import React, { useState, useEffect } from "react";

export default function ProformaPage() {
  const [mounted, setMounted] = useState(false);
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState("");
  const [creditStatus, setCreditStatus] = useState(null);
  const [items, setItems] = useState([{ product_id: "", quantity: 1, unit_price: 0 }]);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState([]);

  // تابع یکپارچه برای نمایش ۳ رقم ۳ رقم ارقام بدون تداخل سرور و مرورگر
  const formatPrice = (val) => {
    const n = Math.round(Number(val) || 0);
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  };

  const getHeaders = () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    };
  };

  useEffect(() => {
    setMounted(true);
    const headers = getHeaders();

    authFetch("/operations/customers-list", { headers })
      .then(res => res.json())
      .then(data => setCustomers(Array.isArray(data) ? data : []))
      .catch(() => {});

    authFetch("/operations/products-list", { headers })
      .then(res => res.json())
      .then(data => setProducts(Array.isArray(data) ? data : []))
      .catch(() => {});

    loadHistory();
  }, []);

  const loadHistory = () => {
    authFetch("/operations/proformas/my", { headers: getHeaders() })
      .then(res => res.json())
      .then(data => setHistory(Array.isArray(data) ? data : []))
      .catch(() => {});
  };

  const handleCustomerChange = (customerId) => {
    setSelectedCustomer(customerId);
    if (!customerId) {
      setCreditStatus(null);
      return;
    }
    authFetch(`/operations/customers/${customerId}/credit`, { headers: getHeaders() })
      .then(res => res.json())
      .then(data => setCreditStatus(data))
      .catch(() => {});
  };

  const handleProductChange = (index, productId) => {
    const prod = products.find(p => p.id === parseInt(productId));
    const newItems = [...items];
    newItems[index].product_id = productId;
    newItems[index].unit_price = prod ? prod.price : 0;
    setItems(newItems);
  };

  const handleQuantityChange = (index, qty) => {
    const newItems = [...items];
    newItems[index].quantity = parseFloat(qty) || 0;
    setItems(newItems);
  };

  const addItem = () => setItems([...items, { product_id: "", quantity: 1, unit_price: 0 }]);
  const removeItem = (index) => setItems(items.filter((_, i) => i !== index));

  const calculateTotal = () => items.reduce((sum, item) => sum + (item.quantity * item.unit_price), 0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedCustomer) {
      alert("لطفاً ابتدا مشتری را انتخاب کنید");
      return;
    }
    setLoading(true);
    setMessage("");

    try {
      const res = await authFetch("/operations/proformas", {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          customer_id: parseInt(selectedCustomer),
          notes,
          items: items.map(it => ({
            product_id: parseInt(it.product_id),
            quantity: it.quantity,
            unit_price: it.unit_price
          }))
        })
      });

      const resData = await res.json();
      if (res.ok) {
        setMessage(`پیش‌فاکتور #${resData.proforma_id} با موفقیت ثبت شد [وضعیت: ${resData.status === "approved" ? "تأیید خودکار" : "در انتظار تأیید مدیریت"}].`);
        setItems([{ product_id: "", quantity: 1, unit_price: 0 }]);
        setNotes("");
        loadHistory();
      } else {
        setMessage(`خطا: ${resData.detail || "ثبت نشد"}`);
      }
    } catch {
      setMessage("خطا در برقراری ارتباط با سرور");
    }
    setLoading(false);
  };

  const getGradeColor = (grade) => {
    if (grade === "green") return "#10B981";
    if (grade === "yellow") return "#F59E0B";
    return "#EF4444";
  };

  if (!mounted) {
    return <div style={{ minHeight: "100vh", backgroundColor: "#0F172A" }}></div>;
  }

  return (
    <div style={{ padding: "24px", minHeight: "100vh", backgroundColor: "#0F172A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}
      <div style={{ marginBottom: "16px", display: "flex", justifyContent: "flex-end" }}>
        <a href="/management" style={{ background: "#1E293B", color: "#38BDF8", border: "1px solid #334155", padding: "8px 16px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.2)" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </a>
      </div>

      <div style={{ maxWidth: "1000px", margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h1 style={{ fontSize: "24px", fontWeight: "bold", color: "#A855F7" }}>ثبت پیش‌فاکتور و اعتبارسنجی آنی مشتری</h1>
          <a href="/login" style={{ color: "#94A3B8", textDecoration: "none", fontSize: "14px" }}>بازگشت به داشبورد</a>
        </div>

        {/* بخش انتخاب مشتری و اعتبارسنجی */}
        <div style={{ background: "#1E293B", padding: "20px", borderRadius: "12px", marginBottom: "20px", border: "1px solid #334155" }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: "bold" }}>انتخاب مشتری (داروخانه / کلینیک / گالری):</label>
          <select
            value={selectedCustomer}
            onChange={(e) => handleCustomerChange(e.target.value)}
            style={{ width: "100%", padding: "12px", borderRadius: "8px", background: "#0F172A", color: "#FFF", border: "1px solid #475569" }}
          >
            <option value="">-- انتخاب مشتری --</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>{c.name} {c.city ? `(${c.city})` : ""}</option>
            ))}
          </select>

          {creditStatus && (
            <div style={{ marginTop: "16px", padding: "16px", borderRadius: "8px", background: "#0F172A", borderRight: `6px solid ${getGradeColor(creditStatus.grade)}` }}>
              <div style={{ display: "flex", gap: "24px", marginBottom: "8px", flexWrap: "wrap" }}>
                <span>مانده بدهی فعلی: <strong>{formatPrice(creditStatus.current_balance)} ریال</strong></span>
                <span>سقف اعتبار: <strong>{formatPrice(creditStatus.credit_limit)} ریال</strong></span>
                <span>رده اعتباری: <strong style={{ color: getGradeColor(creditStatus.grade) }}>{creditStatus.grade === "green" ? "سبز (معتبر)" : creditStatus.grade === "yellow" ? "زرد (مشروط)" : "قرمز (مسدود)"}</strong></span>
              </div>
              <div style={{ fontSize: "14px", color: "#CBD5E1" }}>{creditStatus.message}</div>
            </div>
          )}
        </div>

        {/* فرم اقلام سفارش */}
        <form onSubmit={handleSubmit} style={{ background: "#1E293B", padding: "20px", borderRadius: "12px", border: "1px solid #334155" }}>
          <h2 style={{ fontSize: "18px", marginBottom: "16px", color: "#E2E8F0" }}>اقلام پیش‌فاکتور</h2>
          {items.map((item, idx) => (
            <div key={idx} style={{ display: "flex", gap: "12px", marginBottom: "12px", alignItems: "center" }}>
              <select
                value={item.product_id}
                onChange={(e) => handleProductChange(idx, e.target.value)}
                required
                style={{ flex: 3, padding: "10px", borderRadius: "8px", background: "#0F172A", color: "#FFF", border: "1px solid #475569" }}
              >
                <option value="">-- انتخاب کالا --</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} (موجودی: {p.stock}) - {formatPrice(p.price)} ریال</option>
                ))}
              </select>
              <input
                type="number"
                min="1"
                placeholder="تعداد"
                value={item.quantity}
                onChange={(e) => handleQuantityChange(idx, e.target.value)}
                required
                style={{ flex: 1, padding: "10px", borderRadius: "8px", background: "#0F172A", color: "#FFF", border: "1px solid #475569" }}
              />
              <span style={{ flex: 1.5, textAlign: "left", fontSize: "14px" }}>
                {formatPrice(item.quantity * item.unit_price)} ریال
              </span>
              {items.length > 1 && (
                <button type="button" onClick={() => removeItem(idx)} style={{ background: "#EF4444", color: "#FFF", border: "none", borderRadius: "6px", padding: "8px 12px", cursor: "pointer" }}>حذف</button>
              )}
            </div>
          ))}

          <button type="button" onClick={addItem} style={{ background: "#475569", color: "#FFF", border: "none", borderRadius: "8px", padding: "8px 16px", cursor: "pointer", marginBottom: "16px" }}>+ افزودن سطر کالا</button>

          <div style={{ marginTop: "16px", borderTop: "1px solid #334155", paddingTop: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "18px" }}>مبلغ کل سفارش: <strong>{formatPrice(calculateTotal())} ریال</strong></span>
            <button
              type="submit"
              disabled={loading || calculateTotal() === 0}
              style={{ background: "#9333EA", color: "#FFF", border: "none", borderRadius: "8px", padding: "12px 28px", fontWeight: "bold", cursor: "pointer", opacity: loading ? 0.6 : 1 }}
            >
              {loading ? "در حال ثبت..." : "ثبت و صدور پیش‌فاکتور"}
            </button>
          </div>
          {message && <div style={{ marginTop: "16px", padding: "12px", borderRadius: "8px", background: "#334155", color: "#FDE047" }}>{message}</div>}
        </form>

        {/* سوابق پیش‌فاکتورهای اخیر */}
        <div style={{ marginTop: "32px", background: "#1E293B", padding: "20px", borderRadius: "12px", border: "1px solid #334155" }}>
          <h2 style={{ fontSize: "18px", marginBottom: "16px", color: "#E2E8F0" }}>پیش‌فاکتورهای اخیر</h2>
          <table style={{ width: "100%", textAlign: "right", borderCollapse: "collapse", fontSize: "14px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #475569", color: "#94A3B8" }}>
                <th style={{ padding: "8px" }}>شماره</th>
                <th style={{ padding: "8px" }}>مشتری</th>
                <th style={{ padding: "8px" }}>مبلغ کل</th>
                <th style={{ padding: "8px" }}>اعتبار</th>
                <th style={{ padding: "8px" }}>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} style={{ borderBottom: "1px solid #334155" }}>
                  <td style={{ padding: "10px" }}>#{h.id}</td>
                  <td style={{ padding: "10px" }}>{h.customer_name}</td>
                  <td style={{ padding: "10px" }}>{formatPrice(h.total_amount)} ریال</td>
                  <td style={{ padding: "10px", color: getGradeColor(h.credit_grade) }}>{h.credit_grade}</td>
                  <td style={{ padding: "10px" }}>
                    <span style={{ padding: "4px 8px", borderRadius: "4px", background: h.status === "approved" ? "#065F46" : "#78350F", color: "#FFF", fontSize: "12px" }}>
                      {h.status === "approved" ? "تأیید شده" : "در انتظار تأیید"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
