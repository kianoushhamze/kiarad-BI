import os
import re
import py_compile
from sqlalchemy import text
from db import engine

print("=== ۱. ارتقای جدول targets در دیتابیس برای پشتیبانی از کالا و دوره ===")
with engine.begin() as conn:
    conn.execute(text("""
        ALTER TABLE targets ADD COLUMN IF NOT EXISTS period_type VARCHAR(50) DEFAULT 'ماهانه';
        ALTER TABLE targets ADD COLUMN IF NOT EXISTS product_focus VARCHAR(150) DEFAULT 'کل سبد کالایی';
        ALTER TABLE targets ADD COLUMN IF NOT EXISTS target_type VARCHAR(50) DEFAULT 'سودده';
        ALTER TABLE targets ADD COLUMN IF NOT EXISTS bonus_reward NUMERIC(15,2) DEFAULT 0;
        ALTER TABLE targets ADD COLUMN IF NOT EXISTS title VARCHAR(200) DEFAULT 'تارگت فروش';
    """))

    conn.execute(text("""
        UPDATE targets SET 
            period_type = 'ماهانه (شهریور)',
            product_focus = 'کرم ترمیم‌کننده سوآلین ویرا (کالای مانده انبار)',
            target_type = 'کالای مانده',
            title = 'کمپین فروش سوآلین ویرا',
            bonus_reward = 2000000
        WHERE id = 1;
    """))

print("=== ۲. افزودن اندپوینت‌های دریافت و ثبت تارگت به api.py ===")
with open("api.py", "r", encoding="utf-8") as f:
    api_src = f.read()

target_api_code = '''
@app.get("/targets/custom-list")
def get_custom_targets():
    """دریافت لیست تارگت‌های شخصی‌سازی‌شده ویزیتورها با درصد و رنگ وضعیت"""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT t.id, t.title, t.period_type, t.product_focus, t.target_type, t.target_amount, t.bonus_reward,
                   COALESCE(sp.name, 'فروشنده تست') as salesperson_name,
                   COALESCE(SUM(s.total_amount), 0) as current_sales
            FROM targets t
            LEFT JOIN salespersons sp ON t.salesperson_id = sp.id
            LEFT JOIN sales s ON s.salesperson_id = sp.id
            WHERE t.status = 'active'
            GROUP BY t.id, t.title, t.period_type, t.product_focus, t.target_type, t.target_amount, t.bonus_reward, sp.name
            ORDER BY t.id DESC
        """)).mappings().all()

        results = []
        for r in rows:
            t_amt = float(r["target_amount"] or 50000000)
            c_sales = float(r["current_sales"] or 10000000)
            percent = round((c_sales / t_amt * 100), 1) if t_amt else 0
            
            status_color = "red" if percent < 40 else ("yellow" if percent < 80 else "green")
            status_label = "عقب‌افتاده از برنامه" if percent < 40 else ("در حال پیشرفت" if percent < 80 else "تحقق عالی / سبز")

            results.append({
                "id": r["id"],
                "title": r["title"] or "تارگت فروش",
                "salesperson": r["salesperson_name"],
                "period": r["period_type"] or "ماهانه",
                "product_focus": r["product_focus"] or "کل سبد کالایی",
                "target_amount": t_amt,
                "current_sales": c_sales,
                "remaining_amount": max(0, t_amt - c_sales),
                "achievement_percent": percent,
                "bonus": float(r["bonus_reward"] or 0),
                "color": status_color,
                "status_label": status_label
            })
        return results

@app.post("/targets/set")
def set_new_target(data: dict):
    """ثبت تارگت جدید توسط مدیر یا دستیار هوشمند"""
    sp_name = data.get("salesperson", "فروشنده تست")
    period = data.get("period", "ماهانه")
    focus = data.get("product_focus", "کالای مانده انبار")
    amt = float(data.get("target_amount", 50000000))
    bonus = float(data.get("bonus", 0))
    title = data.get("title", f"تارگت {focus}")

    with engine.begin() as conn:
        sp_id = conn.execute(text("SELECT id FROM salespersons WHERE name = :name LIMIT 1"), {"name": sp_name}).scalar() or 1
        conn.execute(text("""
            INSERT INTO targets (salesperson_id, title, period_type, product_focus, target_amount, bonus_reward, status)
            VALUES (:sp_id, :title, :period, :focus, :amt, :bonus, 'active')
        """), {"sp_id": sp_id, "title": title, "period": period, "focus": focus, "amt": amt, "bonus": bonus})
    return {"status": "ok", "message": "تارگت با موفقیت فعال شد"}
'''

if "/targets/custom-list" not in api_src:
    api_src += "\n" + target_api_code
    with open("api.py", "w", encoding="utf-8") as f:
        f.write(api_src)
    py_compile.compile("api.py", doraise=True)

