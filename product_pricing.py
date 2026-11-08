"""Two explicit selling price levels, in IRR; unknown level two stays unknown."""
from sqlalchemy import text
from fastapi import HTTPException
from decimal import Decimal, InvalidOperation


def ensure_product_prices(conn):
    conn.execute(text('ALTER TABLE products ADD COLUMN IF NOT EXISTS price2 NUMERIC'))


def selected_price(product, level):
    if type(level) is not int or level not in (1,2):
        raise HTTPException(422,'سطح قیمت باید یک یا دو باشد.')
    raw=product.get('price') if level==1 else product.get('price2')
    try:
        value=Decimal(str(raw))
        if not value.is_finite() or value<=0:raise ValueError()
    except (InvalidOperation,ValueError,TypeError):
        raise HTTPException(422,f'قیمت {level} این کالا ثبت نشده یا معتبر نیست؛ قیمت دیگری جایگزین نمی‌شود.')
    return float(value)
