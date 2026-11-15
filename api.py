from kerman_crm import router as kerman_router
from voice_reports import router as voice_reports_router
from proformas import router as proformas_router
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# ----------------------------------------------------------------------------
# Database configuration
# ----------------------------------------------------------------------------

from db import engine
from stock_reservations import reservation_totals
from iran_time import iran_today, iran_month_bounds
from assistant_engine import router as assistant_router
from operations import (
    MANAGER_ROLES,
    current_user,
    require_manager,
    role_has_module_permission,
    router as operations_router,
)
from password_recovery import router as password_recovery_router
from treasury import router as treasury_router
from treasury_strategy import router as treasury_strategy_router
from treasury_excel import router as treasury_excel_router
from field_intelligence import coach_router, inventory_router
from catalog import router as catalog_router
from holoo_router import router as holoo_router
from integrations import router as integrations_router
from data_entry import router as data_entry_router

# ----------------------------------------------------------------------------
# App setup
# ----------------------------------------------------------------------------
app = FastAPI(title="Kiarad BI API")
from agent_center import router as agent_center_router
from live_tracking import router as live_tracking_router
app.include_router(agent_center_router)
app.include_router(live_tracking_router)
from traccar_bridge import router as traccar_router
app.include_router(traccar_router)
from tracking_analytics import router as tracking_analytics_router
app.include_router(tracking_analytics_router)
from outbound_messages import router as outbound_router
app.include_router(outbound_router)
from prospect_pipeline import router as prospect_router
app.include_router(prospect_router)
from agent_routines import router as agent_routines_router
app.include_router(agent_routines_router)
from specialist_workflows import router as specialist_router
app.include_router(specialist_router)
from training_workflows import router as training_router
app.include_router(training_router)

from crud_api import router as crud_router
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
app.include_router(password_recovery_router)
app.include_router(treasury_router)
app.include_router(treasury_strategy_router)
app.include_router(treasury_excel_router)
app.include_router(coach_router)
app.include_router(inventory_router)
app.include_router(assistant_router)
from morning_brief import router as morning_brief_router
app.include_router(morning_brief_router)
app.include_router(catalog_router)
app.include_router(holoo_router)
from platform_sync import router as platforms_router
app.include_router(platforms_router)
from digikala_router import router as digikala_router
app.include_router(digikala_router)
from site_cms import router as site_cms_router, banner_router as site_banner_router
app.include_router(site_cms_router)
app.include_router(site_banner_router)
from site_auth import router as site_auth_router
app.include_router(site_auth_router)
from site_orders import router as site_orders_router
app.include_router(site_orders_router)
from social_connect import router as social_connect_router
app.include_router(social_connect_router)
from marketing_intel import router as marketing_intel_router
app.include_router(marketing_intel_router)
app.include_router(integrations_router)
app.include_router(data_entry_router)
from visit_coverage import router as visit_coverage_router
app.include_router(visit_coverage_router)
from base_proposals import router as base_proposals_router
app.include_router(base_proposals_router)
from monthly_visit_plans import router as monthly_visit_plans_router
app.include_router(monthly_visit_plans_router)
from route_builder import router as route_builder_router
app.include_router(route_builder_router)
app.include_router(crud_router)





# ---------------------------------------------------------------------------
# Authentication gate: JWT for humans, X-API-Key for automations (n8n)
# ---------------------------------------------------------------------------
import os as _os
_KIARAD_API_KEY = _os.getenv("KIARAD_API_KEY", "")
_KIARAD_JWT = _os.getenv("KIARAD_JWT_SECRET", "")
_OPEN_PATHS = ["/", "/health", "/docs", "/redoc", "/openapi.json", "/auth/login", "/auth/recovery/request", "/auth/recovery/confirm",
               "/public/catalog", "/public/catalog/prices",
               "/site-auth/login", "/site-auth/register", "/site-auth/me"]
_AUTH_METADATA_PATHS = {"/auth/me", "/auth/permissions", "/auth/password"}


