from db import engine
from sqlalchemy import text


with engine.begin() as conn:

    # Rebuild the latest snapshot instead of duplicating rows on every run.
    conn.execute(text("DELETE FROM customer_scores"))

    customers = conn.execute(text("""
        SELECT
            c.id,
            COALESCE(SUM(s.total_amount),0) AS total_sales,
            COUNT(s.id) AS sales_count

        FROM customers c

        LEFT JOIN sales s
        ON c.id = s.customer_id

        GROUP BY c.id
    """)).fetchall()


    for customer in customers:

        score = 0


        if customer.total_sales >= 5000000:
            score += 50

        elif customer.total_sales > 0:
            score += 30


        if customer.sales_count >= 3:
            score += 30

        elif customer.sales_count > 0:
            score += 15


        if score >= 70:
            status = "gold"

        elif score >= 40:
            status = "normal"

        else:
            status = "at_risk"


        conn.execute(text("""
            INSERT INTO customer_scores
            (customer_id, score, status)

            VALUES
            (:customer_id,:score,:status)
        """),
        {
            "customer_id": customer.id,
            "score": score,
            "status": status
        })


print("customer scoring completed")
