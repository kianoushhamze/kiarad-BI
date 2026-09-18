import os
import re
import py_compile
from sqlalchemy import text
from db import engine

print("==================================================================")
print(" ۱. ساخت جدول تعاملات و پیگیری‌های CRM در دیتابیس")
print("==================================================================")
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS customer_interactions (
            id SERIAL PRIMARY KEY,
            customer_name VARCHAR(200) NOT NULL,
            visitor_name VARCHAR(100) DEFAULT 'فروشنده تست',
            interaction_type VARCHAR(50) DEFAULT 'ویزیت حضوری',
            product_discussed VARCHAR(150) DEFAULT 'سوآلین ویرا',
            notes TEXT,
            next_followup_date DATE DEFAULT CURRENT_DATE + INTERVAL '2 days',
            status VARCHAR(50) DEFAULT 'در انتظار تماس',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """))

# افزودن چند دیتای نمونه اولیه در صورت خالی بودن جدول
with engine.begin() as conn:
    cnt = conn.execute(text("SELECT COUNT(*) FROM customer_interactions")).scalar()
    if cnt == 0:
        conn.execute(text("""
            INSERT INTO customer_interactions (customer_name, visitor_name, interaction_type, product_discussed, notes, next_followup_date, status) VALUES
            ('داروخانه دکتر شریفی (کرمان)', 'فروشنده تست', 'ویزیت حضوری', 'سوآلین ویرا', 'سمپل ترمیم‌کننده تحویل شد، راضی بودند. قرار شد امروز برای ثبت فاکتور تماس بگیریم.', CURRENT_DATE, 'موعد تماس امروز'),
            ('کلینیک پوست و زیبایی مهر (کرمان)', 'فروشنده تست', 'تماس تلفنی', 'ام‌سی کازمتیک', 'درخواست پیش‌فاکتور برای ۲ باکس مزوتراپی ارسال شد.', CURRENT_DATE + INTERVAL '1 day', 'در انتظار واریز'),
            ('داروخانه رازی (رفسنجان)', 'فروشنده تست', 'ویزیت حضوری', 'درمالیست', 'موجودی ژل شستشو تمام شده، فاکتور جدید ثبت شد.', CURRENT_DATE + INTERVAL '3 days', 'سفارش ثبت شد');
        """))
print("✓ جدول پیگیری‌های CRM با موفقیت در دیتابیس مستقر شد.")

print("==================================================================")
print(" ۲. افزودن اندپوینت‌های ذخیره و دریافت پیگیری‌ها در api.py")
print("==================================================================")
with open("api.py", "r", encoding="utf-8") as f:
    api_src = f.read()

crm_api_code = '''
@app.get("/crm/interactions")
def get_crm_interactions():
    """دریافت لیست پرونده‌ها و پیگیری‌های ثبت‌شده"""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, customer_name, visitor_name, interaction_type, product_discussed, notes, 
                   TO_CHAR(next_followup_date, 'YYYY/MM/DD') as next_date, status,
                   CASE WHEN next_followup_date <= CURRENT_DATE THEN true ELSE false END as is_due
            FROM customer_interactions 
            ORDER BY id DESC LIMIT 50
        """)).mappings().all()
        return [dict(r) for r in rows]

