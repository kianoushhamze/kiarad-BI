from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import engine
from sqlalchemy import text


app = FastAPI(
    title="Kiarad BI API",
    version="1.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "status": "Kiarad BI API is running"
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return {
            "database": "connected"
        }

    except Exception as e:
        return {
            "database": "error",
            "detail": str(e)
        }


@app.get("/reports/summary")
def report_summary():

    query = text("""
        SELECT
            (SELECT COUNT(*) FROM customers) AS customers_count,
            (SELECT COUNT(*) FROM sales) AS sales_count,
            (SELECT COALESCE(SUM(total_amount),0) FROM sales) AS sales_amount,
            (SELECT COALESCE(SUM(amount),0) FROM payments) AS payments_amount
    """)

    with engine.connect() as conn:
        result = conn.execute(query).first()

    return dict(result._mapping)


@app.get("/reports/target")
def target_report(
    salesperson_id: int | None = None
):

    if salesperson_id:

        query = text("""
            SELECT
                t.title,
                t.target_amount,
                COALESCE(SUM(s.total_amount),0) AS actual_sales

            FROM targets t

            LEFT JOIN sales s
            ON s.salesperson_id = t.salesperson_id

            WHERE
                t.status='active'
                AND t.salesperson_id=:sid

            GROUP BY
                t.id,
                t.title,
                t.target_amount

            ORDER BY t.id DESC

            LIMIT 1
        """)

        params = {
            "sid": salesperson_id
        }

    else:

        query = text("""
            SELECT
                t.title,
                t.target_amount,
                COALESCE(SUM(s.total_amount),0) AS actual_sales

            FROM targets t

            LEFT JOIN sales s
            ON s.date >= t.start_date
            AND s.date <= t.end_date

            WHERE t.status='active'

            GROUP BY
                t.id,
                t.title,
                t.target_amount

            ORDER BY t.id DESC

            LIMIT 1
        """)

        params = {}


    with engine.connect() as conn:
        result = conn.execute(
            query,
            params
        ).first()


    if not result:
        return {
            "message": "No active target"
        }


    achievement = 0

    if result.target_amount:
        achievement = (
            result.actual_sales /
            result.target_amount
        ) * 100


    return {
        "title": result.title,
        "target": result.target_amount,
        "actual_sales": result.actual_sales,
        "achievement_percent": round(
            achievement,
            2
        ),
        "remaining": max(
            result.target_amount-result.actual_sales,
            0
        )
    }@app.get("/reports/sales-trend")
def sales_trend():

    query = text("""
        SELECT
            DATE(date) AS sale_date,
            COUNT(*) AS sales_count,
            COALESCE(SUM(total_amount),0) AS total_sales

        FROM sales

        GROUP BY DATE(date)

        ORDER BY sale_date
    """)

    with engine.connect() as conn:
        result = conn.execute(query)

        data = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "count": len(data),
        "trend": data
    }



@app.get("/reports/inactive-customers")
def inactive_customers():

    query = text("""
        SELECT
            c.id,
            c.name,
            c.city,
            MAX(s.date) AS last_purchase,
            COALESCE(SUM(s.total_amount),0) AS total_sales

        FROM customers c

        LEFT JOIN sales s
        ON c.id=s.customer_id

        GROUP BY
            c.id,
            c.name,
            c.city

        HAVING
            MAX(s.date) IS NULL
            OR MAX(s.date) < CURRENT_DATE - INTERVAL '30 days'

        ORDER BY total_sales DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query)

        data = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "count": len(data),
        "inactive_customers": data
    }



@app.get("/reports/customer-scores")
def customer_scores():

    query = text("""
        SELECT
            cs.customer_id,
            c.name,
            c.city,
            cs.score,
            cs.status

        FROM customer_scores cs

        JOIN customers c
        ON c.id=cs.customer_id

        ORDER BY cs.score DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query)

        data = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "count": len(data),
        "customers": data
    }



@app.get("/reports/recommendations")
def recommendations():

    query = text("""
        SELECT
            r.id,
            r.customer_id,
            c.name,
            c.city,
            r.priority,
            r.message,
            r.created_at

        FROM recommendations r

        LEFT JOIN customers c
        ON c.id=r.customer_id

        ORDER BY
            CASE
                WHEN r.priority='high' THEN 1
                WHEN r.priority='medium' THEN 2
                ELSE 3
            END,
            r.id DESC
    """)

    with engine.connect() as conn:
        result = conn.execute(query)

        data = [
            dict(row._mapping)
            for row in result
        ]

    return {
        "count": len(data),
        "recommendations": data
    }@app.get("/staff/performance")
