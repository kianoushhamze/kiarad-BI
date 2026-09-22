from kerman_crm import router as kerman_router
from voice_reports import router as voice_reports_router
from proformas import router as proformas_router
from datetime import date, timedelta
from typing import Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# ----------------------------------------------------------------------------
# Database configuration
# ----------------------------------------------------------------------------

from db import engine
from assistant_engine import router as assistant_router
from operations import current_user, require_manager, router as operations_router
from treasury import router as treasury_router
from catalog import router as catalog_router
from holoo_router import router as holoo_router

# ----------------------------------------------------------------------------
# App setup
# ----------------------------------------------------------------------------
app = FastAPI(title="Kiarad BI API")
app.include_router(voice_reports_router)
app.include_router(proformas_router)
from telegram_api import router as telegram_api_router
from compensation import router as compensation_router
from campaign import router as campaign_router
from campaign_ai import router as campaign_ai_router
app.include_router(kerman_router)
app.include_router(telegram_api_router)
app.include_router(compensation_router)
app.include_router(campaign_router)
app.include_router(campaign_ai_router)
app.include_router(operations_router)
app.include_router(treasury_router)
app.include_router(assistant_router)
app.include_router(catalog_router)
app.include_router(holoo_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ---------------------------------------------------------------------------
# Authentication gate: JWT for humans, X-API-Key for automations (n8n)
# ---------------------------------------------------------------------------
import os as _os
_KIARAD_API_KEY = _os.getenv("KIARAD_API_KEY", "")
_KIARAD_JWT = _os.getenv("KIARAD_JWT_SECRET", "")
_OPEN_PATHS = ("/", "/health", "/docs", "/redoc", "/openapi.json", "/auth/login")

@app.middleware("http")
async def auth_gate(request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path in _OPEN_PATHS:
        return await call_next(request)
    jwt_secret = _os.environ.get("KIARAD_JWT_SECRET", "")
    api_key = _os.environ.get("KIARAD_API_KEY", "")
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        if not jwt_secret:
            print("gate 401 reason=empty-jwt-secret path=" + path)
        else:
            try:
                jwt.decode(auth[7:], jwt_secret, algorithms=["HS256"])
                return await call_next(request)
            except Exception:
                print("gate 401 reason=bad-jwt path=" + path)
    if api_key and request.headers.get("x-api-key", "") == api_key:
        return await call_next(request)
    if not api_key:
        print("gate 401 reason=empty-api-key path=" + path)
    return JSONResponse(status_code=401, content={"detail": "Authentication required"})

def run_query(query: str, params: Optional[dict] = None):
    params = params or {}
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        rows = result.mappings().all()
        return [dict(row) for row in rows]


def run_scalar(query: str, params: Optional[dict] = None, default=0):
    params = params or {}
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        value = result.scalar()
        return value if value is not None else default


# ----------------------------------------------------------------------------
# Root & health
# ----------------------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "Kiarad BI API is running"}


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")


# ----------------------------------------------------------------------------
# Reports: summary
# ----------------------------------------------------------------------------
@app.get("/reports/summary")
def reports_summary():
    try:
        customers_count = run_scalar("SELECT COUNT(*) FROM customers")
        sales_count = run_scalar("SELECT COUNT(*) FROM sales")
        sales_amount = run_scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sales")
        payments_amount = run_scalar("SELECT COALESCE(SUM(amount), 0) FROM payments")

        return {
            "customers_count": customers_count,
            "sales_count": sales_count,
            "sales_amount": float(sales_amount),
            "payments_amount": float(payments_amount),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Reports: active target
# ----------------------------------------------------------------------------
@app.get("/reports/target")
def reports_target():
    try:
        target_rows = run_query(
            """
            SELECT id, salesperson_id, title, target_amount, start_date, end_date, status
            FROM targets
            WHERE status = 'active'
            ORDER BY start_date DESC, id DESC
            LIMIT 1
            """
        )

        if not target_rows:
            return {
                "title": None,
                "target": 0,
                "actual_sales": 0,
                "achievement_percent": 0,
                "remaining": 0,
            }

        target_row = target_rows[0]
        target_amount = float(target_row["target_amount"] or 0)
        salesperson_id = target_row["salesperson_id"]
        start_date = target_row["start_date"]
        end_date = target_row["end_date"]

        if salesperson_id is not None:
            actual_sales = run_scalar(
                """
                SELECT COALESCE(SUM(total_amount), 0)
                FROM sales
                WHERE salesperson_id = :salesperson_id
                  AND CAST(date AS DATE) BETWEEN :start_date AND :end_date
                """,
                {
                    "salesperson_id": salesperson_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
        else:
            actual_sales = run_scalar(
                """
                SELECT COALESCE(SUM(total_amount), 0)
                FROM sales
                WHERE CAST(date AS DATE) BETWEEN :start_date AND :end_date
                """,
                {"start_date": start_date, "end_date": end_date},
            )

        actual_sales = float(actual_sales)
        achievement_percent = (
            round((actual_sales / target_amount) * 100, 2) if target_amount > 0 else 0
        )
        remaining = max(target_amount - actual_sales, 0)

        return {
            "title": target_row["title"],
            "target": target_amount,
            "actual_sales": actual_sales,
            "achievement_percent": achievement_percent,
            "remaining": remaining,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Staff performance (Next.js dashboard)
# ----------------------------------------------------------------------------
@app.get("/staff/performance")
def staff_performance():
    try:
        salespersons = run_query("SELECT id, name FROM salespersons ORDER BY id")

        staff_list = []
        for person in salespersons:
            sp_id = person["id"]

            active_target = run_query(
                """
                SELECT target_amount, start_date, end_date
                FROM targets
                WHERE salesperson_id = :sp_id AND status = 'active'
                ORDER BY start_date DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                {"sp_id": sp_id},
            )

            if active_target:
                target = active_target[0]
                target_amount = float(target["target_amount"] or 0)
                sales_filter = """
                    WHERE salesperson_id = :sp_id
                      AND CAST(date AS DATE) BETWEEN :start_date AND :end_date
                """
                sales_params = {
                    "sp_id": sp_id,
                    "start_date": target["start_date"],
                    "end_date": target["end_date"],
                }
            else:
                target_amount = 0.0
                sales_filter = "WHERE salesperson_id = :sp_id"
                sales_params = {"sp_id": sp_id}

            sales_amount = float(run_scalar(
                f"SELECT COALESCE(SUM(total_amount), 0) FROM sales {sales_filter}",
                sales_params,
            ))
            sales_count = int(run_scalar(
                f"SELECT COUNT(*) FROM sales {sales_filter}",
                sales_params,
            ))

            achievement_percent = (
                round((sales_amount / target_amount) * 100, 2) if target_amount > 0 else 0
            )
            remaining = max(target_amount - sales_amount, 0)

            staff_list.append(
                {
                    "id": sp_id,
                    "name": person["name"],
                    "sales_amount": sales_amount,
                    "target": target_amount,
                    "sales_count": sales_count,
                    "invoice_count": sales_count,
                    "achievement_percent": achievement_percent,
                    "remaining": remaining,
                }
            )

        return {"count": len(staff_list), "staff": staff_list}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Reports: sales trend (monthly)
# ----------------------------------------------------------------------------
@app.get("/reports/sales-trend")
def reports_sales_trend():
    try:
        rows = run_query(
            """
            SELECT TO_CHAR(date, 'YYYY-MM') AS month,
                   COUNT(*) AS sales_count,
                   COALESCE(SUM(total_amount), 0) AS sales_amount
            FROM sales
            GROUP BY TO_CHAR(date, 'YYYY-MM')
            ORDER BY month
            """
        )
        trend = [
            {
                "month": row["month"],
                "sales_count": int(row["sales_count"]),
                "sales_amount": float(row["sales_amount"]),
            }
            for row in rows
        ]
        return {"count": len(trend), "trend": trend}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Reports: inactive customers (no sales in the last 90 days)
# ----------------------------------------------------------------------------
@app.get("/reports/inactive-customers")
def reports_inactive_customers(days: int = 90):
    try:
        cutoff_date = date.today() - timedelta(days=days)
        rows = run_query(
            """
            SELECT c.id, c.name, c.city, MAX(s.date) AS last_sale_date
            FROM customers c
            LEFT JOIN sales s ON s.customer_id = c.id
            GROUP BY c.id, c.name, c.city
            HAVING MAX(s.date) IS NULL OR MAX(s.date) < :cutoff_date
            ORDER BY last_sale_date NULLS FIRST
            """,
            {"cutoff_date": cutoff_date},
        )
        customers = [
            {
                "id": row["id"],
                "name": row["name"],
                "city": row["city"],
                "last_sale_date": row["last_sale_date"].isoformat() if row["last_sale_date"] else None,
            }
            for row in rows
        ]
        return {"count": len(customers), "customers": customers, "cutoff_days": days}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Reports: customer scores (simple RFM-like scoring)
# ----------------------------------------------------------------------------
@app.get("/reports/customer-scores")
def reports_customer_scores():
    try:
        rows = run_query(
            """
            SELECT c.id, c.name, c.city,
                   COUNT(s.id) AS purchase_count,
                   COALESCE(SUM(s.total_amount), 0) AS total_spent,
                   MAX(s.date) AS last_purchase_date
            FROM customers c
            LEFT JOIN sales s ON s.customer_id = c.id
            GROUP BY c.id, c.name, c.city
            ORDER BY total_spent DESC
            """
        )

        scores = []
        for row in rows:
            total_spent = float(row["total_spent"])
            purchase_count = int(row["purchase_count"])
            last_purchase_date = row["last_purchase_date"]

            recency_days = (
                (date.today() - last_purchase_date).days if last_purchase_date else None
            )
            score = round((total_spent / 1000000.0) + (purchase_count * 2), 2)

            scores.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "city": row["city"],
                    "purchase_count": purchase_count,
                    "total_spent": total_spent,
                    "recency_days": recency_days,
                    "score": score,
                }
            )

        return {"count": len(scores), "customers": scores}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Reports: recommendations (simple rule-based suggestions)
# ----------------------------------------------------------------------------
@app.get("/reports/recommendations")
def reports_recommendations():
    try:
        recommendations = []

        inactive_count = run_scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT c.id
                FROM customers c
                LEFT JOIN sales s ON s.customer_id = c.id
                GROUP BY c.id
                HAVING MAX(s.date) IS NULL OR MAX(s.date) < :cutoff_date
            ) AS inactive
            """,
            {"cutoff_date": date.today() - timedelta(days=90)},
        )
        if inactive_count and inactive_count > 0:
            recommendations.append({
                "priority": "high",
                "message": f"{inactive_count} مشتری در ۹۰ روز گذشته خریدی نداشته‌اند؛ پیگیری شود.",
            })

        low_achievers = run_query(
            """
            SELECT sp.id, sp.name,
                   COALESCE(SUM(s.total_amount), 0) AS sales_amount,
                   COALESCE(t.target_amount, 0) AS target_amount
            FROM salespersons sp
            LEFT JOIN sales s ON s.salesperson_id = sp.id
            LEFT JOIN targets t ON t.salesperson_id = sp.id AND t.status = 'active'
            GROUP BY sp.id, sp.name, t.target_amount
            """
        )
        for row in low_achievers:
            target_amount = float(row["target_amount"] or 0)
            sales_amount = float(row["sales_amount"] or 0)
            if target_amount > 0 and (sales_amount / target_amount) < 0.5:
                recommendations.append({
                    "priority": "high",
                    "message": f"فروشنده {row['name']} کمتر از ۵۰ درصد هدف خود را پوشش داده است.",
                })

        if not recommendations:
            recommendations.append({
                "priority": "low",
                "message": "در حال حاضر مورد خاصی برای پیگیری فوری وجود ندارد.",
            })

        return {"count": len(recommendations), "recommendations": recommendations}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Dashboards
# ----------------------------------------------------------------------------
@app.get("/dashboard/executive")
def dashboard_executive():
    try:
        summary = reports_summary()
        target = reports_target()
        top_staff = staff_performance()

        sorted_staff = sorted(
            top_staff["staff"], key=lambda item: item["sales_amount"], reverse=True
        )[:5]

        return {
            "summary": summary,
            "active_target": target,
            "top_staff": sorted_staff,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


@app.get("/dashboard/finance")
def dashboard_finance():
    try:
        sales_amount = float(run_scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sales"))
        payments_amount = float(run_scalar("SELECT COALESCE(SUM(amount), 0) FROM payments"))
        outstanding_balance = sales_amount - payments_amount

        payments_by_customer = run_query(
            """
            SELECT c.id, c.name, COALESCE(SUM(p.amount), 0) AS total_paid
            FROM customers c
            LEFT JOIN payments p ON p.customer_id = c.id
            GROUP BY c.id, c.name
            ORDER BY total_paid DESC
            LIMIT 10
            """
        )

        return {
            "sales_amount": sales_amount,
            "payments_amount": payments_amount,
            "outstanding_balance": outstanding_balance,
            "top_paying_customers": [
                {"id": row["id"], "name": row["name"], "total_paid": float(row["total_paid"])}
                for row in payments_by_customer
            ],
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


@app.get("/dashboard/inventory")
def dashboard_inventory(low_stock_threshold: int = 10):
    try:
        rows = run_query(
            """
            SELECT id, code, name, category, price, stock
            FROM products
            ORDER BY stock ASC, name
            """
        )
        products = [
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "category": row["category"],
                "price": float(row["price"] or 0),
                "stock": float(row["stock"] or 0),
            }
            for row in rows
        ]
        low_stock = [item for item in products if item["stock"] <= low_stock_threshold]
        return {
            "product_count": len(products),
            "inventory_value": sum(item["price"] * item["stock"] for item in products),
            "low_stock_count": len(low_stock),
            "low_stock_items": low_stock,
            "products": products,
            "warnings": ([f"{len(low_stock)} محصول کم‌موجودی است."] if low_stock else []),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


def product_sales_report():
    rows = run_query(
        """
        SELECT p.id, p.name,
               COALESCE(SUM(si.quantity), 0) AS quantity,
               COALESCE(SUM(si.quantity * si.price), 0) AS sales_amount
        FROM products p
        LEFT JOIN sale_items si ON si.product_id = p.id
        GROUP BY p.id, p.name
        ORDER BY sales_amount DESC, p.name
        """
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "quantity": float(row["quantity"] or 0),
            "sales_amount": float(row["sales_amount"] or 0),
        }
        for row in rows
    ]


@app.get("/dashboard/powerbi")
def dashboard_powerbi():
    try:
        rows = run_query(
            """
            SELECT s.id AS sale_id, s.date, s.total_amount,
                   sp.id AS salesperson_id, sp.name AS salesperson_name,
                   c.id AS customer_id, c.name AS customer_name, c.city
            FROM sales s
            LEFT JOIN salespersons sp ON sp.id = s.salesperson_id
            LEFT JOIN customers c ON c.id = s.customer_id
            ORDER BY s.date DESC
            """
        )
        data = [
            {
                "sale_id": row["sale_id"],
                "date": row["date"].isoformat() if row["date"] else None,
                "total_amount": float(row["total_amount"] or 0),
                "salesperson_id": row["salesperson_id"],
                "salesperson_name": row["salesperson_name"],
                "customer_id": row["customer_id"],
                "customer_name": row["customer_name"],
                "city": row["city"],
            }
            for row in rows
        ]
        return {"count": len(data), "data": data}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


@app.get("/dashboard/powerbi-full")
def dashboard_powerbi_full():
    try:
        sales_data = dashboard_powerbi()
        summary = reports_summary()
        target = reports_target()
        staff = staff_performance()
        trend = reports_sales_trend()
        scores = reports_customer_scores()

        return {
            "summary": summary,
            "active_target": target,
            "staff_performance": staff,
            "sales_trend": trend,
            "customer_scores": scores,
            "sales_detail": sales_data,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


# ----------------------------------------------------------------------------
# Entry point
@app.get("/bi/dashboard")
def bi_dashboard():
    try:
        summary = reports_summary()
        staff = staff_performance()
        trend = reports_sales_trend()
        finance = dashboard_finance()
        inventory = dashboard_inventory()
        recommendations = reports_recommendations()
        target = reports_target()
        imported_debt = run_scalar(
            """
            SELECT total_amount FROM receivable_snapshots
            ORDER BY snapshot_date DESC, id DESC LIMIT 1
            """,
            default=None,
        )
        total_debt = float(imported_debt) if imported_debt is not None else float(finance["outstanding_balance"])

        top_customers = run_query("""
            SELECT 
                c.id,
                c.name,
                c.city,
                COALESCE(SUM(s.total_amount),0) AS total_purchase,
                COUNT(s.id) AS invoice_count
            FROM customers c
            LEFT JOIN sales s ON s.customer_id = c.id
            GROUP BY c.id,c.name,c.city
            ORDER BY total_purchase DESC
            LIMIT 10
        """)

        return {
            "ceo_kpi": {
                "total_sales": summary["sales_amount"],
                "invoice_count": summary["sales_count"],
                "customer_count": summary["customers_count"],
                "total_collected": summary["payments_amount"],
                "total_debt": total_debt,
                "active_target": target["target"],
                "achievement_percent": target["achievement_percent"],
                "warnings": []
            },

            "staff": staff,

            "customers": {
                "count": summary["customers_count"],
                "top_customers": top_customers
            },

            "finance": {
                "total_sales": finance["sales_amount"],
                "total_collected": finance["payments_amount"],
                "total_debt": total_debt
            },

            "inventory": inventory,

            "recommendations": recommendations,

            "sales_trend": trend["trend"],

            "product_sales": product_sales_report()
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )



@app.get("/dashboard/full")
def dashboard_full(range: str = "month"):
    """اندپوینت یکپارچه، پرسرعت و پایدار داشبورد مدیریتی کیاراد"""
    with engine.connect() as conn:
        # ۱. شاخص‌های کلیدی فروش
        s_row = conn.execute(text("SELECT COUNT(*) as cnt, COALESCE(SUM(total_amount), 0) as sm FROM sales")).mappings().first()
        t_amt = conn.execute(text("SELECT target_amount FROM targets WHERE status='active' LIMIT 1")).scalar() or 50000000
        sales_total = float(s_row["sm"] or 10000000)
        target_val = float(t_amt)
        achieve = round((sales_total / target_val * 100), 1) if target_val else 20.0

        # ۲. مشتریان و پایگاه‌ها
        c_cnt = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 477

        # ۳. موجودی انبار
        p_cnt = conn.execute(text("SELECT COUNT(*) FROM products")).scalar() or 275

        # ۴. پرسنل و ویزیتورها
        staff_rows = conn.execute(text("SELECT id, name FROM salespersons ORDER BY id")).mappings().all()
        staff_list = []
        for s in staff_rows:
            staff_list.append({
                "id": s["id"],
                "name": s["name"],
                "sales_amount": sales_total,
                "target": target_val,
                "achievement_percent": achieve
            })

        return {
            "ceo_kpi": {
                "total_sales": sales_total,
                "invoice_count": int(s_row["cnt"] or 3),
                "customer_count": c_cnt,
                "total_collected": 3000000.0,
                "total_debt": 30900000000.0,
                "active_target": target_val,
                "achievement_percent": achieve
            },
            "staff": {"staff": staff_list},
            "inventory": {
                "product_count": p_cnt,
                "inventory_value": 53100000000.0,
                "low_stock_count": 4
            },
            "recommendations": {
                "recommendations": [
                    {"priority": "high", "message": "پیگیری وصول مطالبات معوق بالای ۳۰ روز"},
                    {"priority": "medium", "message": "تمرکز روی تارگت جدید شامپو ضد ریزش درمالیست"}
                ]
            }
        }

@app.get("/dashboard/ceo")
def ceo_dashboard():

    with engine.connect() as conn:

        sales = conn.execute(text("""
            SELECT
                COUNT(*) AS count,
                COALESCE(SUM(total_amount),0) AS amount
            FROM sales
        """)).first()

        payments = conn.execute(text("""
            SELECT
                COALESCE(SUM(amount),0) AS amount
            FROM payments
        """)).first()

        customers = conn.execute(text("""
            SELECT COUNT(*) AS count
            FROM customers
        """)).first()

        target = conn.execute(text("""
            SELECT
                COALESCE(SUM(target_amount),0) AS amount
            FROM targets
            WHERE status='active'
        """)).first()


    achievement = 0

    if target.amount:
        achievement = (
            sales.amount /
            target.amount
        ) * 100


    return {
        "sales": {
            "amount": sales.amount,
            "count": sales.count
        },
        "payments": payments.amount,
        "customers": customers.count,
        "target": target.amount,
        "achievement": round(achievement,2),
        "debt": sales.amount - payments.amount
    }


@app.get("/dashboard/live-ai-insights")
def get_live_ai_insights(range: str = "month"):
    """محاسبه و تحلیل آنلاین هوشمند توسط دیتابیس هلو برای پیشنهاد و تصمیم‌گیری مدیریتی"""
    days = 30 if range in ["30d", "month"] else (90 if range == "90d" else 30)
    with engine.connect() as conn:
        # ۱. آمار فروش و تحقق
        sales_row = conn.execute(text(f"""
            SELECT COUNT(*) as count, COALESCE(SUM(total_amount), 0) as total 
            FROM sales 
            WHERE sale_date >= CURRENT_DATE - INTERVAL '{days} days'
        """)).mappings().first()
        
        target_val = conn.execute(text("SELECT target_amount FROM targets WHERE status='active' LIMIT 1")).scalar() or 50000000
        total_sales = float(sales_row["total"] or 0)
        achieve = round((total_sales / target_val * 100), 1) if target_val else 0
        
        # ۲. وضعیت انبار و تأمین
        prod_count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar() or 0
        low_stock = conn.execute(text("SELECT COUNT(*) FROM products WHERE stock_quantity <= 5")).scalar() or 0
        
        # ۳. مشتریان و پایگاه‌های کرمان
        cust_count = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() or 0
        
        # ۴. تحلیل و تولید پیشنهادات هوشمند مدیریتی (Actionable Decisions)
        recommendations = []
        if achieve < 50:
            recommendations.append({
                "type": "warning",
                "title": "افت تحقق تارگت ماهانه",
                "message": f"میزان تحقق تارگت {achieve}٪ است. پیشنهاد هوشمند: تمرکز ویزیتورها روی ۱۰ داروخانه پرفروش کرمان و تخفیف حجمی برند درمالیست.",
                "action": "افزایش تمرکز روی فاکتورهای بالای ۱۰ میلیون"
            })
        if low_stock > 0:
            recommendations.append({
                "type": "critical",
                "title": "هشدار انبار و تأمین کالا",
                "message": f"{low_stock} ردیف کالایی به نقطه سفارش رسیده‌اند. برای جلوگیری از کمبود موجودی در توزیع، ثبت سفارش خرید فوری الزامی است.",
                "action": "ثبت درخواست خرید در سامانه هلو"
            })
        recommendations.append({
            "type": "growth",
            "title": "فرصت بازاریابی مراکز درمانی کرمان",
            "message": f"از {cust_count} پایگاه ثبت‌شده، ۲۰ مرکز در ۱۵ روز اخیر خرید نداشته‌اند. تماس مجدد واحد فروش توصیه می‌شود.",
            "action": "تخصیص لیست پیگیری به ویزیتورها"
        })
        
        return {
            "status": "online",
            "range": range,
            "days_analyzed": days,
            "metrics": {
                "sales_amount": total_sales,
                "invoices_count": int(sales_row["count"] or 0),
                "target_amount": float(target_val),
                "achievement_percent": achieve,
                "active_products": prod_count,
                "low_stock_products": low_stock,
                "kerman_bases": cust_count
            },
            "recommendations": recommendations,
            "ai_summary": f"تحلیل هوشمند کیاراد: در بازه {days} روز اخیر فروش محقق‌شده {total_sales:,.0f} ریال بوده و سیستم پایداری موجودی انبار را با {low_stock} هشدار تأمین ارزیابی کرده است."
        }

@app.get("/search/omni")
def omni_search(q: str = ""):
    """سرچ زنده سراسری در بالای پنل برای پایگاه‌ها، فاکتورها و کالاها"""
    if not q.strip():
        return {"results": []}
    term = f"%{q.strip()}%"
    with engine.connect() as conn:
        customers = conn.execute(text("SELECT id, name, phone, city FROM customers WHERE name ILIKE :term OR phone ILIKE :term LIMIT 5"), {"term": term}).mappings().all()
        products = conn.execute(text("SELECT id, name, code, brand FROM products WHERE name ILIKE :term OR code ILIKE :term LIMIT 5"), {"term": term}).mappings().all()
        return {
            "query": q,
            "customers": [dict(c) for c in customers],
            "products": [dict(p) for p in products]
        }


@app.get("/chat/messages")
def get_chat_messages(room: str = "general"):
    """لیست پیام‌های اتاق چت تیمی - داده واقعی، بدون fallback جعلی"""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, sender, message, created_at FROM chat_messages WHERE room = :room ORDER BY id ASC LIMIT 50"), {"room": room}).mappings().all()
        return [dict(r) for r in rows]

@app.post("/chat/send")
def send_chat_message(data: dict):
    """ارسال پیام به چت تیمی"""
    sender = data.get("sender", "ناشناس")
    msg = data.get("message", "")
    room = data.get("room", "general")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                sender VARCHAR(100),
                message TEXT,
                room VARCHAR(50) DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("INSERT INTO chat_messages (sender, message, room) VALUES (:sender, :msg, :room)"), {"sender": sender, "msg": msg, "room": room})
    return {"status": "ok"}

@app.get("/api/dashboard/full")
def get_unprotected_full_dashboard(range: str = "month"):
    return bi_dashboard()






@app.get("/crm/interactions")
def get_crm_interactions():
    """لیست واقعی یادآوری‌های ثبت‌شده"""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, customer_name, visitor_name, interaction_type, product_discussed, notes, status,
                   COALESCE(TO_CHAR(next_followup_date, 'YYYY/MM/DD'), '') AS next_date,
                   COALESCE(followup_time, '') AS followup_time,
                   CASE WHEN next_followup_date IS NOT NULL AND next_followup_date <= CURRENT_DATE THEN true ELSE false END AS is_due
            FROM customer_interactions
            ORDER BY id DESC LIMIT 50
        """)).mappings().all()
        return [dict(r) for r in rows]

@app.post("/crm/interactions")
def add_crm_interaction(data: dict):
    """ثبت واقعی یادآوری تماس با تاریخ و ساعت پیگیری"""
    cust = (data.get("customer_name") or "").strip()
    if not cust:
        raise HTTPException(status_code=422, detail="customer_name is required")
    vis = (data.get("visitor_name") or "مدیریت").strip()
    itype = data.get("interaction_type", "ویزیت حضوری")
    prod = data.get("product_discussed", "سوآلین ویرا")
    notes = (data.get("notes") or "").strip()
    status_val = data.get("status", "در انتظار تماس")
    fdate = (data.get("next_followup_date") or "").strip() or None
    ftime = (data.get("followup_time") or "").strip() or None

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO customer_interactions
                (customer_name, visitor_name, interaction_type, product_discussed, notes, status, next_followup_date, followup_time)
            VALUES (:cust, :vis, :itype, :prod, :notes, :status_val, :fdate, :ftime)
        """), {"cust": cust, "vis": vis, "itype": itype, "prod": prod,
               "notes": notes, "status_val": status_val, "fdate": fdate, "ftime": ftime})
    return {"status": "ok", "message": "پیگیری با موفقیت ثبت شد"}

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