@app.post("/crm/interactions")
def add_crm_interaction(data: dict):
    """ثبت گزارش ویزیت یا تماس جدید در دیتابیس"""
    cust = data.get("customer_name", "").strip()
    vis = data.get("visitor_name", "مدیریت").strip()
    itype = data.get("interaction_type", "ویزیت حضوری")
    prod = data.get("product_discussed", "سوآلین ویرا")
    notes = data.get("notes", "").strip()
    status = data.get("status", "در انتظار تماس")
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO customer_interactions (customer_name, visitor_name, interaction_type, product_discussed, notes, status)
            VALUES (:cust, :vis, :itype, :prod, :notes, :status)
        """), {"cust": cust, "vis": vis, "itype": itype, "prod": prod, "notes": notes, "status": status})
    return {"status": "ok", "message": "پیگیری با موفقیت ثبت شد"}
'''

if "/crm/interactions" not in api_src:
    api_src += "\n" + crm_api_code
    with open("api.py", "w", encoding="utf-8") as f:
        f.write(api_src)
    py_compile.compile("api.py", doraise=True)
    print("✓ اندپوینت‌های CRM در بک‌اند فعال شدند.")

print("==================================================================")
print(" ۳. طراحی کامل و تعاملی صفحه app/crm/page.tsx")
print("==================================================================")
crm_page_file = r"D:\project\kiaradbi\kiarad-dashboard\app\crm\page.tsx"
os.makedirs(os.path.dirname(crm_page_file), exist_ok=True)

crm_full_page = '''"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";

interface Interaction {
  id: number;
  customer_name: string;
  visitor_name: string;
  interaction_type: string;
  product_discussed: string;
  notes: string;
  next_date: string;
  status: string;
  is_due: boolean;
}

export default function CrmPage() {
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "today">("all");

  // مقادیر فرم جدید
  const [custName, setCustName] = useState("");
  const [visName, setVisName] = useState("فروشنده تست");
  const [interType, setInterType] = useState("ویزیت حضوری");
  const [product, setProduct] = useState("سوآلین ویرا");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("در انتظار تماس");
  const [submitting, setSubmitting] = useState(false);

  const fetchInteractions = async () => {
    try {
      const res = await fetch("http://localhost:8000/crm/interactions");
      if (res.ok) {
        const data = await res.json();
        setInteractions(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInteractions();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!custName.trim() || !notes.trim()) return;

    setSubmitting(true);
    try {
      const res = await fetch("http://localhost:8000/crm/interactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_name: custName,
          visitor_name: visName,
          interaction_type: interType,
          product_discussed: product,
          notes: notes,
          status: status,
        }),
      });
      if (res.ok) {
        setCustName("");
        setNotes("");
        fetchInteractions();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  const displayedList = filter === "today" ? interactions.filter((i) => i.is_due) : interactions;
  const todayDueCount = interactions.filter((i) => i.is_due).length;

  return (
    <div style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      {/* هدر صفحه و دکمه بازگشت */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>📞 مرکز مدیریت پیگیری‌ها و ارتباط با مشتریان (CRM)</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>ثبت گزارش ویزیت، یادآوری نوبت تماس و پیگیری ۴۷۷ پایگاه درمانی استان کرمان</p>
        </div>
        <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </Link>
      </div>

      {/* ۳ کارت خلاصه شاخص‌های CRM */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", marginBottom: "24px" }}>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#94A3B8" }}>کل پیگیری‌های ثبت‌شده</div>
          <div style={{ fontSize: "22px", fontWeight: "bold", color: "#fff", marginTop: "6px" }}>{interactions.length} پرونده</div>
        </div>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#FBBF24" }}>⚠️ موعد پیگیری و تماس امروز</div>
          <div style={{ fontSize: "22px", fontWeight: "bold", color: "#FBBF24", marginTop: "6px" }}>{todayDueCount} مرکز در نوبت</div>
        </div>
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "12px", color: "#34D399" }}>وضعیت ثبت در دیتابیس</div>
          <div style={{ fontSize: "18px", fontWeight: "bold", color: "#34D399", marginTop: "8px" }}>● همگام و آنلاین</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 2.5fr", gap: "24px" }}>
        {/* فرم ثبت گزارش ویزیت جدید */}
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px", height: "fit-content" }}>
          <h3 style={{ margin: "0 0 14px 0", fontSize: "15px", color: "#38BDF8" }}>➕ ثبت گزارش ویزیت / تماس جدید</h3>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div>
              <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>نام داروخانه / کلینیک / پزشک:</label>
              <input
                type="text"
                required
                placeholder="مثال: داروخانه رازی کرمان"
                value={custName}
                onChange={(e) => setCustName(e.target.value)}
                style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "6px", fontSize: "13px", outline: "none" }}
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
              <div>
                <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>ویزیتور مسئول:</label>
                <select value={visName} onChange={(e) => setVisName(e.target.value)} style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px", borderRadius: "6px", fontSize: "12px" }}>
                  <option value="فروشنده تست">فروشنده تست</option>
                  <option value="مدیریت (کیانوش)">مدیریت (کیانوش)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>نوع تعامل:</label>
                <select value={interType} onChange={(e) => setInterType(e.target.value)} style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px", borderRadius: "6px", fontSize: "12px" }}>
                  <option value="ویزیت حضوری">ویزیت حضوری</option>
                  <option value="تماس تلفنی">تماس تلفنی</option>
                  <option value="جلسه مطب">جلسه با پزشک</option>
                  <option value="ارسال نمونه">ارسال کاتالوگ/سمپل</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>کالای محوری مذاکره:</label>
              <select value={product} onChange={(e) => setProduct(e.target.value)} style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px", borderRadius: "6px", fontSize: "12px" }}>
                <option value="سوآلین ویرا">کرم ترمیم‌کننده سوآلین ویرا</option>
                <option value="درمالیست">محصولات مراقبتی درمالیست</option>
                <option value="ام‌سی کازمتیک">مزوتراپی و سرم‌های MC</option>
                <option value="توتال درم">ضدآفتاب‌های توتال درم</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>شرح مذاکره و نتیجه:</label>
              <textarea
                required
                rows={3}
                placeholder="نتیجه صحبت، بازخورد سمپل، حجم خرید احتمالی..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px 12px", borderRadius: "6px", fontSize: "13px", outline: "none", resize: "none" }}
              />
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94A3B8", display: "block", marginBottom: "4px" }}>وضعیت فعلی پرونده:</label>
              <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: "100%", background: "#111C35", border: "1px solid #334155", color: "#fff", padding: "8px", borderRadius: "6px", fontSize: "12px" }}>
                <option value="در انتظار تماس">در انتظار تماس مجدد</option>
                <option value="نیاز به پیش‌فاکتور">نیاز به ارسال پیش‌فاکتور</option>
                <option value="سفارش ثبت شد">سفارش قطعی شد</option>
                <option value="عدم تمایل فعلی">عدم تمایل در این ماه</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={submitting}
              style={{ background: "#10B981", color: "#fff", border: "none", padding: "10px", borderRadius: "6px", cursor: "pointer", fontWeight: "bold", fontSize: "13px", marginTop: "4px" }}
            >
              {submitting ? "در حال ثبت در دیتابیس..." : "💾 ذخیره گزارش در پرونده پایگاه"}
            </button>
          </form>
        </div>

        {/* لیست پرونده‌ها و فیلترهای نوبت امروز */}
        <div style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "12px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ margin: 0, fontSize: "15px", color: "#F8FAFC" }}>📋 پرونده‌های پیگیری ویزیتورها</h3>
            
            <div style={{ display: "flex", gap: "8px", background: "#111C35", padding: "3px", borderRadius: "8px" }}>
              <button
                onClick={() => setFilter("all")}
                style={{ padding: "5px 12px", borderRadius: "6px", border: "none", background: filter === "all" ? "#2563EB" : "transparent", color: filter === "all" ? "#fff" : "#94A3B8", cursor: "pointer", fontSize: "12px" }}
              >
                همه ({interactions.length})
              </button>
              <button
                onClick={() => setFilter("today")}
                style={{ padding: "5px 12px", borderRadius: "6px", border: "none", background: filter === "today" ? "#F59E0B" : "transparent", color: filter === "today" ? "#000" : "#94A3B8", cursor: "pointer", fontSize: "12px", fontWeight: "bold" }}
              >
                ⚠️ نوبت تماس امروز ({todayDueCount})
              </button>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px", maxHeight: "580px", overflowY: "auto" }}>
            {displayedList.length === 0 ? (
              <div style={{ textAlign: "center", color: "#94A3B8", padding: "40px 0" }}>هیچ پیگیری در این دسته وجود ندارد.</div>
            ) : (
              displayedList.map((it) => (
                <div key={it.id} style={{ background: "#111C35", border: it.is_due ? "1px solid #F59E0B" : "1px solid #1E293B", borderRadius: "8px", padding: "14px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <div style={{ fontWeight: "bold", fontSize: "14px", color: "#38BDF8" }}>
                      {it.customer_name}
                      {it.is_due && <span style={{ marginRight: "8px", fontSize: "11px", background: "#78350F", color: "#FDE68A", padding: "2px 6px", borderRadius: "4px" }}>موعد امروز</span>}
                    </div>
                    <span style={{ fontSize: "11px", background: "#1E293B", color: "#CBD5E1", padding: "2px 8px", borderRadius: "4px" }}>{it.interaction_type}</span>
                  </div>

                  <p style={{ margin: "0 0 10px 0", fontSize: "13px", color: "#CBD5E1", lineHeight: "1.6" }}>{it.notes}</p>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", color: "#94A3B8", borderTop: "1px solid #1E293B", paddingTop: "8px" }}>
                    <div>کالای محوری: <strong style={{ color: "#fff" }}>{it.product_discussed}</strong></div>
                    <div>ویزیتور: <strong style={{ color: "#fff" }}>{it.visitor_name}</strong></div>
                    <div>موعد پیگیری: <strong style={{ color: "#34D399" }}>{it.next_date}</strong></div>
                    <div>وضعیت: <strong style={{ color: "#FBBF24" }}>{it.status}</strong></div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
'''

with open(crm_page_file, "w", encoding="utf-8") as f:
    f.write(crm_full_page)

print("✓ صفحه پیشرفته CRM بازنویسی و مستقر شد.")

print("==================================================================")
print(" ۴. ارتقای دستیار هوشمند برای پاسخگویی به پیگیری‌های CRM")
print("==================================================================")
with open("assistant_engine.py", "r", encoding="utf-8") as f:
    asst_code = f.read()

crm_assistant_logic = '''
        # استعلام پیگیری‌ها و وظایف CRM
        if any(k in q for k in ["پیگیری", "نوبت تماس", "تماس امروز", "crm", "ویزیت امروز"]):
            crm_rows = conn.execute(text("""
                SELECT customer_name, notes, status 
                FROM customer_interactions 
                WHERE next_followup_date <= CURRENT_DATE 
                ORDER BY id DESC LIMIT 5
            """)).mappings().all()
            if crm_rows:
                lines = [f"• {r['customer_name']}: {r['notes']} ({r['status']})" for r in crm_rows]
                ans = "📞 پایگاه‌های در نوبت پیگیری و تماس امروز (CRM):\\n" + "\\n".join(lines)
                return {"reply": ans, "answer": ans}
            else:
                ans = "برای امروز پیگیری فوری ثبت نشده است. تمام موارد پیگیری شده‌اند."
                return {"reply": ans, "answer": ans}
'''

if "پیگیری" not in asst_code:
    asst_code = re.sub(r'(with engine\.connect\(\) as conn:)', r'\1\n' + crm_assistant_logic, asst_code, count=1)
    with open("assistant_engine.py", "w", encoding="utf-8") as f:
        f.write(asst_code)
    py_compile.compile("assistant_engine.py", doraise=True)
    print("✓ قابلیت گزارش پیگیری‌های CRM به هوش مصنوعی اضافه شد.")

print("==================================================================")
print(" تمام مراحل با موفقیت ۱۰۰٪ کامل شدند!")
print("==================================================================")