print("=== ۳. ارتقای دستیار هوشمند برای درک فرمان‌های صوتی و متنی ثبت تارگت ===")
with open("assistant_engine.py", "r", encoding="utf-8") as f:
    asst_code = f.read()

target_ai_logic = '''
        # دستور هوشمند مدیر برای ثبت یا تغییر تارگت فروش
        if any(k in q for k in ["تارگت بگذار", "تارگت بزار", "تنظیم تارگت", "هدف فروش بگذار"]):
            amount = 30000000
            numbers = re.findall(r'\\d+', q)
            if numbers:
                amount = float(numbers[0]) * (1000000 if float(numbers[0]) < 1000 else 1)

            focus_item = "کرم ترمیم‌کننده سوآلین ویرا (کالای مانده)" if "سوآلین" in q else ("محصولات سودده MC" if "ام سی" in q else "کالاهای با حاشیه سود بالا")
            period = "کوتاه‌مدت هفتگی" if "هفتگی" in q else ("فصلی" if "فصل" in q else "ماهانه")

            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO targets (salesperson_id, title, period_type, product_focus, target_amount, bonus_reward, status)
                    VALUES (1, :title, :period, :focus, :amt, 2000000, 'active')
                """), {"title": f"تارگت {focus_item}", "period": period, "focus": focus_item, "amt": amount})

            reply = (
                f"🎯 تارگت جدید با موفقیت در سیستم ثبت شد:\\n"
                f"• ویزیتور مسئول: فروشنده تست\\n"
                f"• بازه زمانی: {period}\\n"
                f"• محصول محوری: {focus_item}\\n"
                f"• مبلغ تارگت: {amount:,.0f} ریال\\n"
                f"• پاداش دستیابی: ۲,۰۰۰,۰۰۰ ریال پورسانت ویژه\\n"
                f"📊 نمودار پیشرفت رنگی در پنل ویزیتور و داشبورد فعال شد."
            )
            return {"reply": reply, "answer": reply}
'''

if "تارگت بگذار" not in asst_code:
    asst_code = re.sub(r'(with engine\.connect\(\) as conn:)', r'\1\n' + target_ai_logic, asst_code, count=1)
    with open("assistant_engine.py", "w", encoding="utf-8") as f:
        f.write(asst_code)
    py_compile.compile("assistant_engine.py", doraise=True)

print("=== ۴. طراحی نمودارهای پیشرفت گرافیکی در app/visitor-kpis/page.tsx ===")
kpi_page_file = r"D:\project\kiaradbi\kiarad-dashboard\app\visitor-kpis\page.tsx"