def staff_performance(
    salesperson_id: int | None = None
):

    query = """
        SELECT
            sp.id,
            sp.name,

            COUNT(s.id) AS sales_count,

            COALESCE(
                SUM(s.total_amount),
                0
            ) AS sales_amount,

            COALESCE(
                t.target_amount,
                0
            ) AS target_amount

        FROM salespersons sp

        LEFT JOIN sales s
            ON s.salesperson_id = sp.id

        LEFT JOIN targets t
            ON t.salesperson_id = sp.id
            AND t.status='active'

        WHERE
            (:sid IS NULL OR sp.id=:sid)

        GROUP BY
            sp.id,
            sp.name,
            t.target_amount

        ORDER BY sales_amount DESC
    """

    with engine.connect() as conn:

        result = conn.execute(
            text(query),
            {
                "sid": salesperson_id
            }
        )

        rows = result.fetchall()


    data = []

    for row in rows:

        target = row.target_amount or 0
        sales = row.sales_amount or 0

        percent = (
            sales / target * 100
            if target else 0
        )

        data.append({

            "id": row.id,

            "name": row.name,

            "sales_count": row.sales_count,

            "sales_amount": sales,

            "target": target,

            "achievement_percent":
                round(percent,2),

            "remaining":
                max(target-sales,0)
        })


    return {
        "count": len(data),
        "staff": data
    }





@app.get("/dashboard/executive")
def executive_dashboard():

    with engine.connect() as conn:

        customers = conn.execute(text("""
            SELECT COUNT(*) AS count
            FROM customers
        """)).first()


        sales = conn.execute(text("""
            SELECT
                COUNT(*) AS count,
                COALESCE(SUM(total_amount),0) AS amount
            FROM sales
        """)).first()


        target = conn.execute(text("""
            SELECT
                title,
                target_amount

            FROM targets

            WHERE status='active'

            ORDER BY id DESC

            LIMIT 1
        """)).first()



    achievement = 0

    if target and target.target_amount:

        achievement = (
            sales.amount /
            target.target_amount
        ) * 100


    return {

        "customers":
            customers.count,


        "sales": {

            "count":
                sales.count,

            "amount":
                sales.amount
        },


        "target": {

            "title":
                target.title
                if target else None,

            "amount":
                target.target_amount
                if target else 0,

            "achievement":
                round(
                    achievement,
                    2
                )
        }

    }





@app.get("/dashboard/finance")
def finance_dashboard():

    with engine.connect() as conn:

        sales = conn.execute(text("""
            SELECT
                COALESCE(
                    SUM(total_amount),
                    0
                ) AS amount

            FROM sales
        """)).first()


        payments = conn.execute(text("""
            SELECT
                COALESCE(
                    SUM(amount),
                    0
                ) AS amount

            FROM payments
        """)).first()



        debts = conn.execute(text("""
            SELECT
                c.id,
                c.name,

                COALESCE(
                    SUM(s.total_amount),
                    0
                )
                -
                COALESCE(
                    SUM(p.amount),
                    0
                ) AS debt


            FROM customers c

            LEFT JOIN sales s
            ON c.id=s.customer_id


            LEFT JOIN payments p
            ON c.id=p.customer_id


            GROUP BY
                c.id,
                c.name


            HAVING
                (
                COALESCE(
                    SUM(s.total_amount),
                    0
                )
                -
                COALESCE(
                    SUM(p.amount),
                    0
                )
                ) > 0


            ORDER BY debt DESC
        """)).fetchall()



    return {

        "total_sales":
            sales.amount,


        "total_payments":
            payments.amount,


        "total_debt":
            sales.amount-payments.amount,


        "debtors":[

            dict(row._mapping)

            for row in debts

        ]

    }@app.get("/dashboard/inventory")
