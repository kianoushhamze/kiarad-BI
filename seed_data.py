"use client";
import React, { useState, useEffect } from "react";

export default function ProformaSection() {
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

  const formatPrice = (val) => {
    const n = Math.round(Number(val) || 0);
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  };

  const getHeaders = () => {
    const token = typeof window !== "undefined" ? (localStorage.getItem("token") || localStorage.getItem("access_token")) : null;
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    };
  };

  useEffect(() => {
    setMounted(true);
    const headers = getHeaders();

    fetch("http://127.0.0.1:8000/operations/customers-list", { headers })
      .then(res => res.json())
      .then(data => setCustomers(Array.isArray(data) ? data : []))
      .catch(() => {});

    fetch("http://127.0.0.1:8000/operations/products-list", { headers })
      .then(res => res.json())
      .then(data => setProducts(Array.isArray(data) ? data : []))
      .catch(() => {});

    loadHistory();
  }, []);

  const loadHistory = () => {
    fetch("http://127.0.0.1:8000/operations/proformas/my", { headers: getHeaders() })
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
    fetch(`http://127.0.0.1:8000/operations/customers/${customerId}/credit`, { headers: getHeaders() })
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
      const res = await fetch("http://127.0.0.1:8000/operations/proformas", {
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

  if (!mounted) return null;

  return (
    <div style={{ marginTop: "24px", direction: "rtl" }}>
      {/* بخش انتخاب مشتری و اعتبارسنجی */}
      <div style={{ background: "#1E293B", padding: "20px", borderRadius: "12px", marginBottom: "20px", border: "1px solid #334155" }}>
        <h3 style={{ fontSize: "18px", fontWeight: "bold", color: "#A855F7", marginBottom: "16px" }}>صدور پیش‌فاکتور و استعلام سقف اعتبار</h3>
        
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
        <h4 style={{ fontSize: "16px", marginBottom: "16px", color: "#E2E8F0" }}>اقلام سفارش</h4>
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
            {loading ? "در حال ثبت..." : "ثبت نهایی پیش‌فاکتور"}
          </button>
        </div>
        {message && <div style={{ marginTop: "16px", padding: "12px", borderRadius: "8px", background: "#334155", color: "#FDE047" }}>{message}</div>}
      </form>

      {/* سوابق پیش‌فاکتورهای اخیر */}
      <div style={{ marginTop: "24px", background: "#1E293B", padding: "20px", borderRadius: "12px", border: "1px solid #334155" }}>
        <h4 style={{ fontSize: "16px", marginBottom: "16px", color: "#E2E8F0" }}>پیش‌فاکتورهای صادرشده</h4>
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
                  <span style={{ padding: "4px 8px", borderRadius: "4px", background: h.statusبرای ادغام کامل بخش پیش‌فاکتور در **پنل اصلی** (به‌طوری‌که هم مدیرعامل و هم ویزیتورها در همان صفحه اصلی به آن دسترسی داشته باشند و نیازی به آدرس جداگانه نباشد):

یک تب با عنوان **«📄 پیش‌فاکتور و اعتبار»** به هدر و تب‌های پنل اصلی اضافه می‌کنیم که کامپوننت داخلی پیش‌فاکتور را مستقیماً در صفحه اصلی نمایش دهد.

---

### دستور ادغام در PowerShell

دستور زیر را در PowerShell اجرا کنید:

```powershell
Set-Location "D:\project\kiaradbi"

# ۱. ساخت پوشه components
New-Item -ItemType Directory -Path "kiarad-dashboard\components" -Force | Out-Null

# ۲. ساخت کامپوننت یکپارچه پیش‌فاکتور
@'
"use client";
import React, { useState, useEffect } from "react";

export default function ProformaSection() {
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState("");
  const [creditStatus, setCreditStatus] = useState(null);
  const [items, setItems] = useState([{ product_id: "", quantity: 1, unit_price: 0 }]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [history, setHistory] = useState([]);

  const fmt = (v) => Math.round(Number(v) || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  useEffect(() => {
    fetch("[http://127.0.0.1:8000/operations/customers-list](http://127.0.0.1:8000/operations/customers-list)").then(r => r.json()).then(d => setCustomers(Array.isArray(d) ? d : [])).catch(() => {});
    fetch("[http://127.0.0.1:8000/operations/products-list](http://127.0.0.1:8000/operations/products-list)").then(r => r.json()).then(d => setProducts(Array.isArray(d) ? d : [])).catch(() => {});
    loadHist();
  }, []);

  const loadHist = () => {
    fetch("[http://127.0.0.1:8000/operations/proformas/my](http://127.0.0.1:8000/operations/proformas/my)").then(r => r.json()).then(d => setHistory(Array.isArray(d) ? d : [])).catch(() => {});
  };

  const handleCust = (id) => {
    setSelectedCustomer(id);
    if (!id) return setCreditStatus(null);
    fetch(`[http://127.0.0.1:8000/operations/customers/$](http://127.0.0.1:8000/operations/customers/$){id}/credit`).then(r => r.json()).then(setCreditStatus).catch(() => {});
  };

  const handleProd = (idx, pid) => {
    const p = products.find(x => x.id === parseInt(pid));
    const next = [...items];
    next[idx].product_id = pid;
    next[idx].unit_price = p ? p.price : 0;
    setItems(next);
  };

  const total = items.reduce((s, it) => s + (it.quantity * it.unit_price), 0);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedCustomer) return alert("مشتری را انتخاب کنید");
    setLoading(true);
    try {
      const res = await fetch("[http://127.0.0.1:8000/operations/proformas](http://127.0.0.1:8000/operations/proformas)", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: parseInt(selectedCustomer),
          items: items.map(x => ({ product_id: parseInt(x.product_id), quantity: x.quantity, unit_price: x.unit_price }))
        })
      });
      const data = await res.json();
      if (res.ok) {
        setMsg(`پیش‌فاکتور #${data.proforma_id} با موفقیت ثبت شد.`);
        setItems([{ product_id: "", quantity: 1, unit_price: 0 }]);
        loadHist();
      } else {
        setMsg(`خطا: ${data.detail || "ثبت نشد"}`);
      }
    } catch {
      setMsg("خطای ارتباط با سرور");
    }
    setLoading(false);
  };

  const gradeColor = (g) => g === "green" ? "#10B981" : g === "yellow" ? "#F59E0B" : "#EF4444";

  return (
    <div style={{ marginTop: "20px", direction: "rtl", color: "#F8FAFC" }}>
      <div style={{ background: "#1E293B", padding: "18px", borderRadius: "10px", marginBottom: "16px", border: "1px solid #334155" }}>
        <label style={{ fontWeight: "bold", display: "block", marginBottom: "8px" }}>انتخاب مشتری و بررسی وضعیت اعتبار:</label>
        <select value={selectedCustomer} onChange={e => handleCust(e.target.value)} style={{ width: "100%", padding: "1برای اینکه بخش پیش‌فاکتور و اعتبارسنجی **دقیقاً جزئی از پنل اصلی** باشد و هم مدیرعامل و هم ویزیتورها در بالای همان داشبورد با یک کلیک به آن دسترسی داشته باشند:

یک نوار ناوبری (منوی دسترسی سریع) در بالای پنل اصلی قرار می‌دهیم تا تب **«📄 ثبت پیش‌فاکتور و اعتبار»** در کنار بخش‌های دیگر داشبورد قرار گیرد.

همچنین کالاها و مشتریان پایه (سوالین ویرا، درمالیست، توتال درم، ام‌سی کازمتیک و داروخانه‌های کرمان) را در دیتابیس ثبت می‌کنیم تا منوها پر شوند.

---

### دستور اجرا در PowerShell

دستور فشرده زیر را در PowerShell اجرا کنید:

```powershell
Set-Location "D:\project\kiaradbi"

# ۱. بارگذاری اطلاعات کالاها، قیمت‌ها و مشتریان در دیتابیس
@'
from db import engine
from sqlalchemy import text

with engine.begin() as conn:
    if not conn.execute(text("SELECT COUNT(*) FROM customers")).scalar():
        conn.execute(text("""
            INSERT INTO customers (code, name, phone, city, credit_limit, created_at) VALUES
            ('C101', 'داروخانه شبانه‌روزی دکتر کرمانی', '03432221100', 'کرمان', 120000000, NOW()),
            ('C102', 'داروخانه دکتر ابراهیمی', '03432456789', 'کرمان', 80000000, NOW()),
            ('C103', 'کلینیک پوست و زیبایی بهار', '03433334455', 'کرمان', 200000000, NOW()),
            ('C104', 'داروخانه دکتر صادقی', '03442223344', 'سیرجان', 60000000, NOW()),
            ('C105', 'گالری آرایشی رز', '03432112233', 'رفسنجان', 40000000, NOW())
        """))
        print("✓ مشتریان و سقف اعتبارات ثبت شدند.")

    if not conn.execute(text("SELECT COUNT(*) FROM products")).scalar():
        conn.execute(text("""
            INSERT INTO products (code, name, category, price, stock) VALUES
            ('P101', 'کرم ترمیم‌کننده سوالین ویرا ۳۰ میل', 'ترمیم‌کننده', 3800000, 150),
            ('P102', 'ژل شستشوی پوست درمالیست ۱۵۰ میل', 'شوینده', 2100000, 200),
            ('P103', 'ضدآفتاب رنگی توتال درم ۵۰ میل', 'ضدآفتاب', 4500000, 120),
            ('P104', 'کوکتل مزوتراپی ضدلک ام‌سی کازمتیک', 'مزوتراپی', 12500000, 50),
            ('P105', 'کوکتل جوانساز ام‌سی کازمتیک', 'مزوتراپی', 14000000, 45),
            ('P106', 'کرم مرطوب‌کننده قوی درمالیست', 'مرطوب‌کننده', 2900000, 180)
        """))
        print("✓ کالاها و قیمت‌ها ثبت شدند.")
