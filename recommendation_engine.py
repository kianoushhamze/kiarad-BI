from db import engine
from sqlalchemy import text


with engine.begin() as conn:

    conn.execute(text("""
        DELETE FROM recommendations
    """))


    customers = conn.execute(text("""
        SELECT
            cs.customer_id,
            c.name,
            cs.score,
            cs.status

        FROM customer_scores cs

        JOIN customers c
        ON c.id = cs.customer_id
    """)).fetchall()


    for customer in customers:

        if customer.status == "at_risk":

            message = (
                f"مشتری {customer.name} در خطر ریزش است. "
                "تماس پیگیری انجام شود."
            )

            priority = "high"


        elif customer.status == "gold":

            message = (
                f"مشتری {customer.name} مشتری ارزشمند است. "
                "پیشنهاد حفظ و افزایش خرید ارائه شود."
            )

            priority = "medium"


        else:

            message = (
                f"مشتری {customer.name} نیاز به بررسی فروش دارد."
            )

            priority = "low"


        conn.execute(text("""
            INSERT INTO recommendations
            (
                customer_id,
                priority,
                message
            )

            VALUES
            (
                :customer_id,
                :priority,
                :message
            )
        """),
        {
            "customer_id": customer.customer_id,
            "priority": priority,
            "message": message
        })


print("recommendations generated")