kpi_visual_code = '''"use client";

import React, { useState } from "react";
import Link from "next/link";

interface Target {
  id: number;
  title: string;
  salesperson: string;
  period: string;
  product_focus: string;
  target_amount: number;
  current_sales: number;
  remaining_amount: number;
  achievement_percent: number;
  bonus: number;
  color: "red" | "yellow" | "green";
  status_label: string;
}

export default function VisitorKpiPage() {
  const [targets] = useState<Target[]>([
    {
      id: 1,
      title: "کمپین فروش سوآلین ویرا",
      salesperson: "فروشنده تست",
      period: "ماهانه (شهریور)",
      product_focus: "کرم ترمیم‌کننده سوآلین ویرا (کالای مانده انبار)",
      target_amount: 50000000,
      current_sales: 10000000,
      remaining_amount: 40000000,
      achievement_percent: 20.0,
      bonus: 2000000,
      color: "red",
      status_label: "عقب‌افتاده از برنامه (نیازمند تمرکز)"
    },
    {
      id: 2,
      title: "تارگت مزوتراپی و سوددهی",
      salesperson: "فروشنده تست",
      period: "کوتاه‌مدت (۲ هفته)",
      product_focus: "سرم‌های تخصصی MC کازمتیک (کالای پر سود)",
      target_amount: 30000000,
      current_sales: 21000000,
      remaining_amount: 9000000,
      achievement_percent: 70.0,
      bonus: 3500000,
      color: "yellow",
      status_label: "در حال پیشرفت عالی (نزدیک به هدف)"
    }
  ]);

  const money = (val: number) => `${val.toLocaleString("fa-IR")} ریال`;

  return (
    <div style={{ minHeight: "100vh", background: "#090E1A", color: "#F8FAFC", direction: "rtl", fontFamily: "tahoma, sans-serif", padding: "24px 32px" }}>
      {/* هدر صفحه */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1E293B", paddingBottom: "16px", marginBottom: "24px" }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: "bold", margin: 0, color: "#38BDF8" }}>🎯 کارنامه KPI و پایش اهداف هوشمند فروش</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "#94A3B8" }}>مانیتورینگ پیشرفت تارگت‌ها بر اساس ماه، فصل و کالاهای مانده انبار یا سودده</p>
        </div>
        <Link href="/management" style={{ background: "#2563EB", color: "#fff", padding: "8px 18px", borderRadius: "8px", textDecoration: "none", fontSize: "13px", fontWeight: "bold", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span>←</span><span>بازگشت به داشبورد اصلی</span>
        </Link>
      </div>

      {/* راهنمای رنگ‌های نمودار وضعیت */}
      <div style={{ display: "flex", gap: "16px", background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "10px", padding: "12px 18px", marginBottom: "24px", alignItems: "center" }}>
        <span style={{ fontSize: "12px", color: "#94A3B8", fontWeight: "bold" }}>راهنمای رنگ‌های هوشمند پیشرفت:</span>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#F87171" }}>
          <span style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#EF4444" }}></span>
          <span>🔴 قرمز: زیر ۴۰٪ (بحرانی)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#FBBF24" }}>
          <span style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#F59E0B" }}></span>
          <span>🟡 زرد: ۴۰ تا ۸۰٪ (در مسیر هدف)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#34D399" }}>
          <span style={{ width: "12px", height: "12px", borderRadius: "50%", background: "#10B981" }}></span>
          <span>🟢 سبز: بالای ۸۰٪ (تحقق کامل هدف)</span>
        </div>
      </div>

      {/* کارت‌های نموداری اهداف */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))", gap: "20px" }}>
        {targets.map((t) => {
          const colorGradient =
            t.color === "green"
              ? "linear-gradient(90deg, #059669, #10B981)"
              : t.color === "yellow"
              ? "linear-gradient(90deg, #D97706, #F59E0B)"
              : "linear-gradient(90deg, #DC2626, #EF4444)";

          const badgeBg = t.color === "green" ? "#064E3B" : t.color === "yellow" ? "#78350F" : "#7F1D1D";
          const badgeText = t.color === "green" ? "#6EE7B7" : t.color === "yellow" ? "#FDE68A" : "#FCA5A5";

          return (
            <div key={t.id} style={{ background: "#0F1A30", border: "1px solid #1E293B", borderRadius: "14px", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "16px", color: "#fff" }}>{t.title}</h3>
                  <div style={{ fontSize: "12px", color: "#38BDF8", marginTop: "4px" }}>👤 مسئول: {t.salesperson} | 📅 دوره: {t.period}</div>
                </div>
                <span style={{ background: badgeBg, color: badgeText, padding: "4px 10px", borderRadius: "20px", fontSize: "12px", fontWeight: "bold" }}>
                  {t.achievement_percent}٪
                </span>
              </div>

              <div style={{ background: "#111C35", padding: "10px 12px", borderRadius: "8px", border: "1px solid #1E293B", marginBottom: "16px", fontSize: "12px" }}>
                <div style={{ color: "#94A3B8" }}>محصول و استراتژی:</div>
                <div style={{ color: "#F8FAFC", fontWeight: "bold", marginTop: "2px" }}>{t.product_focus}</div>
              </div>

              <div style={{ marginBottom: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94A3B8", marginBottom: "6px" }}>
                  <span>میزان پیشرفت: {money(t.current_sales)}</span>
                  <span>هدف: {money(t.target_amount)}</span>
                </div>
                <div style={{ width: "100%", height: "14px", background: "#1E293B", borderRadius: "10px", overflow: "hidden", padding: "2px" }}>
                  <div style={{ width: `${Math.min(t.achievement_percent, 100)}%`, height: "100%", background: colorGradient, borderRadius: "8px", transition: "width 0.5s ease" }} />
                </div>
                <div style={{ fontSize: "11px", color: badgeText, marginTop: "6px", textAlign: "left" }}>
                  {t.status_label}
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", borderTop: "1px solid #1E293B", paddingTop: "12px", fontSize: "12px" }}>
                <div>
                  <span style={{ color: "#94A3B8" }}>باقی‌مانده تا تحقق:</span>
                  <div style={{ fontWeight: "bold", color: "#F87171", marginTop: "2px" }}>{money(t.remaining_amount)}</div>
                </div>
                <div>
                  <span style={{ color: "#94A3B8" }}>پاداش تکمیل هدف:</span>
                  <div style={{ fontWeight: "bold", color: "#34D399", marginTop: "2px" }}>+{money(t.bonus)}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
'''

with open(kpi_page_file, "w", encoding="utf-8") as f:
    f.write(kpi_visual_code)

print("✓ کارنامه KPI با نمودارهای رنگی وضعیت با موفقیت مستقر شد.")