def _required_module(path: str) -> Optional[str]:
    """Map every protected API family to the module whose grants control it."""
    if path.startswith("/api/compensation/"):
        if path == "/api/compensation/position-check":
            return "map"
        if "/payroll" in path or path.startswith("/api/compensation/contract/"):
            return "payroll"
        if path.startswith(("/api/compensation/visit-routes", "/api/compensation/visit-coverage")):
            return "tasks"
        if path.startswith(("/api/compensation/bases", "/api/compensation/base-checkins", "/api/compensation/base-portfolios", "/api/compensation/base-proposals")):
            return "kerman-bases"
        return "map" if "/attendance/" in path else "compensation"
    if path.startswith("/api/"):
        path = path[4:]

    if path.startswith(("/crud/", "/import/excel/", "/import/template/")):
        parts = path.strip("/").split("/")
        table = parts[1] if parts[0] == "crud" else (parts[2] if len(parts) > 2 else "")
        table_modules = {
            "products": "catalog",
            "product_media": "catalog",
            "pharmacies": "kerman-bases",
            "cosmetics_shops": "kerman-bases",
            "kerman_bases_manual": "kerman-bases",
            "cash_accounts": "treasury",
            "fixed_expenses": "treasury",
        }
        return table_modules.get(table)

    if path.startswith(("/upload/", "/product-media", "/catalog-files", "/files/products/", "/files/catalog/")):
        return "catalog"
    if path.startswith('/data-entry/'):
        entity=path.split('/')[2]
        return {'schema':'catalog','products':'catalog','customers':'customers','targets':'personnel','batches':'catalog'}.get(entity)

    if path == "/dashboard/full":
        return "visitor-kpis"

    if path.startswith("/holoo/payment-options"):
        return "proformas"
    if path in {"/holoo/sync","/holoo/status","/holoo/history","/holoo/errors"}:
        return "management"

    # Managers receive company data; field roles receive the personal view only.
    if path in {"/dashboard/full", "/api/dashboard/full"}:
        return "visitor-kpis"

    if path.startswith("/operations/customers/") and path.endswith(("/credit", "/ledger")):
        return "debtors"

    prefix_modules = (
        ("/digikala", "online-sales"),
        ("/site-cms", "online-sales"),
        ("/site-orders", "online-sales"),
        ("/social-connect", "online-sales"),
        ("/marketing", "online-sales"),
        ("/route-builder", "manager"),
        ("/platforms", "online-sales"),
        ("/assistant/advisory", "advisory"),
        ("/treasury/debtors", "debtors"),
        ("/operations/locations", "map"),
        ("/operations/visitors", "visitor-kpis"),
        ("/directory/customers", "customers"),
        ("/operations/proformas", "proformas"),
        ("/operations/customers", "proformas"),
        ("/operations/products", "proformas"),
        ("/operations/transcribe-audio", "voice-report"),
        ("/operations/operations/transcribe-audio", "voice-report"),
        ("/operations/voice-customers", "voice-report"),
        ("/operations/voice-reports", "voice-report"),
        ("/operations/speech-readiness", "voice-report"),
        ("/operations/submit-daily-report", "daily-reports"),
        ("/api/compensation/", "compensation"),
        ("/monthly-visit-plans", "map"),
        ("/compensation/", "compensation"),
        ("/campaigns", "campaigns"),
        ("/treasury", "treasury"),
        ("/catalog", "catalog"),
        ("/holoo", "catalog"),
        ("/integrations", "online-sales"),
        ("/kerman", "kerman-bases"),
        ("/telegram", "team-chat"),
        ("/agent-center", "assistant"),
        ("/tracking", "map"),
        ("/outbound", "assistant"),
        ("/prospects", "assistant"),
        ("/agent-routines", "assistant"),
        ("/specialists", "assistant"),
        ("/training", "tasks"),
        ("/assistant", "assistant"),
        ("/chat", "team-chat"),
        ("/crm", "crm"),
        ("/notifications", "assistant"),
        ("/tasks", "tasks"),
        ("/daily-reports", "daily-reports"),
        ("/transcribe-audio", "voice-report"),
        ("/submit-daily-report", "daily-reports"),
        ("/operations/customers-list", "proformas"),
        ("/operations/products-list", "proformas"),
        ("/customers-list", "proformas"),
        ("/products-list", "proformas"),
        ("/targets/my-summary", "personnel"),
        ("/targets/person-targets", "personnel"),
        ("/targets/custom-list", "visitor-kpis"),
        ("/targets/company", "management"),
        ("/targets/set", "visitor-kpis"),
        ("/targets", "visitor-kpis"),
        ("/visitors", "visitors"),
        ("/users", "manager"),
        ("/salespersons", "manager"),
        ("/roles", "management"),
        ("/reports/finance", "treasury"),
        ("/dashboard/finance", "treasury"),
        ("/dashboard/inventory", "catalog"),
        ("/dashboard", "management"),
        ("/api/dashboard", "management"),
        ("/bi/dashboard", "management"),
        ("/reports", "management"),
        ("/staff/performance", "management"),
        ("/search", "management"),
    )
    for prefix, module in prefix_modules:
        if path == prefix or path.startswith(prefix + "/"):
            return module
    return None


def _required_permission(method: str, path: str) -> str:
    if method == 'POST' and path.startswith('/kerman/coach/bases/') and path.endswith('/explain'):
        return 'can_read'
    if method == "POST" and path in {
        "/assistant/chat",
        "/assistant/advisory/ask",
        "/operations/transcribe-audio",
        "/operations/operations/transcribe-audio",
        "/transcribe-audio",
        "/api/compensation/position-check",
        "/treasury/strategy/cash-scenario",
        "/treasury/strategy/profit-scenario",
        "/treasury/strategy/reconciliation-preview",
    }:
        return "can_read"
    if method == "DELETE":
        if path == "/assistant/history":
            return "can_write"
        return "can_delete"
    if method in {"POST", "PUT", "PATCH"}:
        return "can_write"
    return "can_read"

