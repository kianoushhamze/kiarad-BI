"use client";
import { PortalShell } from "../../components/portal-shell";
import { authFetch, getSavedUser } from "../../lib/secure-api";
import { IranDateInput } from "../../components/IranDateInput";
import { iranTodayIso, formatIranDate } from "../../lib/iran-date";
import { matchesSearch } from "../../lib/text-search";

import React, { useCallback, useState, useEffect } from "react";

type Customer = { id: number; name: string; city?: string | null; phone?: string | null; code?: string | null };
type Product = { id: number; code?: string | null; category?: string | null; name: string; stock: number; available_stock?: number; reserved_quantity?: number; price: number; price2?: number | null };
type ProformaItem = { product_id: string; quantity: number; unit_price: number; price_level: 1 | 2 };
type CreditStatus = {
  current_balance: number;
  proforma_amount?: number;
  projected_balance?: number;
  credit_limit: number;
  grade: string;
  message: string;
};
type ProformaHistory = {
  id: number;
  salesperson_id: number;
  customer_name: string;
  total_amount: number;
  credit_grade: string;
  status: string;
  operation_key?: string | null;
  queue_status?: string | null;
  attempt_count?: number | null;
  items_json?: Array<{ product_id?: number; product_name?: string; quantity?: number; unit_price?: number; line_total?: number }> | null;
};
type ExportFile = { file_name: string; size_bytes: number; generated_at: string };
type HolooQueueItem = {
  queue_id: number; proforma_id: number; customer_name: string; total_amount: number;
  queue_status: string; mapping_ready: boolean; blockers: string[];
  items_json?: Array<{ product_name?: string; quantity?: number; line_total?: number }>;
};
type HolooPaymentOptions = { cash: Array<{ code: string; name: string; balance?: string | number }>; banks: Array<{ code: string; name: string; has_pos: boolean }>; invoice_write_enabled: false };

