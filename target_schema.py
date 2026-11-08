"""افزودن ستون‌های اختیاری هدف شخصی بدون تغییر داده‌های کسب‌وکار."""

from sqlalchemy import text


def ensure_person_target_columns(conn) -> None:
    """ستون‌های مفقود را در تراکنش فراخواننده و بدون مقدار پیش‌فرض اضافه کند."""
    for statement in (
        "ALTER TABLE targets ADD COLUMN IF NOT EXISTS period_type VARCHAR(50)",
        "ALTER TABLE targets ADD COLUMN IF NOT EXISTS product_focus VARCHAR(150)",
        "ALTER TABLE targets ADD COLUMN IF NOT EXISTS bonus_reward NUMERIC(15,2)",
    ):
        conn.execute(text(statement))