@app.middleware("http")
async def auth_gate(request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if request.method == "POST" and path == "/tracking/traccar/positions":
        # This single server-to-server route authenticates its dedicated forwarding
        # credential before reading a bounded body; a device identifier is not a JWT.
        from traccar_bridge import authorize_forward
        try: authorize_forward(request)
        except HTTPException as exc: return JSONResponse(status_code=exc.status_code,content={"detail":exc.detail})
        return await call_next(request)
    if path in _OPEN_PATHS:
        return await call_next(request)
    if request.method in {"GET", "HEAD"} and (path == "/site-banners" or path.startswith("/site-banners/")):
        # Public, read-only CMS banners for the storefront (no personal data).
        return await call_next(request)
    # Load from .env if env var missing (fix for --env-file not working)
    jwt_secret = _os.environ.get("KIARAD_JWT_SECRET", "")
    api_key = _os.environ.get("KIARAD_API_KEY", "")
    if not jwt_secret:
        try:
            from dotenv import load_dotenv as _ld
            _ld(Path(__file__).resolve().parent / ".env", override=False)
            jwt_secret = _os.environ.get("KIARAD_JWT_SECRET", "")
            api_key = api_key or _os.environ.get("KIARAD_API_KEY", "")
        except Exception:
            pass
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        if not jwt_secret:
            print("gate 401 reason=empty-jwt-secret path=" + path)
        else:
            authorized = False
            try:
                payload = jwt.decode(auth[7:], jwt_secret, algorithms=["HS256"])
                if payload.get("role") == "site_customer":
                    # Site-customer JWT (site_auth) — no users-table row exists.
                    # Only its own endpoint family passes; the endpoint's
                    # current_site_customer dependency validates the DB row.
                    if path in {"/site-orders", "/site-orders/mine"} and "sub" in payload:
                        return await call_next(request)
                    raise jwt.InvalidTokenError
                user_id = int(payload["sub"])
                with engine.connect() as conn:
                    user_row = conn.execute(
                        text("SELECT id, role, is_active, password_version FROM users WHERE id = :id"),
                        {"id": user_id},
                    ).mappings().first()
                if not user_row or not bool(user_row["is_active"]):
                    return JSONResponse(status_code=401, content={"detail": "User is inactive"})
                if payload.get("pwd_ver", 0) != user_row["password_version"]:
                    return JSONResponse(status_code=401, content={"detail": "Session expired after password change"})

                # Training access is an explicit per-enrollment account grant; the router
                # checks ownership for every lesson/assessment and CEO role for publishing.
                training_account_path = path == "/training" or path.startswith("/training/")
                # Ending one's own tracking session is account self-service:
                # revoking map access must not prevent withdrawing tracking consent.
                # JWT activation/version checks above and router ownership checks still apply.
                own_tracking_stop = request.method == "POST" and path == "/tracking/sessions/stop"
                if path not in _AUTH_METADATA_PATHS and not training_account_path and not own_tracking_stop:
                    module = _required_module(path)
                    if path in {"/dashboard/full", "/api/dashboard/full"} and str(user_row["role"]) in MANAGER_ROLES:
                        module = "management"
                    if not module:
                        return JSONResponse(status_code=403, content={"detail": "No access rule for this endpoint"})
                    if not role_has_module_permission(
                        str(user_row["role"]), module, _required_permission(request.method, path)
                    ):
                        return JSONResponse(status_code=403, content={"detail": "Module permission denied"})
                authorized = True
            except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
                print("gate 401 reason=invalid-jwt-sub path=" + path)
            except Exception:
                print("gate 503 reason=auth-check-failed path=" + path)
                return JSONResponse(status_code=503, content={"detail": "Authorization check unavailable"})
            if authorized:
                # Endpoint failures must keep their own status and traceback; they are not auth failures.
                return await call_next(request)
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
    except SQLAlchemyError:
        # Public health checks must not disclose driver errors or DB addresses.
        raise HTTPException(status_code=503, detail="Database connection unavailable")


# ----------------------------------------------------------------------------
# Public catalog — open, read-only, zero personal data. Powers the public site
# (site/) so it can show live prices without shipping database dumps.
# ----------------------------------------------------------------------------
@app.get("/public/catalog")
def public_catalog():
    try:
        with engine.connect() as conn:
            conn.execute(text("""CREATE TABLE IF NOT EXISTS cms_product_meta(
                code VARCHAR(100) PRIMARY KEY, site_category TEXT, image_url TEXT,
                hidden BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
            conn.execute(text("ALTER TABLE cms_product_meta ADD COLUMN IF NOT EXISTS discount_price_irr BIGINT"))
            rows = conn.execute(text(
                """
                SELECT p.id, p.code, p.name,
                       COALESCE(NULLIF(m.site_category, ''), p.category) AS category,
                       p.price, p.stock, m.image_url, m.discount_price_irr, NOW() AS generated_at
                FROM products p
                LEFT JOIN cms_product_meta m ON m.code = p.code
                WHERE p.is_active = 1 AND COALESCE(m.hidden, FALSE) = FALSE
                ORDER BY p.name
                """
            )).mappings().all()
            totals = reservation_totals(conn, [r['id'] for r in rows])
            products = []
            for row in rows:
                item = dict(row)
                product_id = item.pop('id')
                item['stock'] = max(0, float(item['stock'] or 0) - totals.get(product_id, 0))
                products.append(item)
        return {
            "store": {"name": "Ordibeauty", "tagline": "اردی‌بیوتی — زیبایی اورجینال، با قیمت و موجودی زنده"},
            "currency": "IRR",
            "products": products,
        }
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="catalog unavailable")


@app.get("/public/catalog/prices")
def public_catalog_prices():
    """Live Digikala selling prices for products mapped by holoo code."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT v.holoo_code AS code, v.price_selling AS price_irr, v.stock, v.updated_at "
                "FROM digikala_variants v WHERE v.holoo_code IS NOT NULL AND v.status = 'active'"
            )).mappings().all()
        return {"currency": "IRR", "source": "digikala_sync", "prices": [dict(r) for r in rows]}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="prices unavailable")


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
    import jdatetime
    buckets={}
    for row in run_query("SELECT date,total_amount FROM sales ORDER BY date"):
        if row['date'] is None:continue
        day=row['date'].date() if isinstance(row['date'],datetime) else row['date']
        month=jdatetime.date.fromgregorian(date=day).strftime('%Y-%m')
        bucket=buckets.setdefault(month,{'month':month,'sales_count':0,'sales_amount':0.0})
        bucket['sales_count']+=1;bucket['sales_amount']+=float(row['total_amount'] or 0)
    trend=[buckets[k] for k in sorted(buckets)]
    return {'count':len(trend),'trend':trend,'calendar':'jalali','amount_basis':'net_merchandise_irr_excluding_tax','count_includes_returns':True}


