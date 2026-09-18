import decimal
import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from db import engine

# ----------------------------------------------------------------------------
# App setup
# ----------------------------------------------------------------------------
app = FastAPI(title="Kiarad BI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def serialize_value(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def serialize_row(row: dict) -> dict:
    return {key: serialize_value(value) for key, value in row.items()}


def safe_fetch_all(query: str, params: Optional[dict] = None):
    params = params or {}
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            rows = result.mappings().all()
            return [serialize_row(dict(row)) for row in rows], None
    except SQLAlchemyError as exc:
        return [], str(exc)
    except Exception as exc:
        return [], str(exc)


def safe_fetch_one(query: str, params: Optional[dict] = None):
    rows, error = safe_fetch_all(query, params)
    if error:
        return None, error
    if not rows:
        return None, None
    return rows[0], None


def safe_scalar(query: str, params: Optional[dict] = None, default=0):
    params = params or {}
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            value = result.scalar()
            return (value if value is not None else default), None
    except SQLAlchemyError as exc:
        return default, str(exc)
    except Exception as exc:
        return default, str(exc)


def get_active_target_summary():
    target_row, error = safe_fetch_one(
        """
        SELECT id, salesperson_id, title, target_amount, month, year,
               target_type, start_date, end_date, status
        FROM targets
        WHERE status = 'active'
        ORDER BY start_date DESC, id DESC
        LIMIT 1
        """
    )

    if error:
        return {
            "title": None,
            "target": 0,
            "actual_sales": 0,
            "achievement_percent": 0,
            "remaining": 0,
            "warning": error,
        }

    if not target_row:
        return {
            "title": None,
            "target": 0,
            "actual_sales": 0,
            "achievement_percent": 0,
            "remaining": 0,
        }

    target_amount = float(target_row.get("target_amount") or 0)
    salesperson_id = target_row.get("salesperson_id")
    start_date = target_row.get("start_date")
    end_date = target_row.get("end_date")

    if start_date and end_date:
        if salesperson_id is not None:
            actual_sales, sales_error = safe_scalar(
                """
                SELECT COALESCE(SUM(total_amount), 0)
                FROM sales
                WHERE salesperson_id = :salesperson_id
                  AND date BETWEEN :start_date AND :end_date
                """,
                {
                    "salesperson_id": salesperson_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
        else:
            actual_sales, sales_error = safe_scalar(
                """
                SELECT COALESCE(SUM(total_amount), 0)
                FROM sales
                WHERE date BETWEEN :start_date AND :end_date
                """,
                {"start_date": start_date, "end_date": end_date},
            )
    else:
        if salesperson_id is not None:
            actual_sales, sales_error = safe_scalar(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE salesperson_id = :salesperson_id",
                {"salesperson_id": salesperson_id},
            )
        else:
            actual_sales, sales_error = safe_scalar(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sales"
            )

    actual_sales = float(actual_sales or 0)
    achievement_percent = (
        round((actual_sales / target_amount) * 100, 2) if target_amount > 0 else 0
    )
    remaining = max(target_amount - actual_sales, 0)

    result = {
        "title": target_row.get("title"),
        "target": target_amount,
        "actual_sales": actual_sales,
        "achievement_percent": achievement_percent,
        "remaining": remaining,
    }
    if sales_error:
        result["warning"] = sales_error
    return result


def get_staff_performance():
    salespersons, error = safe_fetch_all("SELECT id, name, phone FROM salespersons ORDER BY id")
    if error:
        return [], error

    staff_list = []
    for person in salespersons:
        sp_id = person.get("id")

        sales_amount, _ = safe_scalar(
            "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE salesperson_id = :sp_id",
            {"sp_id": sp_id},
        )
        invoice_count, _ = safe_scalar(
            "SELECT COUNT(*) FROM sales WHERE salesperson_id = :sp_id",
            {"sp_id": sp_id},
        )
        target_amount, _ = safe_scalar(
            """
            SELECT COALESCE(SUM(target_amount), 0)
            FROM targets
            WHERE salesperson_id = :sp_id AND status = 'active'
            """,
            {"sp_id": sp_id},
        )

        sales_amount = float(sales_amount or 0)
        invoice_count = int(invoice_count or 0)
        target_amount = float(target_amount or 0)

        achievement_percent = (
            round((sales_amount / target_amount) * 100, 2) if target_amount > 0 else 0
        )
        remaining = max(target_amount - sales_amount, 0)

        staff_list.append(
            {
                "id": sp_id,
                "name": person.get("name"),
                "sales_amount": sales_amount,
                "invoice_count": invoice_count,
                "target": target_amount,
                "achievement_percent": achievement_percent,
                "remaining": remaining,
            }
        )

    return staff_list, None


def get_finance_summary():
    warnings = []

    total_sales, error = safe_scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sales")
    if error:
        warnings.append(error)

    total_collected, error = safe_scalar("SELECT COALESCE(SUM(amount), 0) FROM payments")
    if error:
        warnings.append(error)

    total_sales = float(total_sales or 0)
    total_collected = float(total_collected or 0)
    total_debt = total_sales - total_collected
    collection_percent = (
        round((total_collected / total_sales) * 100, 2) if total_sales > 0 else 0
    )

    result = {
        "total_sales": total_sales,
        "total_collected": total_collected,
        "total_debt": total_debt,
        "collection_percent": collection_percent,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def get_inventory_summary(low_stock_threshold: int = 10):
    warnings = []

    products, error = safe_fetch_all("SELECT id, code, name, category, price, stock FROM products ORDER BY id")
    if error:
        warnings.append(error)
        products = []

    product_count = len(products)
    inventory_value = 0.0
    low_stock_items = []

    for product in products:
        price = float(product.get("price") or 0)
        stock = float(product.get("stock") or 0)
        inventory_value += price * stock
        if stock <= low_stock_threshold:
            low_stock_items.append(product)

    result = {
        "product_count": product_count,
        "inventory_value": inventory_value,
        "low_stock_count": len(low_stock_items),
        "low_stock_items": low_stock_items,
        "products": products,
    }
    if warnings:
        result["warnings"] = warnings
    return result


def get_recommendations():
    rows, error = safe_fetch_all(
        """
        SELECT r.id, r.customer_id, r.priority, r.message, r.created_at, c.name AS customer_name
        FROM recommendations r
        LEFT JOIN customers c ON c.id = r.customer_id
        ORDER BY r.priority DESC, r.created_at DESC
        """
    )
    if error:
        return [], error
    return rows, None


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
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {exc}")


# ----------------------------------------------------------------------------
# Dashboard: CEO
# ----------------------------------------------------------------------------
@app.get("/dashboard/ceo")
def dashboard_ceo():
    warnings = []

    total_sales, error = safe_scalar("SELECT COALESCE(SUM(total_amount), 0) FROM sales")
    if error:
        warnings.append(error)

    invoice_count, error = safe_scalar("SELECT COUNT(*) FROM sales")
    if error:
        warnings.append(error)

    total_collected, error = safe_scalar("SELECT COALESCE(SUM(amount), 0) FROM payments")
    if error:
        warnings.append(error)

    customer_count, error = safe_scalar("SELECT COUNT(*) FROM customers")
    if error:
        warnings.append(error)

    target_summary = get_active_target_summary()
    if target_summary.get("warning"):
        warnings.append(target_summary["warning"])

    total_sales = float(total_sales or 0)
    total_collected = float(total_collected or 0)
    total_debt = total_sales - total_collected

    response = {
        "total_sales": total_sales,
        "invoice_count": int(invoice_count or 0),
        "total_collected": total_collected,
        "customer_count": int(customer_count or 0),
        "active_target": target_summary.get("target", 0),
        "achievement_percent": target_summary.get("achievement_percent", 0),
        "total_debt": total_debt,
    }
    if warnings:
        response["warnings"] = warnings
    return response


# ----------------------------------------------------------------------------
# Staff performance & ranking
# ----------------------------------------------------------------------------
@app.get("/staff/performance")
def staff_performance():
    staff_list, error = get_staff_performance()
    if error:
        return {"count": 0, "staff": [], "warning": error}
    return {"count": len(staff_list), "staff": staff_list}


@app.get("/staff/ranking")
def staff_ranking():
    staff_list, error = get_staff_performance()
    if error:
        return {"count": 0, "ranking": [], "warning": error}

    sorted_staff = sorted(staff_list, key=lambda item: item["sales_amount"], reverse=True)

    ranking = []
    for index, staff in enumerate(sorted_staff, start=1):
        entry = dict(staff)
        entry["rank"] = index
        ranking.append(entry)

    return {"count": len(ranking), "ranking": ranking}


# ----------------------------------------------------------------------------
# Customers
# ----------------------------------------------------------------------------
@app.get("/customers/top")
def customers_top(limit: int = 10):
    rows, error = safe_fetch_all(
        """
        SELECT c.id, c.code, c.name, c.city,
               COALESCE(SUM(s.total_amount), 0) AS total_purchase,
               COUNT(s.id) AS invoice_count
        FROM customers c
        LEFT JOIN sales s ON s.customer_id = c.id
        GROUP BY c.id, c.code, c.name, c.city
        ORDER BY total_purchase DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    if error:
        return {"count": 0, "customers": [], "warning": error}
    return {"count": len(rows), "customers": rows}


@app.get("/customers/inactive")
def customers_inactive(days: int = 90):
    rows, error = safe_fetch_all(
        """
        SELECT c.id, c.code, c.name, c.city, c.phone, MAX(s.date) AS last_sale_date
        FROM customers c
        LEFT JOIN sales s ON s.customer_id = c.id
        GROUP BY c.id, c.code, c.name, c.city, c.phone
        HAVING MAX(s.date) IS NULL OR MAX(s.date) < (CURRENT_DATE - (:days || ' days')::interval)
        ORDER BY last_sale_date NULLS FIRST
        """,
        {"days": days},
    )
    if error:
        return {"count": 0, "customers": [], "cutoff_days": days, "warning": error}
    return {"count": len(rows), "customers": rows, "cutoff_days": days}


@app.get("/customers/scores")
def customers_scores():
    rows, error = safe_fetch_all(
        """
        SELECT cs.id, cs.customer_id, cs.score, cs.status, cs.created_at,
               c.name AS customer_name, c.city AS customer_city
        FROM customer_scores cs
        LEFT JOIN customers c ON c.id = cs.customer_id
        ORDER BY cs.score DESC
        """
    )
    if error:
        return {"count": 0, "customers": [], "warning": error}
    return {"count": len(rows), "customers": rows}


# ----------------------------------------------------------------------------
# Dashboard: finance
# ----------------------------------------------------------------------------
@app.get("/dashboard/finance")
def dashboard_finance():
    return get_finance_summary()


# ----------------------------------------------------------------------------
# Dashboard: inventory
# ----------------------------------------------------------------------------
@app.get("/dashboard/inventory")
def dashboard_inventory(low_stock_threshold: int = 10):
    return get_inventory_summary(low_stock_threshold)


# ----------------------------------------------------------------------------
# Products
# ----------------------------------------------------------------------------
@app.get("/products/top")
def products_top(limit: int = 10):
    rows, error = safe_fetch_all(
        """
        SELECT p.id, p.code, p.name, p.category, p.price,
               COALESCE(SUM(si.quantity), 0) AS total_sold
        FROM products p
        LEFT JOIN sale_items si ON si.product_id = p.id
        GROUP BY p.id, p.code, p.name, p.category, p.price
        ORDER BY total_sold DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )
    if error:
        fallback_rows, fallback_error = safe_fetch_all(
            """
            SELECT id, code, name, category, price, stock
            FROM products
            ORDER BY stock ASC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        if fallback_error:
            return {"count": 0, "products": [], "warning": f"{error} | {fallback_error}"}
        return {
            "count": len(fallback_rows),
            "products": fallback_rows,
            "warning": "sale_items table not available; showing lowest-stock products instead of top-selling.",
        }
    return {"count": len(rows), "products": rows}


# ----------------------------------------------------------------------------
# Recommendations
# ----------------------------------------------------------------------------
@app.get("/recommendations")
def recommendations():
    rows, error = get_recommendations()
    if error:
        return {"count": 0, "recommendations": [], "warning": error}
    return {"count": len(rows), "recommendations": rows}


# ----------------------------------------------------------------------------
# Dashboard: full (comprehensive for Next.js)
# ----------------------------------------------------------------------------
@app.get("/dashboard/full")
def dashboard_full():
    ceo_kpi = dashboard_ceo()

    staff_list, staff_error = get_staff_performance()
    staff_section = {"count": len(staff_list), "staff": staff_list}
    if staff_error:
        staff_section["warning"] = staff_error

    top_customers, top_customers_error = safe_fetch_all(
        """
        SELECT c.id, c.code, c.name, c.city,
               COALESCE(SUM(s.total_amount), 0) AS total_purchase,
               COUNT(s.id) AS invoice_count
        FROM customers c
        LEFT JOIN sales s ON s.customer_id = c.id
        GROUP BY c.id, c.code, c.name, c.city
        ORDER BY total_purchase DESC
        LIMIT 10
        """
    )
    customers_section = {"count": len(top_customers), "top_customers": top_customers}
    if top_customers_error:
        customers_section["warning"] = top_customers_error

    finance_section = get_finance_summary()
    inventory_section = get_inventory_summary()

    recs, recs_error = get_recommendations()
    recommendations_section = {"count": len(recs), "recommendations": recs}
    if recs_error:
        recommendations_section["warning"] = recs_error

    return {
        "ceo_kpi": ceo_kpi,
        "staff": staff_section,
        "customers": customers_section,
        "finance": finance_section,
        "inventory": inventory_section,
        "recommendations": recommendations_section,
    }


# ----------------------------------------------------------------------------
# Local run helper (not required when using uvicorn CLI)
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_full:app", host="0.0.0.0", port=8000, reload=True)