export default function ProformaPage() {
  const [mounted, setMounted] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState("");
  const [customerQuery, setCustomerQuery] = useState("");
  const [productQuery, setProductQuery] = useState("");
  const [showOutOfStock, setShowOutOfStock] = useState(false);
  const [creditStatus, setCreditStatus] = useState<CreditStatus | null>(null);
  const [items, setItems] = useState<ProformaItem[]>([{ product_id: "", quantity: 1, unit_price: 0, price_level: 1 }]);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<ProformaHistory[]>([]);
  const [holooQueue, setHolooQueue] = useState<HolooQueueItem[]>([]);
  const [holooQueueError, setHolooQueueError] = useState("");
  const [holooPaymentOptions, setHolooPaymentOptions] = useState<HolooPaymentOptions | null>(null);
  const [paymentOptionsBusy, setPaymentOptionsBusy] = useState(false);
  const [paymentOptionsError, setPaymentOptionsError] = useState("");
  const [exports, setExports] = useState<ExportFile[]>([]);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportDate, setExportDate] = useState("");
  const [exportError, setExportError] = useState("");
  const [isManager, setIsManager] = useState(false);
  const [canManageProformas, setCanManageProformas] = useState(false);
  const [currentSalespersonId, setCurrentSalespersonId] = useState<number | null>(null);
  const [cancellingId, setCancellingId] = useState<number | null>(null);

  // تابع یکپارچه برای نمایش ۳ رقم ۳ رقم ارقام بدون تداخل سرور و مرورگر
  const formatPrice = (val: number | string | null | undefined) => {
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

  const loadHolooQueue = useCallback(() => {
    authFetch("/operations/proformas/holoo-queue", { headers: getHeaders() })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "پیش‌بررسی صف هلو دریافت نشد");
        setHolooQueue(Array.isArray(data.items) ? data.items : []);
        setHolooQueueError("");
      })
      .catch(error => setHolooQueueError(error instanceof Error ? error.message : "پیش‌بررسی صف هلو دریافت نشد"));
  }, []);

  const loadHolooPaymentOptions = async () => {
    setPaymentOptionsBusy(true);
    setPaymentOptionsError("");
    try {
      const res = await authFetch("/holoo/payment-options", { headers: getHeaders() });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "خواندن حساب‌های هلو انجام نشد");
      setHolooPaymentOptions(data);
    } catch (error) {
      setPaymentOptionsError(error instanceof Error ? error.message : "خواندن حساب‌های هلو انجام نشد");
    } finally { setPaymentOptionsBusy(false); }
  };

  const loadHistory = useCallback(() => {
    authFetch("/operations/proformas/my", { headers: getHeaders() })
      .then(res => res.json())
      .then(data => setHistory(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const loadExports = useCallback(() => {
    authFetch("/operations/proformas/exports", { headers: getHeaders() })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "خواندن خروجی‌ها ناموفق بود");
        setExports(Array.isArray(data.items) ? data.items : []);
        setExportError("");
      })
      .catch(() => setExportError("دریافت فهرست خروجی‌ها انجام نشد؛ دوباره تلاش کنید."));
  }, []);

  useEffect(() => {
    const savedUser = getSavedUser();
    const manager = savedUser?.role === "ceo" || savedUser?.role === "sales_manager" || savedUser?.role === "finance";
    Promise.resolve().then(() => {
      setMounted(true);
      setExportDate(new Date(Date.parse(iranTodayIso()+"T12:00:00Z")-86400000).toISOString().slice(0,10));
      setIsManager(manager);
      setCanManageProformas(savedUser?.role === "ceo" || savedUser?.role === "sales_manager");
      setCurrentSalespersonId(Number.isFinite(Number(savedUser?.salesperson_id)) && savedUser?.salesperson_id != null ? Number(savedUser.salesperson_id) : null);
    });
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
    if (manager) { loadExports(); loadHolooQueue(); }
  }, [loadExports, loadHistory, loadHolooQueue]);

  const loadProducts = () => {
    authFetch("/operations/products-list", { headers: getHeaders() })
      .then(res => res.json())
      .then(data => setProducts(Array.isArray(data) ? data : []))
      .catch(() => {});
  };

  const generateSelectedExport = async () => {
    if (!exportDate) { setMessage("تاریخ خروجی را مشخص کنید."); return; }
    setExportBusy(true);
    setMessage("");
    try {
      const res = await authFetch("/operations/proformas/exports/generate", { method: "POST", body: JSON.stringify({date:exportDate}) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "ساخت خروجی ناموفق بود");
      setMessage(data.records ? `خروجی ${formatIranDate(exportDate)} با ${data.records} پیش‌فاکتور ساخته شد.` : `در ${formatIranDate(exportDate)} پیش‌فاکتوری در پنل ثبت نشده است؛ فایل فقط سرستون دارد.`);
      loadExports();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ساخت خروجی ناموفق بود");
    } finally {
      setExportBusy(false);
    }
  };

  const downloadExport = async (fileName: string) => {
    const res = await authFetch(`/operations/proformas/exports/${encodeURIComponent(fileName)}`);
    if (!res.ok) {
      setMessage("دانلود خروجی ناموفق بود");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const cancelProforma = async (proforma: ProformaHistory) => {
    if (!window.confirm(`پیش‌فاکتور شماره ${proforma.id} لغو شود و رزرو کالاهای آن آزاد شود؟`)) return;
    setCancellingId(proforma.id);
    setMessage("");
    try {
      const res = await authFetch(`/operations/proformas/${proforma.id}/cancel`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "لغو پیش‌فاکتور ناموفق بود");
      setMessage(`پیش‌فاکتور #${proforma.id} لغو شد؛ ${Number(data.reservations_released || 0)} رزرو کالا آزاد شد.`);
      loadHistory();
      loadProducts();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "لغو پیش‌فاکتور ناموفق بود");
    } finally {
      setCancellingId(null);
    }
  };

  const queueProforma = async (id: number) => {
    setCancellingId(id);
    try {
      const response = await authFetch(`/operations/proformas/${id}/queue`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "ثبت در صف ناموفق بود");
      setMessage(`پیش‌فاکتور شماره ${id} در صف ثبت در هلو قرار گرفت؛ هنوز به هلو ارسال نشده است.`);
      loadHistory();
      loadHolooQueue();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "ثبت در صف ناموفق بود");
    } finally { setCancellingId(null); }
  };

  const decideProforma = async (id: number, decision: "approve" | "reject") => {
    const label = decision === "approve" ? "تأیید" : "رد";
    if (decision === "reject" && !window.confirm(`پیش‌فاکتور شماره ${id} رد شود و رزرو کالاهای آن آزاد شود؟`)) return;
    setCancellingId(id);
    setMessage("");
    try {
      const response = await authFetch(`/operations/proformas/${id}/${decision}`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `${label} پیش‌فاکتور ناموفق بود`);
      setMessage(decision === "approve"
        ? `پیش‌فاکتور شماره ${id} تأیید شد و اکنون آمادهٔ ورود به صف هلو است.`
        : `پیش‌فاکتور شماره ${id} رد شد؛ ${Number(result.reservations_released || 0)} رزرو کالا آزاد شد.`);
      loadHistory();
      loadProducts();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${label} پیش‌فاکتور ناموفق بود`);
    } finally {
      setCancellingId(null);
    }
  };

  const handleCustomerChange = (customerId: string) => {
    setSelectedCustomer(customerId);
    setCreditStatus(null);
  };

  const handleProductChange = (index: number, productId: string) => {
    const prod = products.find(p => p.id === parseInt(productId));
    setItems(current => current.map((item,i) => i === index
      ? {...item, product_id: productId, price_level: 1, unit_price: Number(prod?.price || 0)} : item));
  };

  const handlePriceLevelChange = (index: number, level: 1 | 2) => {
    setItems(current => current.map((item,i) => {
      if (i !== index) return item;
      const product = products.find(p => String(p.id) === item.product_id);
      const price = level === 1 ? product?.price : product?.price2;
      return {...item, price_level: level, unit_price: Number(price || 0)};
    }));
  };

  const handleQuantityChange = (index: number, qty: string) => {
    const newItems = [...items];
    newItems[index].quantity = parseFloat(qty) || 0;
    setItems(newItems);
  };

  const addItem = () => setItems([...items, { product_id: "", quantity: 1, unit_price: 0, price_level: 1 }]);
  const removeItem = (index: number) => setItems(items.filter((_, i) => i !== index));

  const calculateTotal = () => items.reduce((sum, item) => sum + (item.quantity * item.unit_price), 0);

  // اعتبارسنجی سقف بدهی همیشه با مبلغ همین پیش‌فاکتور (مجموع اقلام) گرفته می‌شود؛
  // با هر تغییر در اقلام یا مشتری دوباره سنجیده می‌شود تا «همه سبز» رخ ندهد.
  useEffect(() => {
    if (!selectedCustomer) return;
    const amount = calculateTotal();
    const query = Number.isFinite(amount) && amount > 0 ? `?proforma_amount=${encodeURIComponent(String(Math.round(amount)))}` : "";
    let cancelled = false;
    authFetch(`/operations/customers/${selectedCustomer}/credit${query}`, { headers: getHeaders() })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "گرفتن وضعیت اعتبار مشتری ناموفق بود.");
        return data;
      })
      .then(data => { if (!cancelled) setCreditStatus(data); })
      .catch(error => {
        if (cancelled) return;
        setCreditStatus(null);
        setMessage(error instanceof Error ? error.message : "گرفتن وضعیت اعتبار مشتری ناموفق بود.");
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCustomer, items]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedCustomer) {
      alert("لطفاً ابتدا مشتری را انتخاب کنید");
      return;
    }
    if (items.some(item => !item.product_id || !Number.isFinite(item.unit_price) || item.unit_price <= 0 || !Number.isFinite(item.quantity) || item.quantity <= 0)) {
      setMessage("کالا، تعداد و سطح قیمت معتبر را برای همهٔ ردیف‌ها انتخاب کنید.");
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
          total_amount: calculateTotal(),
          notes,
          items: items.map(it => ({
            product_id: parseInt(it.product_id),
            quantity: it.quantity,
            price_level: it.price_level
          }))
        })
      });

      const resData = await res.json();
      if (res.ok) {
        const proformaId = resData.proforma_id ?? resData.proforma?.id;
        setMessage(`پیش‌فاکتور #${proformaId} با موفقیت ثبت شد [وضعیت: ${resData.status === "approved" ? "تأیید خودکار" : "در انتظار تأیید مدیریت"}].${resData.inventory_reserved ? " موجودی اقلام برای این پیش‌فاکتور رزرو شد." : ""}`);
        setItems([{ product_id: "", quantity: 1, unit_price: 0, price_level: 1 }]);
        setNotes("");
        loadHistory();
        loadProducts();
      } else {
        setMessage(`خطا: ${resData.detail || "ثبت نشد"}`);
      }
    } catch {
      setMessage("خطا در برقراری ارتباط با سرور");
    }
    setLoading(false);
  };

  const getGradeColor = (grade: string) => {
    if (grade === "unrated") return "#94A3B8";
    if (grade === "green") return "#10B981";
    if (grade === "yellow") return "#F59E0B";
    return "#EF4444";
  };

  // به‌صورت پیش‌فرض فقط کالاهای با موجودی آزاد بیشتر از صفر در انتخابگر می‌آیند؛
  // کالای انتخاب‌شدهٔ هر ردیف همیشه در فهرست می‌ماند و سوئیچ، ناموجودها را نشان می‌دهد.
  const productAvailable = (p: Product) => showOutOfStock || Number(p.available_stock ?? p.stock ?? 0) > 0;

  if (!mounted) {
    return <div style={{ minHeight: "100vh", backgroundColor: "#080b16" }}></div>;
  }

  return (
    <PortalShell title="پیش‌فاکتورها و کارتابل ثبت" eyebrow="سفارش و رزرو کالا"><div className="kiarad-proforma" style={{ padding: "12px", backgroundColor: "transparent", color: "#f0f3ff", direction: "rtl" }}>

      {/* دکمه بازگشت مستقیم به داشبورد مدیریت بدون نیاز به ورود مجدد */}


      <div style={{ maxWidth: "1000px", margin: "0 auto" }}>
        <div className="kiarad-proforma-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h1 style={{ fontSize: "24px", fontWeight: "bold", color: "#f0f3ff" }}>ثبت پیش‌فاکتور و اعتبارسنجی آنی مشتری</h1>
        </div>

        {/* بخش انتخاب مشتری و اعتبارسنجی */}
        <div className="kiarad-proforma-card" style={{ background: "#1E293B", padding: "20px", borderRadius: "12px", marginBottom: "20px", border: "1px solid #334155" }}>
          <label style={{ display: "block", marginBottom: "8px", fontWeight: "bold" }}>انتخاب مشتری (داروخانه / کلینیک / گالری):</label>
          <input aria-label="جست‌وجوی مشتری پیش‌فاکتور" value={customerQuery} onChange={e=>setCustomerQuery(e.target.value)} placeholder="بخشی از نام، شهر، شماره یا کد مشتری" className="mb-2 w-full rounded-lg border border-slate-600 bg-slate-900 p-3 text-sm text-white"/>
          <select
            aria-label="مشتری پیش‌فاکتور"
            value={selectedCustomer}
            onChange={(e) => handleCustomerChange(e.target.value)}
            style={{ width: "100%", padding: "12px", borderRadius: "8px", background: "#0F172A", color: "#FFF", border: "1px solid #475569" }}
          >
            <option value="">-- انتخاب مشتری --</option>
            {customers.filter(c=>String(c.id)===selectedCustomer || matchesSearch(customerQuery,c.name,c.city,c.phone,c.code)).map((c) => (
              <option key={c.id} value={c.id}>{c.name} {c.city ? `(${c.city})` : ""}</option>
            ))}
          </select>

          {creditStatus && (
            <div style={{ marginTop: "16px", padding: "16px", borderRadius: "8px", background: "#0F172A", borderRight: `6px solid ${getGradeColor(creditStatus.grade)}` }}>
              <div style={{ display: "flex", gap: "24px", marginBottom: "8px", flexWrap: "wrap" }}>
                <span>مانده بدهی فعلی: <strong>{formatPrice(creditStatus.current_balance)} ریال</strong></span>
                <span>سقف اعتبار: <strong>{formatPrice(creditStatus.credit_limit)} ریال</strong></span>
                <span>رده اعتباری: <strong style={{ color: getGradeColor(creditStatus.grade) }}>{creditStatus.grade === "unrated" ? "بدون رتبه (سقف ثبت نشده)" : creditStatus.grade === "green" ? "سبز (در محدودهٔ سقف)" : creditStatus.grade === "yellow" ? "زرد (مشروط)" : "قرمز (مسدود)"}</strong></span>
              </div>
              <div style={{ fontSize: "14px", color: "#CBD5E1" }}>{creditStatus.message}</div>
            </div>
          )}
        </div>

        {/* فرم اقلام سفارش */}
        <form className="kiarad-proforma-card" onSubmit={handleSubmit} style={{ background: "#1E293B", padding: "20px", borderRadius: "12px", border: "1px solid #334155" }}>
          <h2 style={{ fontSize: "18px", marginBottom: "16px", color: "#E2E8F0" }}>اقلام پیش‌فاکتور</h2>
          <input aria-label="جست‌وجوی کالای پیش‌فاکتور" value={productQuery} onChange={e=>setProductQuery(e.target.value)} placeholder="بخشی از نام یا کد کالا؛ ترتیب واژه‌ها مهم نیست" className="mb-3 w-full rounded-lg border border-slate-600 bg-slate-900 p-3 text-sm text-white"/>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", fontSize: "13px", color: "#CBD5E1" }}>
            <input type="checkbox" checked={showOutOfStock} onChange={e => setShowOutOfStock(e.target.checked)} aria-label="نمایش کالاهای ناموجود" />
            نمایش ناموجودها (کالاهای با موجودی صفر)
          </label>
          {items.map((item, idx) => (
            <div key={idx} className="kiarad-proforma-item" style={{ display: "flex", gap: "12px", marginBottom: "12px", alignItems: "center" }}>
              <select
                aria-label={`کالای ردیف ${idx + 1}`}
                value={item.product_id}
                onChange={(e) => handleProductChange(idx, e.target.value)}
                required
                style={{ flex: 3, padding: "10px", borderRadius: "8px", background: "#0F172A", color: "#FFF", border: "1px solid #475569" }}
              >
                <option value="">-- انتخاب کالا --</option>
                {products.filter(p=>String(p.id)===item.product_id || (productAvailable(p) && matchesSearch(productQuery,p.name,p.code,p.category))).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} (آزاد: {p.available_stock ?? p.stock}{(p.reserved_quantity || 0) > 0 ? `، رزرو: ${p.reserved_quantity}` : ""}) - {formatPrice(p.price)} ریال</option>
                ))}
              </select>
              <select aria-label={`سطح قیمت ردیف ${idx + 1}`} value={item.price_level}
                onChange={event => handlePriceLevelChange(idx, Number(event.target.value) as 1 | 2)}
                disabled={!item.product_id}
                className="rounded-lg border border-slate-600 bg-slate-900 p-2 text-xs text-white">
                <option value={1}>قیمت ۱</option>
                <option value={2} disabled={Number(products.find(p => String(p.id) === item.product_id)?.price2 || 0) <= 0}>قیمت ۲</option>
              </select>
              <input
                type="number"
                min="1"
                placeholder="تعداد"
                aria-label={`تعداد ردیف ${idx + 1}`}
                value={item.quantity}
                onChange={(e) => handleQuantityChange(idx, e.target.value)}
                required
                style={{ flex: 1, padding: "10px", borderRadius: "8px", background: "#0F172A", color: "#FFF", border: "1px solid #475569" }}
              />
              <span style={{ flex: 1.5, textAlign: "left", fontSize: "14px" }}>
                <small className="block text-slate-400">واحد: {formatPrice(item.unit_price)} ریال</small>
                {formatPrice(item.quantity * item.unit_price)} ریال
              </span>
              {items.length > 1 && (
                <button type="button" onClick={() => removeItem(idx)} style={{ background: "#EF4444", color: "#FFF", border: "none", borderRadius: "6px", padding: "8px 12px", cursor: "pointer" }}>حذف</button>
              )}
            </div>
          ))}

          <button type="button" onClick={addItem} style={{ background: "#475569", color: "#FFF", border: "none", borderRadius: "8px", padding: "8px 16px", cursor: "pointer", marginBottom: "16px" }}>+ افزودن سطر کالا</button>

          <div className="kiarad-proforma-total" style={{ marginTop: "16px", borderTop: "1px solid #334155", paddingTop: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "18px" }}>مبلغ کل سفارش: <strong>{formatPrice(calculateTotal())} ریال</strong></span>
            <button
              type="submit"
              disabled={loading || calculateTotal() === 0}
              style={{ background: "#6668d9", color: "#FFF", border: "none", borderRadius: "8px", padding: "12px 28px", fontWeight: "bold", cursor: "pointer", opacity: loading ? 0.6 : 1 }}
            >
              {loading ? "در حال ثبت..." : "ثبت و صدور پیش‌فاکتور"}
            </button>
          </div>
          {message && <div style={{ marginTop: "16px", padding: "12px", borderRadius: "8px", background: "#334155", color: "#FDE047" }}>{message}</div>}
        </form>

        {/* سوابق پیش‌فاکتورهای اخیر */}
        {isManager && <div className="kiarad-proforma-card" style={{ marginTop: "32px", background: "#1E293B", padding: "20px", borderRadius: "12px", border: "1px solid #334155" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
            <div>
              <h2 style={{ fontSize: "18px", marginBottom: "6px", color: "#E2E8F0" }}>خروجی روزانه پیش‌فاکتورها</h2>
              <p style={{ color: "#94A3B8", fontSize: "13px" }}>خروجی پیش‌فاکتورهای پنل برای تاریخ انتخابی؛ خروجی روز قبل نیز ساعت ۸ ساخته می‌شود. این بخش فهرست همهٔ فاکتورهای هلو نیست.</p>
            </div>
            <label className="text-xs text-slate-300">تاریخ شمسی خروجی<IranDateInput value={exportDate} onChange={setExportDate} max={iranTodayIso()} required aria-label="تاریخ خروجی پیش‌فاکتور" className="mt-2 block rounded-lg bg-slate-900 p-2"/></label>
            <button type="button" onClick={generateSelectedExport} disabled={exportBusy || !exportDate} style={{ background: "#6668d9", color: "#fff", border: 0, borderRadius: "8px", padding: "10px 16px", cursor: "pointer" }}>
              {exportBusy ? "در حال ساخت..." : "ساخت خروجی تاریخ انتخابی"}
            </button>
          </div>
          <div style={{ display: "grid", gap: "8px", marginTop: "16px" }}>
            {exportError && <p role="alert" className="text-xs text-rose-300">{exportError}<button type="button" onClick={loadExports} className="mr-3 underline">تلاش دوباره</button></p>}
            {!exportError && exports.length === 0 && <span style={{ color: "#94A3B8", fontSize: "13px" }}>هنوز خروجی‌ای ساخته نشده است.</span>}
            {exports.slice(0, 14).map(file => <button key={file.file_name} type="button" onClick={() => downloadExport(file.file_name)} style={{ display: "flex", justifyContent: "space-between", background: "#0F172A", color: "#CBD5E1", border: "1px solid #334155", borderRadius: "8px", padding: "10px 12px", cursor: "pointer" }}>
              <span>{file.file_name}</span><span>{Math.max(1, Math.ceil(file.size_bytes / 1024))} کیلوبایت</span>
            </button>)}
          </div>
        </div>}

        <div className="kiarad-proforma-card" style={{ marginTop: "32px", background: "#1E293B", padding: "20px", borderRadius: "12px", border: "1px solid #334155" }}>
          {canManageProformas && <section style={{ marginBottom: "24px", background: "#0F172A", padding: "16px", borderRadius: "10px", border: "1px solid #334155" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", marginBottom: "12px" }}>
              <h2 style={{ fontSize: "15px", color: "#E2E8F0" }}>پیش‌بررسی نگاشت هلو</h2>
              <button type="button" onClick={loadHolooQueue} style={{ color: "#C4B5FD", fontSize: "12px" }}>به‌روزرسانی</button>
            </div>
            <p style={{ color: "#94A3B8", fontSize: "11px", lineHeight: 1.8, marginBottom: "12px" }}>این بررسی فقط کد هلو برای مشتری و کالاها را می‌سنجد؛ آماده‌بودن نگاشت به معنی آماده‌بودن پرداخت یا ارسال فاکتور نیست. دکمهٔ حساب‌ها فقط دادهٔ خواندنی می‌گیرد و ثبت نمی‌کند.</p>
            <button type="button" disabled={paymentOptionsBusy} onClick={() => void loadHolooPaymentOptions()} style={{ border: "1px solid #475569", borderRadius: "8px", padding: "8px 12px", color: "#C4B5FD", fontSize: "11px", opacity: paymentOptionsBusy ? 0.6 : 1 }}>{paymentOptionsBusy ? "در حال خواندن حساب‌ها…" : "خواندن گزینه‌های پرداخت از هلو"}</button>
            {paymentOptionsError && <p role="alert" style={{ marginTop: "8px", color: "#FCA5A5", fontSize: "11px" }}>{paymentOptionsError}</p>}
            {holooPaymentOptions && <div style={{ marginTop: "10px", color: "#CBD5E1", fontSize: "11px", lineHeight: 1.9 }}>
              <div>صندوق‌ها: {holooPaymentOptions.cash.length ? holooPaymentOptions.cash.map(x => `${x.name} (${x.code})`).join("، ") : "در پاسخ هلو موردی برنگشت"}</div>
              <div>حساب‌های بانکی: {holooPaymentOptions.banks.length ? holooPaymentOptions.banks.map(x => `${x.name} (${x.code})${x.has_pos ? " · کارت‌خوان" : ""}`).join("، ") : "در پاسخ هلو موردی برنگشت"}</div>
              <div style={{ color: "#FCD34D" }}>این اطلاعات فقط‌خواندنی است؛ ثبت فاکتور از این صفحه فعال نیست.</div>
            </div>}
            {holooQueueError && <p role="alert" style={{ color: "#FCA5A5", fontSize: "12px" }}>{holooQueueError}</p>}
            {holooQueue.map(item => <article key={item.queue_id} style={{ padding: "12px 0", borderTop: "1px solid #334155", fontSize: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", color: "#E2E8F0" }}><span>پیش‌فاکتور {item.proforma_id} · {item.customer_name}</span><span style={{ color: item.mapping_ready ? "#6EE7B7" : "#FCD34D" }}>{item.mapping_ready ? "نگاشت مشتری و کالا کامل" : "نیازمند اصلاح نگاشت"}</span></div>
              {!!item.blockers?.length && <ul style={{ marginTop: "8px", color: "#FCD34D", lineHeight: 1.8 }}>{item.blockers.map((blocker, index) => <li key={index}>{blocker}</li>)}</ul>}
            </article>)}
            {!holooQueue.length && !holooQueueError && <p style={{ color: "#64748B", fontSize: "11px" }}>پیش‌فاکتور صف‌شده‌ای برای بررسی نیست.</p>}
          </section>}
          <h2 style={{ fontSize: "18px", marginBottom: "16px", color: "#E2E8F0" }}>پیش‌فاکتورهای اخیر</h2>
          <div className="kiarad-proforma-history"><table style={{ width: "100%", minWidth: "520px", textAlign: "right", borderCollapse: "collapse", fontSize: "14px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #475569", color: "#94A3B8" }}>
                <th style={{ padding: "8px" }}>شماره</th>
                <th style={{ padding: "8px" }}>مشتری</th>
                <th style={{ padding: "8px" }}>مبلغ کل</th>
                <th style={{ padding: "8px" }}>اعتبار</th>
                <th style={{ padding: "8px" }}>وضعیت</th>
                <th style={{ padding: "8px" }}>عملیات</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <React.Fragment key={h.id}>
                  <tr style={{ borderBottom: "1px solid #334155" }}>
                    <td style={{ padding: "10px" }}>#{h.id}</td>
                    <td style={{ padding: "10px" }}>{h.customer_name}</td>
                    <td style={{ padding: "10px" }}>{formatPrice(h.total_amount)} ریال</td>
                    <td style={{ padding: "10px", color: getGradeColor(h.credit_grade) }}>{h.credit_grade}</td>
                    <td style={{ padding: "10px" }}>
                      <span style={{ padding: "4px 8px", borderRadius: "4px", background: h.status === "approved" ? "#065F46" : h.status === "cancelled" ? "#7F1D1D" : "#78350F", color: "#FFF", fontSize: "12px" }}>
                        {h.status === "queued" ? "منتظر ثبت در هلو" : h.status === "approved" ? "تأیید شده" : h.status === "cancelled" ? "لغو شده" : h.status === "rejected" ? "رد شده" : h.status === "pending" ? "در انتظار تأیید" : h.status}
                      </span>
                    </td>
                    <td style={{ padding: "10px" }}>
                      {canManageProformas && h.status === "pending" && <span style={{ display: "inline-flex", gap: "6px", marginLeft: "6px" }}>
                        <button type="button" disabled={cancellingId !== null} onClick={() => decideProforma(h.id, "approve")} className="rounded-lg bg-emerald-700 px-3 py-2 text-xs text-white">تأیید</button>
                        <button type="button" disabled={cancellingId !== null} onClick={() => decideProforma(h.id, "reject")} className="rounded-lg bg-rose-900 px-3 py-2 text-xs text-white">رد و آزادسازی</button>
                      </span>}
                      {canManageProformas && h.status === "approved" && <button type="button" disabled={cancellingId !== null} onClick={() => queueProforma(h.id)} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs text-white">افزودن به صف هلو</button>}
                      {(canManageProformas || currentSalespersonId === h.salesperson_id) && h.status === "queued" && <button type="button" disabled={cancellingId !== null} onClick={() => cancelProforma(h)} className="rounded-lg bg-rose-900 px-3 py-2 text-xs text-white">لغو و آزادسازی کالا</button>}
                      {(canManageProformas || currentSalespersonId === h.salesperson_id) && ["pending", "approved"].includes(h.status) && <button type="button" onClick={() => cancelProforma(h)} disabled={cancellingId === h.id} style={{ background: "#7F1D1D", color: "#FEE2E2", border: "1px solid #991B1B", borderRadius: "6px", padding: "6px 10px", cursor: cancellingId === h.id ? "wait" : "pointer", opacity: cancellingId === h.id ? 0.6 : 1 }}>{cancellingId === h.id ? "در حال لغو…" : "لغو و آزادسازی کالا"}</button>}
                    </td>
                  </tr>
                  {h.items_json?.length ? <tr style={{ borderBottom: "1px solid #334155", color: "#CBD5E1" }}><td colSpan={6} style={{ padding: "8px 14px 12px" }}>
                    {h.items_json.map((item, index) => <span key={`${item.product_id || item.product_name}-${index}`} style={{ display: "inline-block", margin: "4px 0 0 12px", fontSize: "12px" }}>
                      {item.product_name || "کالا"} × {formatPrice(item.quantity)} · {formatPrice(item.line_total)} ریال
                    </span>)}
                  </td></tr> : null}
                </React.Fragment>
              ))}
            </tbody>
          </table></div>
        </div>
      </div>
    </div></PortalShell>
  );
}