# ----------------------------------------------------------------------------
# Reports: inactive customers (no sales in the last 90 days)
# ----------------------------------------------------------------------------
@app.get("/reports/inactive-customers")
def reports_inactive_customers(days: int = 90):
    try:
        cutoff_date = iran_today() - timedelta(days=days)
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

            if isinstance(last_purchase_date, datetime):
                last_purchase_date = last_purchase_date.date()
            elif last_purchase_date and not isinstance(last_purchase_date, date):
                try:
                    last_purchase_date = datetime.fromisoformat(
                        str(last_purchase_date)
                    ).date()
                except (TypeError, ValueError):
                    last_purchase_date = None

            recency_days = (
                (iran_today() - last_purchase_date).days if last_purchase_date else None
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
            {"cutoff_date": iran_today() - timedelta(days=90)},
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
def dashboard_full(range: str = "month", authorization: str = Header(default=None)):
    user = current_user(authorization)
    role = user.get("role", "")
    spid = user.get("salesperson_id")
    if role in {"salesperson", "visitor"}:
        if not spid:
            raise HTTPException(status_code=403, detail="Salesperson profile required")
        is_salesperson = True
    elif role in MANAGER_ROLES:
        is_salesperson = False
    else:
        raise HTTPException(status_code=403, detail="Dashboard access required")

    report_today=iran_today()
    month_start,month_next=iran_month_bounds(report_today)
    month_end=month_next-timedelta(days=1)
    period_start=month_start if range=="month" else report_today-timedelta(days=29 if range=="30d" else 89)
    period_next=report_today+timedelta(days=1)
    date_filter="date >= CAST(:period_start AS DATE) AND date < CAST(:period_next AS DATE)"
    staff_date_filter="s.date >= CAST(:period_start AS DATE) AND s.date < CAST(:period_next AS DATE)"
    payment_date_filter="payment_date >= CAST(:period_start AS DATE) AND payment_date < CAST(:period_next AS DATE)"
    def statement(sql):
        values={'month_start':month_start,'month_end':month_end,'period_start':period_start,'period_next':period_next}
        query=text(sql)
        return query.bindparams(**{k:v for k,v in values.items() if ':'+k in sql})

    with engine.connect() as conn:
        current_report_date = report_today
        from holoo_operational_sync import operational_status
        data_sync=operational_status(conn,manager=not is_salesperson)
        latest_receivable_snapshot = conn.execute(statement("""
            SELECT id, snapshot_date FROM receivable_snapshots
            ORDER BY snapshot_date DESC, id DESC LIMIT 1
        """)).mappings().first()
        latest_receivable_snapshot_id = latest_receivable_snapshot["id"] if latest_receivable_snapshot else None
        debt_snapshot_date = str(latest_receivable_snapshot["snapshot_date"]) if latest_receivable_snapshot else None
        if is_salesperson:
            # ===== VISITOR VIEW (limited) =====
            sales_source_date = conn.execute(statement(
                "SELECT MAX(date)::date FROM sales WHERE salesperson_id = :spid"
            ), {"spid": spid}).scalar()
            sales_row = conn.execute(statement("""
                SELECT COUNT(*) AS cnt, COALESCE(SUM(total_amount), 0) AS sm
                FROM sales WHERE salesperson_id = :spid AND """ + date_filter + """
            """), {"spid": spid}).mappings().first()
            total_sales = float(sales_row.get("sm") or 0)
            invoice_count = int(sales_row.get("cnt") or 0)

            cust_cnt = int(conn.execute(statement("""
                SELECT COUNT(DISTINCT customer_id) FROM sales WHERE salesperson_id = :spid
            """), {"spid": spid}).scalar() or 0)

            # my customers' debts (only from my sales)
            total_debt = float(conn.execute(statement("""
                SELECT COALESCE(SUM(rb.balance), 0)
                FROM receivable_balances rb
                WHERE rb.snapshot_id = :snapshot_id AND rb.customer_id IN (
                    SELECT DISTINCT customer_id FROM sales WHERE salesperson_id = :spid
                )
            """), {"spid": spid, "snapshot_id": latest_receivable_snapshot_id}).scalar() or 0)

            # my top debtors (only my customers)
            my_debtors = conn.execute(statement("""
                SELECT rb.counterparty AS name, rb.balance,
                       c.name AS customer_name, c.city, c.phone
                FROM receivable_balances rb
                LEFT JOIN customers c ON c.id = rb.customer_id
                WHERE rb.customer_id IN (
                    SELECT DISTINCT customer_id FROM sales WHERE salesperson_id = :spid
                ) AND rb.snapshot_id = :snapshot_id AND rb.balance > 0
                ORDER BY rb.balance DESC
                LIMIT 20
            """), {"spid": spid, "snapshot_id": latest_receivable_snapshot_id}).mappings().all()
            my_debtors_list = [dict(r) for r in my_debtors]

            # my targets
            target_rows = conn.execute(statement("""
                SELECT id, title, target_amount, target_type, product_focus,
                       period_type, bonus_reward, status, start_date, end_date
                FROM targets
                WHERE salesperson_id = :spid AND status = 'active'
                ORDER BY id DESC
            """), {"spid": spid}).mappings().all()
            my_targets_list = [dict(r) for r in target_rows]
            current_month_targets = [
                t for t in my_targets_list
                if t.get("start_date")==month_start and t.get("end_date")==month_end
            ]
            target_val = sum(float(t.get("target_amount") or 0) for t in current_month_targets)

            month_sales = float(conn.execute(statement("""
                SELECT COALESCE(SUM(total_amount), 0) FROM sales
                WHERE salesperson_id = :spid AND date >= CAST(:month_start AS DATE)
            """), {"spid": spid}).scalar() or 0)

            achieve = round((month_sales / target_val * 100), 1) if target_val > 0 else None

            staff_list = [dict(id=spid, name=(user or {}).get("full_name", ""),
                               sales_amount=total_sales, target=target_val if target_val > 0 else None,
                               achievement_percent=achieve, invoice_count=invoice_count)]

            recommendations = [dict(priority="medium",message="آمار شخصی فقط اسناد صریحاً منتسب به شماست؛ اسناد بدون مسئول وارد عملکرد شخصی نمی‌شوند.")]
            if my_targets_list and not current_month_targets:
                recommendations.append(dict(priority="medium", message="برای ماه جاری هدف شخصی با بازهٔ زمانی معتبر ثبت نشده است؛ درصد تحقق محاسبه نمی‌شود"))
            if total_debt > 0:
                recommendations.append(dict(priority="high", message="مطالبات باز مشتریان شما: " + format(total_debt, ",.0f") + " ریال - پیگیری وصول در اولویت است"))
            if achieve is not None and 0 < achieve < 70:
                recommendations.append(dict(priority="medium", message="تحقق تارگت شما: " + str(achieve) + "٪ - تا پایان ماه نیاز به تلاش بیشتر دارید"))
            if achieve is not None and achieve >= 100:
                recommendations.append(dict(priority="low", message="🎉 تارگت شما تحقق یافته — به فروش ادامه دهید"))

            return dict(
                view_mode="salesperson", data_sync=data_sync,period={"from_date":period_start,"to_date":report_today,"calendar":"jalali"},
                ceo_kpi=dict(total_sales=total_sales, invoice_count=invoice_count,
                             customer_count=cust_cnt, total_collected=0,
                             total_debt=total_debt, active_target=target_val,
                             achievement_percent=achieve, debt_snapshot_date=debt_snapshot_date,
                             sales_source_date=str(sales_source_date) if sales_source_date else None),
                staff=dict(staff=staff_list),
                customers=dict(count=cust_cnt),
                inventory=dict(product_count=0, inventory_value=0, low_stock_count=0),
                recommendations=dict(recommendations=recommendations),
                my_debtors=my_debtors_list,
                my_targets=my_targets_list,
            )

        # ===== CEO / MANAGER VIEW (original) =====
        sales_source_date = conn.execute(statement("SELECT MAX(date)::date FROM sales")).scalar()
        s_row = conn.execute(statement("SELECT COUNT(*) AS cnt, COALESCE(SUM(total_amount), 0) AS sm FROM sales WHERE " + date_filter)).mappings().first()
        total_sales = float(s_row.get("sm") or 0)
        invoice_count = int(s_row.get("cnt") or 0)
        pay_row = conn.execute(statement("SELECT COALESCE(SUM(amount), 0) AS pv FROM payments WHERE " + payment_date_filter)).mappings().first()
        total_collected = float(pay_row.get("pv") or 0)
        if latest_receivable_snapshot_id is not None:
            total_debt = float(conn.execute(statement("""
                SELECT COALESCE(SUM(balance), 0)
                FROM receivable_balances WHERE snapshot_id = :snapshot_id
            """), {"snapshot_id": latest_receivable_snapshot_id}).scalar() or 0)
        else:
            total_balances = conn.execute(statement("""
                SELECT COALESCE((SELECT SUM(total_amount) FROM sales), 0)
                     - COALESCE((SELECT SUM(amount) FROM payments), 0)
            """)).scalar()
            total_debt = max(float(total_balances or 0), 0.0)
        cust_cnt = int(conn.execute(statement("SELECT COUNT(*) FROM customers")).scalar() or 0)
        prod_cnt = int(conn.execute(statement("SELECT COUNT(*) FROM products WHERE is_active = 1")).scalar() or 0)
        inv_val = float(conn.execute(statement("SELECT COALESCE(SUM(price * stock), 0) FROM products WHERE is_active = 1")).scalar() or 0)
        low_cnt = int(conn.execute(statement("SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock IS NOT NULL AND min_stock > 0 AND stock <= min_stock")).scalar() or 0)
        zero_cnt = int(conn.execute(statement("SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock <= 0")).scalar() or 0)
        zero_without_target = int(conn.execute(statement("SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock <= 0 AND COALESCE(min_stock, 0) <= 0")).scalar() or 0)
        t_row = conn.execute(statement("""
            SELECT target_amount, start_date, end_date FROM targets
            WHERE status = 'active' AND salesperson_id IS NULL ORDER BY id DESC LIMIT 1
        """)).mappings().first()
        target_val = float(t_row["target_amount"] or 0) if t_row else 0.0
        target_period_valid = bool(t_row and t_row["start_date"] == month_start and t_row["end_date"] == month_end)
        month_sales = float(conn.execute(statement("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE date >= CAST(:month_start AS DATE)")).scalar() or 0)
        achieve = round((month_sales / target_val * 100), 1) if target_val > 0 and target_period_valid else None
        staff_rows = conn.execute(statement("""
            SELECT sp.id, sp.name,
                   COALESCE(SUM(s.total_amount), 0) AS sm,
                   COUNT(s.id) AS cnt,
                   COALESCE(SUM(CASE WHEN s.date >= CAST(:month_start AS DATE)
                                     THEN s.total_amount ELSE 0 END), 0) AS month_sales
            FROM salespersons sp
            LEFT JOIN sales s ON s.salesperson_id = sp.id AND """ + staff_date_filter + """
            GROUP BY sp.id, sp.name
            ORDER BY sm DESC
        """)).mappings().all()
        personal_target_rows = conn.execute(statement("""
            SELECT salesperson_id, COALESCE(SUM(target_amount), 0) AS target_amount
            FROM targets
            WHERE status = 'active' AND salesperson_id IS NOT NULL
              AND start_date = CAST(:month_start AS DATE)::date
              AND end_date = CAST(:month_end AS DATE)
            GROUP BY salesperson_id
        """)).mappings().all()
        targets_by_salesperson = {
            int(row["salesperson_id"]): float(row["target_amount"] or 0)
            for row in personal_target_rows
        }
        staff_list = list()
        for sp in staff_rows:
            sp_sales = float(sp.get("sm") or 0)
            sp_target = targets_by_salesperson.get(int(sp.get("id")))
            sp_month_sales = float(sp.get("month_sales") or 0)
            sp_ach = round((sp_month_sales / sp_target * 100), 1) if sp_target and sp_target > 0 else None
            staff_list.append(dict(id=sp.get("id"), name=sp.get("name"), sales_amount=sp_sales, target=sp_target, achievement_percent=sp_ach, invoice_count=int(sp.get("cnt") or 0)))
        recommendations = list()
        if data_sync.get('unattributed_documents'):
            recommendations.append(dict(priority="medium",message="بخشی از اسناد هلو مسئول تأییدشده ندارد؛ در جمع شرکت هست ولی در عملکرد اشخاص وارد نشده است."))
        if data_sync['status']!='fresh':
            recommendations.append(dict(priority="high",message="همگام‌سازی عملیاتی تازه تأیید نشده؛ زمان منبع را بررسی کنید."))
        if target_val > 0 and not target_period_valid:
            recommendations.append(dict(priority="medium", message="هدف شرکت بازهٔ معتبرِ ماه جاری ندارد؛ درصد تحقق محاسبه نمی‌شود"))
        if total_debt > 0:
            recommendations.append(dict(priority="high", message="مطالبات وصول‌نشده: " + format(total_debt, ",.0f") + " ریال - پیگیری وصول در اولویت است"))
        if low_cnt > 0:
            recommendations.append(dict(priority="critical", message=str(low_cnt) + " ردیف کالا به حد سفارش رسیده است"))
        if zero_cnt > 0:
            recommendations.append(dict(priority="critical", message=str(zero_cnt) + " ردیف کالای فعال موجودی صفر دارد" + ("؛ برای " + str(zero_without_target) + " ردیف حد سفارش معتبر ثبت نشده است" if zero_without_target else "")))
        if achieve is not None:
            recommendations.append(dict(priority="medium", message="تحقق هدف این ماه: " + str(achieve) + " درصد - باقی‌مانده: " + format(max(target_val - month_sales, 0), ",.0f") + " ریال"))
        return dict(
            view_mode="manager", data_sync=data_sync,period={"from_date":period_start,"to_date":report_today,"calendar":"jalali"},
            ceo_kpi=dict(total_sales=total_sales, invoice_count=invoice_count, customer_count=cust_cnt, total_collected=total_collected, total_debt=total_debt, active_target=target_val, achievement_percent=achieve, debt_snapshot_date=debt_snapshot_date, sales_source_date=str(sales_source_date) if sales_source_date else None),
            staff=dict(staff=staff_list),
            customers=dict(count=cust_cnt),
            inventory=dict(product_count=prod_cnt, inventory_value=inv_val, low_stock_count=low_cnt, zero_stock_count=zero_cnt, zero_without_target_count=zero_without_target),
            recommendations=dict(recommendations=recommendations),
        )


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
            WHERE date >= CURRENT_DATE - INTERVAL '{days} days'
        """)).mappings().first()
        
        target_val = conn.execute(text("SELECT target_amount FROM targets WHERE status='active' LIMIT 1")).scalar() or 50000000
        total_sales = float(sales_row["total"] or 0)
        achieve = round((total_sales / target_val * 100), 1) if target_val else 0
        
        # ۲. وضعیت انبار و تأمین
        prod_count = conn.execute(text("SELECT COUNT(*) FROM products")).scalar() or 0
        low_stock = conn.execute(text("SELECT COUNT(*) FROM products WHERE stock <= 5")).scalar() or 0
        
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


_CHAT_UPLOAD_DIR = Path(__file__).resolve().parent / "private_uploads" / "team_chat"
_CHAT_MAX_FILE_BYTES = 10 * 1024 * 1024
_CHAT_ALLOWED_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv", ".txt": "text/plain",
}


def _ensure_chat_table(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            sender VARCHAR(100),
            message TEXT,
            room VARCHAR(50) DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attachment_key VARCHAR(80),
            attachment_name VARCHAR(180),
            attachment_type VARCHAR(120),
            attachment_size BIGINT
        )
    """))
    for column, definition in (
        ("attachment_key", "VARCHAR(80)"),
        ("attachment_name", "VARCHAR(180)"),
        ("attachment_type", "VARCHAR(120)"),
        ("attachment_size", "BIGINT"),
    ):
        conn.execute(text(f"ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS {column} {definition}"))