def inventory_dashboard():

    with engine.connect() as conn:

        summary = conn.execute(text("""
            SELECT
                COUNT(*) AS products_count,
                COALESCE(SUM(stock),0) AS total_stock,
                COALESCE(SUM(stock * price),0) AS inventory_value

            FROM products
        """)).first()


        products = conn.execute(text("""
            SELECT
                id,
                code,
                name,
                category,
                stock,
                price

            FROM products

            ORDER BY stock DESC
        """)).fetchall()


        low_stock = conn.execute(text("""
            SELECT
                id,
                code,
                name,
                stock

            FROM products

            WHERE stock <= 5

            ORDER BY stock ASC
        """)).fetchall()



    return {

        "products_count":
            summary.products_count,


        "total_stock":
            summary.total_stock,


        "inventory_value":
            summary.inventory_value,


        "products":[
            dict(row._mapping)
            for row in products
        ],


        "low_stock":[
            dict(row._mapping)
            for row in low_stock
        ]

    }





@app.get("/dashboard/powerbi")
def powerbi_dashboard():

    with engine.connect() as conn:


        kpi = conn.execute(text("""
            SELECT

                (SELECT COUNT(*) FROM customers)
                AS customers,


                (SELECT COALESCE(
                    SUM(total_amount),0)
                 FROM sales)
                AS sales,


                (SELECT COUNT(*) FROM sales)
                AS invoices,


                (SELECT COALESCE(
                    SUM(amount),0)
                 FROM payments)
                AS payments

        """)).first()



        target = conn.execute(text("""
            SELECT
                title,
                target_amount

            FROM targets

            WHERE status='active'

            ORDER BY id DESC

            LIMIT 1

        """)).first()



    achievement = 0


    if target and target.target_amount:

        achievement = (
            kpi.sales /
            target.target_amount
        ) * 100



    return {

        "kpi":{

            "customers":
                kpi.customers,


            "sales":
                kpi.sales,


            "invoices":
                kpi.invoices,


            "payments":
                kpi.payments,


            "target":
                target.target_amount
                if target else 0,


            "achievement":
                round(
                    achievement,
                    2
                )
        }

    }





@app.get("/dashboard/powerbi-full")
def powerbi_full():

    with engine.connect() as conn:


        sales_trend = conn.execute(text("""
            SELECT

                DATE(date) AS date,

                SUM(total_amount) AS amount


            FROM sales


            GROUP BY DATE(date)


            ORDER BY DATE(date)

        """)).fetchall()



        customer_status = conn.execute(text("""
            SELECT

                status,

                COUNT(*) AS count


            FROM customer_scores


            GROUP BY status

        """)).fetchall()



        recommendations = conn.execute(text("""
            SELECT

                priority,

                message


            FROM recommendations


            ORDER BY id DESC

        """)).fetchall()



    return {

        "sales_trend":[

            dict(row._mapping)

            for row in sales_trend

        ],


        "customer_status":[

            dict(row._mapping)

            for row in customer_status

        ],


        "recommendations":[

            dict(row._mapping)

            for row in recommendations

        ]

    }@app.get("/staff/performance")
def staff_performance(salesperson_id: int | None = None):

    query = """
    SELECT
        sp.id,
        sp.name,

        COALESCE(SUM(s.total_amount),0) AS sales_amount,
        COUNT(s.id) AS sales_count,

        COALESCE(
            MAX(t.target_amount),
            0
        ) AS target

    FROM salespersons sp

    LEFT JOIN sales s
        ON s.salesperson_id = sp.id

    LEFT JOIN targets t
        ON t.salesperson_id = sp.id
        AND t.status='active'

    """

    params = {}

    if salesperson_id:
        query += """
        WHERE sp.id = :salesperson_id
        """
        params["salesperson_id"] = salesperson_id


    query += """

    GROUP BY
        sp.id,
        sp.name

    ORDER BY
        sales_amount DESC

    """


    with engine.connect() as conn:
        rows = conn.execute(
            text(query),
            params
        ).fetchall()


    data = []

    for row in rows:

        target = row.target or 0
        sales = row.sales_amount or 0

        achievement = (
            sales / target * 100
            if target
            else 0
        )

        data.append({

            "id": row.id,
            "name": row.name,
            "sales_amount": sales,
            "sales_count": row.sales_count,
            "target": target,
            "achievement_percent": round(
                achievement,
                2
            ),
            "remaining": max(
                target-sales,
                0
            )

        })


    return {
        "count": len(data),
        "staff": data
    }