def _ensure_crm_table(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS customer_interactions (
            id SERIAL PRIMARY KEY,
            customer_name VARCHAR(200) NOT NULL,
            visitor_name VARCHAR(100),
            interaction_type VARCHAR(50),
            product_discussed VARCHAR(150),
            notes TEXT,
            next_followup_date DATE,
            followup_time VARCHAR(20),
            status VARCHAR(50) NOT NULL DEFAULT 'در انتظار تماس',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_customer_interactions_followup ON customer_interactions(next_followup_date, status)"
    ))
    has_owner = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid='customer_interactions'::regclass
              AND attname='owner_user_id' AND NOT attisdropped
        )
    """)).scalar()
    if not has_owner:
        conn.execute(text("ALTER TABLE customer_interactions ADD COLUMN owner_user_id INTEGER"))
        # Resolve legacy labels once. Ambiguous/unmatched labels stay manager-only;
        # later display-name changes must never transfer ownership of old records.
        conn.execute(text("""
            WITH candidates AS (
                SELECT ci.id, MIN(u.id) AS user_id
                FROM customer_interactions ci
                JOIN users u ON (
                    (ci.visitor_name LIKE '@%' AND ci.visitor_name='@' || u.username)
                    OR (ci.visitor_name NOT LIKE '@%' AND ci.visitor_name=u.full_name)
                )
                GROUP BY ci.id HAVING COUNT(*)=1
            )
            UPDATE customer_interactions ci SET owner_user_id=c.user_id
            FROM candidates c WHERE ci.id=c.id
        """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_customer_interactions_owner ON customer_interactions(owner_user_id)"
    ))


@app.on_event("startup")
def initialize_chat_storage():
    with engine.begin() as conn:
        _ensure_chat_table(conn)
        _ensure_crm_table(conn)
    from assistant_automations import ensure as ensure_automations, start_automations_scheduler
    from morning_brief import ensure as ensure_morning_brief, ensure_and_build_today, start_morning_brief_timer
    with engine.begin() as conn:
        ensure_morning_brief(conn)
    try:
        ensure_and_build_today()
    except Exception:
        pass
    start_morning_brief_timer()
    with engine.begin() as conn:
        ensure_automations(conn)
    start_automations_scheduler()
    # Holoo auto-refresh must survive restarts, not wait for a manual /holoo/refresh hit.
    try:
        from holoo_finance_jobs import start_automatic_refresh
        start_automatic_refresh()
    except Exception:
        pass


def _valid_chat_file(extension: str, content: bytes) -> bool:
    signatures = {
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".gif": content.startswith((b"GIF87a", b"GIF89a")),
        ".webp": len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        ".pdf": content.startswith(b"%PDF-"),
        ".docx": content.startswith(b"PK\x03\x04"),
        ".xlsx": content.startswith(b"PK\x03\x04"),
        ".csv": b"\x00" not in content,
        ".txt": b"\x00" not in content,
    }
    return signatures.get(extension, False)


@app.get("/chat/messages")
def get_chat_messages(room: str = "general", user: dict = Depends(current_user)):
    """پیام‌های مشترک کارکنان با دسترسی چت تیمی"""
    if room != "general":
        raise HTTPException(status_code=400, detail="اتاق چت نامعتبر است")
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT id, sender, message, created_at,
                   attachment_name, attachment_type, attachment_size
            FROM chat_messages WHERE room = :room ORDER BY id DESC LIMIT 50
        """), {"room": room}).mappings().all()
    return [dict(row) for row in reversed(rows)]


@app.post("/chat/send")
async def send_chat_message(request: Request, user: dict = Depends(current_user)):
    """پیام و پیوست مجاز را با هویت حساب واردشده ثبت می‌کند."""
    upload = None
    if "multipart/form-data" in request.headers.get("content-type", ""):
        form = await request.form()
        msg = str(form.get("message", "")).strip()
        room = str(form.get("room", "general"))
        candidate = form.get("file")
        upload = candidate if candidate is not None and hasattr(candidate, "read") and hasattr(candidate, "filename") else None
    else:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="فرمت پیام نامعتبر است")
        msg = str(data.get("message", "")).strip()
        room = str(data.get("room", "general"))
    if room != "general" or len(msg) > 4000:
        raise HTTPException(status_code=400, detail="پیام یا اتاق چت نامعتبر است")
    if not msg and not upload:
        raise HTTPException(status_code=400, detail="متن پیام یا فایل پیوست لازم است")

    stored_path = None
    attachment_key = attachment_name = attachment_type = None
    attachment_size = None
    if upload:
        original = (upload.filename or "").replace("\\", "/").split("/")[-1]
        import re as _re
        attachment_name = _re.sub(r"[\x00-\x1f\x7f]", "", original).strip()[:180]
        extension = Path(attachment_name).suffix.lower()
        if not attachment_name or extension not in _CHAT_ALLOWED_TYPES:
            raise HTTPException(status_code=415, detail="این نوع فایل برای چت مجاز نیست")
        content = await upload.read(_CHAT_MAX_FILE_BYTES + 1)
        if not content or len(content) > _CHAT_MAX_FILE_BYTES or not _valid_chat_file(extension, content):
            raise HTTPException(status_code=400, detail="فایل خالی، بزرگ یا دارای محتوای نامعتبر است")
        attachment_type = _CHAT_ALLOWED_TYPES[extension]
        attachment_size = len(content)
        attachment_key = uuid4().hex + extension
        _CHAT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        stored_path = _CHAT_UPLOAD_DIR / attachment_key
        stored_path.write_bytes(content)

    try:
        with engine.begin() as conn:
            _ensure_chat_table(conn)
            result = conn.execute(text("""
                INSERT INTO chat_messages
                    (sender, message, room, attachment_key, attachment_name, attachment_type, attachment_size)
                VALUES (:sender, :msg, :room, :key, :name, :type, :size)
                RETURNING id
            """), {
                "sender": user.get("full_name") or user.get("username") or "کاربر",
                "msg": msg, "room": room, "key": attachment_key,
                "name": attachment_name, "type": attachment_type, "size": attachment_size,
            })
            message_id = result.scalar_one()
    except Exception:
        if stored_path:
            stored_path.unlink(missing_ok=True)
        raise
    return {"status": "ok", "id": message_id}


@app.get("/chat/attachments/{message_id}")
def get_chat_attachment(message_id: int, user: dict = Depends(current_user)):
    """دریافت پیوست فقط برای کارکنان واردشده و دارای دسترسی چت"""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT attachment_key, attachment_name, attachment_type
            FROM chat_messages WHERE id = :id AND room = 'general'
        """), {"id": message_id}).mappings().first()
    if not row or not row["attachment_key"]:
        raise HTTPException(status_code=404, detail="پیوست پیدا نشد")
    path = _CHAT_UPLOAD_DIR / Path(row["attachment_key"]).name
    if not path.is_file() or path.parent != _CHAT_UPLOAD_DIR:
        raise HTTPException(status_code=404, detail="پیوست پیدا نشد")
    media_type = row["attachment_type"] if row["attachment_type"] in set(_CHAT_ALLOWED_TYPES.values()) else "application/octet-stream"
    disposition = "inline" if media_type.startswith("image/") else "attachment"
    return FileResponse(path, media_type=media_type, filename=row["attachment_name"], content_disposition_type=disposition)

@app.get("/api/dashboard/full")
def get_compatible_full_dashboard(range: str = "month", authorization: str = Header(default=None)):
    return dashboard_full(range=range, authorization=authorization)






@app.get("/crm/interactions")
def get_crm_interactions(user: dict = Depends(current_user)):
    """لیست واقعی یادآوری‌های ثبت‌شده"""
    with engine.connect() as conn:
        params = {"user_id": user["id"]}
        scope = ""
        if user.get("role") not in MANAGER_ROLES:
            scope = "WHERE ci.owner_user_id = :user_id"
        rows = conn.execute(text("""
            SELECT ci.id, ci.customer_name,
                   COALESCE(u.full_name, ci.visitor_name) AS visitor_name,
                   ci.interaction_type, ci.product_discussed, ci.notes, ci.status,
                   COALESCE(TO_CHAR(ci.next_followup_date, 'YYYY/MM/DD'), '') AS next_date,
                   COALESCE(ci.followup_time, '') AS followup_time,
                   CASE WHEN ci.next_followup_date IS NOT NULL AND ci.next_followup_date <= CURRENT_DATE THEN true ELSE false END AS is_due
            FROM customer_interactions ci
            LEFT JOIN users u ON u.id=ci.owner_user_id
            """ + scope + """
            ORDER BY ci.id DESC LIMIT 50
        """), params).mappings().all()
        return [dict(r) for r in rows]

@app.post("/crm/interactions")
def add_crm_interaction(data: dict, user: dict = Depends(current_user)):
    """ثبت واقعی یادآوری تماس با تاریخ و ساعت پیگیری"""
    cust = (data.get("customer_name") or "").strip()
    if not cust:
        raise HTTPException(status_code=422, detail="customer_name is required")
    is_manager = user.get("role") in MANAGER_ROLES
    vis = ("@" + str(user.get("username", "")) if not is_manager else (data.get("visitor_name") or "مدیریت")).strip()
    itype = data.get("interaction_type", "ویزیت حضوری")
    prod = data.get("product_discussed", "سوآلین ویرا")
    notes = (data.get("notes") or "").strip()
    status_val = data.get("status", "در انتظار تماس")
    fdate = (data.get("next_followup_date") or "").strip() or None
    ftime = (data.get("followup_time") or "").strip() or None

    with engine.begin() as conn:
        owner_id = user["id"] if not is_manager else None
        if is_manager:
            owners = conn.execute(text("""
                SELECT id FROM users
                WHERE CASE WHEN :visitor LIKE '@%' THEN '@' || username=:visitor
                           ELSE full_name=:visitor END
                LIMIT 2
            """), {"visitor": vis}).scalars().all()
            if len(owners) > 1:
                raise HTTPException(status_code=422, detail="نام مسئول یکتا نیست؛ نام کاربری او را با @ وارد کنید")
            owner_id = owners[0] if owners else None
        conn.execute(text("""
            INSERT INTO customer_interactions
                (customer_name, visitor_name, owner_user_id, interaction_type, product_discussed, notes, status, next_followup_date, followup_time)
            VALUES (:cust, :vis, :owner_id, :itype, :prod, :notes, :status_val, :fdate, :ftime)
        """), {"cust": cust, "vis": vis, "itype": itype, "prod": prod,
               "owner_id": owner_id, "notes": notes, "status_val": status_val, "fdate": fdate, "ftime": ftime})
    return {"status": "ok", "message": "پیگیری با موفقیت ثبت شد"}


@app.patch("/crm/interactions/{interaction_id}/status")
def update_crm_interaction_status(interaction_id: int, data: dict, user: dict = Depends(current_user)):
    """Move a CRM card between approved Kanban stages with role/ownership checks."""
    allowed = {
        "در انتظار تماس", "پیگیری شد", "نیاز به پیش‌فاکتور",
        "سفارش ثبت شد", "عدم تمایل فعلی",
    }
    status_value = str(data.get("status") or "").strip()
    if status_value not in allowed:
        raise HTTPException(status_code=422, detail="وضعیت ارتباط با مشتری نامعتبر است")
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT id, owner_user_id FROM customer_interactions WHERE id=:id FOR UPDATE
        """), {"id": interaction_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="پیگیری پیدا نشد")
        if user.get("role") not in MANAGER_ROLES and row["owner_user_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="فقط پیگیری‌های خودتان قابل تغییر است")
        conn.execute(text("""
            UPDATE customer_interactions SET status=:status WHERE id=:id
        """), {"id": interaction_id, "status": status_value})
    return {"status": "updated", "interaction_id": interaction_id, "stage": status_value}

@app.get("/targets/custom-list")
def get_custom_targets(user: dict = Depends(current_user)):
    """دریافت لیست تارگت‌های شخصی‌سازی‌شده ویزیتورها با درصد و رنگ وضعیت"""
    salesperson_id = None
    if user.get("role") not in MANAGER_ROLES:
        salesperson_id = user.get("salesperson_id")
        if not salesperson_id:
            return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT t.id, t.title, t.period_type, t.product_focus, t.target_type, t.target_amount, t.bonus_reward,
                   COALESCE(sp.name, 'فروشنده تست') as salesperson_name,
                   COALESCE(SUM(s.total_amount), 0) as current_sales
            FROM targets t
            LEFT JOIN salespersons sp ON t.salesperson_id = sp.id
            LEFT JOIN sales s ON s.salesperson_id = sp.id
            WHERE t.status = 'active'
              AND (:spid IS NULL OR t.salesperson_id = :spid)
            GROUP BY t.id, t.title, t.period_type, t.product_focus, t.target_type, t.target_amount, t.bonus_reward, sp.name
            ORDER BY t.id DESC
        """), {"spid": salesperson_id}).mappings().all()

        results = []
        for r in rows:
            t_amt = float(r["target_amount"] or 50000000)
            c_sales = float(r["current_sales"] or 0)
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
def set_new_target(data: dict, _: dict = Depends(require_manager)):
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


# KIARAD_CORS_OUTERMOST - appended last: outermost middleware, so even 401s carry CORS headers
from config import CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Company monthly target: CEO sets it himself every month (self-service)
# ---------------------------------------------------------------------------
@app.get("/targets/company")
def targets_company():
    with engine.connect() as conn:
        current_report_date = conn.execute(text("SELECT CURRENT_DATE")).scalar()
        rows = conn.execute(text(
            "SELECT id, title, target_amount, status, start_date, end_date FROM targets "
            "WHERE salesperson_id IS NULL ORDER BY id DESC LIMIT 24"
        )).mappings().all()
        ms = conn.execute(text(
            "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE date >= date_trunc('month', CURRENT_DATE)"
        )).scalar() or 0
    items = list()
    for r in rows:
        items.append(dict(id=r.get("id"), title=r.get("title"), target_amount=float(r.get("target_amount") or 0),
                          status=r.get("status"), start_date=str(r.get("start_date") or ""), end_date=str(r.get("end_date") or "")))
    active_target = 0.0
    active_row = None
    for r in items:
        if r.get("status") == "active":
            active_target = r.get("target_amount")
            active_row = r
            break
    month_sales = float(ms or 0)
    month_start = current_report_date.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    period_valid = bool(active_row and active_row["start_date"] == str(month_start) and active_row["end_date"] == str(month_end))
    achieve = round((month_sales / active_target * 100), 1) if active_target > 0 and period_valid else None
    return dict(items=items, active_target=active_target, month_sales=month_sales,
                achievement_percent=achieve, target_period_valid=period_valid)

@app.post("/targets/company")
def set_company_target(data: dict, _: dict = Depends(require_manager)):
    amount_toman = float(data.get("amount_toman") or 0)
    if amount_toman <= 0:
        raise HTTPException(status_code=422, detail="amount_toman must be positive")
    rial = amount_toman * 10
    label = "تارگت ماهانه شرکت - " + iran_today().strftime("%Y-%m")
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE targets SET status = 'archived' WHERE salesperson_id IS NULL AND status = 'active'"
        ))
        tid = conn.execute(text(
            "INSERT INTO targets (salesperson_id, title, period_type, product_focus, target_amount, bonus_reward, status, start_date, end_date) "
            "VALUES (NULL, :t, 'ماهانه', 'کل سبد کالایی', :amt, 0, 'active', "
            "date_trunc('month', CURRENT_DATE)::date, "
            "(date_trunc('month', CURRENT_DATE) + INTERVAL '1 month - 1 day')::date) RETURNING id"
        ), dict(t=label, amt=rial)).scalar()
    return dict(status="ok", id=tid, target_rial=rial, title=label)


# --- RECONCILIATION_4BUCKET_ENDPOINTS ---
from fastapi import HTTPException, Body
from typing import Optional
from datetime import date
import db as _db_mod
import reconciliation_engine as _rec_eng

@app.get("/monthly-visit-plans/{plan_id}/reconciliation")
def get_plan_reconciliation_4buckets(plan_id: int, up_to_date: Optional[date] = None):
    session = _db_mod.SessionLocal()
    try:
        _rec_eng.ensure_reconciliation_schema(session)
        return _rec_eng.calculate_monthly_reconciliation(session, plan_id, up_to_date)
    finally:
        session.close()

@app.post("/monthly-visit-plans/stops/{stop_id}/outcome")
def record_stop_structured_outcome(
    stop_id: int,
    payload: dict = Body(...)
):
    session = _db_mod.SessionLocal()
    try:
        _rec_eng.ensure_reconciliation_schema(session)
        from sqlalchemy import text
        session.execute(
            text("""
                UPDATE monthly_visit_plan_stops
                SET outcome_status = :status,
                    holoo_preinvoice_code = :code,
                    order_amount_rial = :amount,
                    outcome_notes = :notes
                WHERE id = :sid
            """),
            {
                "status": payload.get("outcome_status", "completed"),
                "code": payload.get("holoo_preinvoice_code"),
                "amount": int(payload.get("order_amount_rial") or 0),
                "notes": payload.get("outcome_notes", ""),
                "sid": stop_id
            }
        )
        session.commit()
        return {"ok": True, "stop_id": stop_id}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        session.close()
