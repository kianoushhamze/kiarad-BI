"""افزودن ستون‌های اختیاری هدف شخصی بدون تغییر داده‌های کسب‌وکار."""

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import text

from assistant_money import DIGITS


PERSON_TARGET_FIELDS = (
    'title', 'target_amount', 'month', 'year', 'target_type', 'start_date', 'end_date',
    'status', 'salesperson_id', 'period_type', 'product_focus', 'bonus_reward',
)


def normalize_person_target(data, *, existing=None):
    values = {key: data[key] for key in PERSON_TARGET_FIELDS if key in data}
    if existing is None:
        values = {
            'status': 'active', 'target_type': 'ماهانه', 'period_type': '', 'product_focus': '',
            'salesperson_id': None, 'bonus_reward': 0, 'month': None, 'year': None,
            **values,
        }
        for key in ('title', 'target_amount', 'start_date', 'end_date'):
            values.setdefault(key, None)
    elif not values:
        raise HTTPException(422, 'حداقل یک فیلد برای ویرایش تارگت لازم است.')

    if 'title' in values:
        if not isinstance(values['title'], str) or not 2 <= len(values['title'].strip()) <= 160:
            raise HTTPException(422, 'عنوان تارگت باید ۲ تا ۱۶۰ حرف باشد.')
        values['title'] = values['title'].strip()
    for key, label, low, high in (
        ('target_amount', 'مبلغ تارگت', Decimal('0.01'), Decimal('1e15')),
        ('bonus_reward', 'پاداش', 0, Decimal('9999999999999.99')),
    ):
        if key not in values:
            continue
        raw = values[key]
        if key == 'bonus_reward' and raw in (None, ''):
            raw = 0
        try:
            value = Decimal(str(raw).strip().translate(DIGITS).replace('٬', '').replace(',', '').replace('٫', '.'))
        except InvalidOperation:
            raise HTTPException(422, f'{label} را به‌صورت عدد وارد کنید.') from None
        if not value.is_finite() or not low <= value <= high or value != value.quantize(Decimal('0.01')):
            raise HTTPException(422, f'{label} در محدودهٔ مجاز ریال نیست.')
        values[key] = format(value, 'f')

    for key, limit in (('product_focus', 150), ('period_type', 50), ('target_type', 50)):
        if key not in values:
            continue
        if values[key] is None and key != 'target_type':
            values[key] = ''
        if not isinstance(values[key], str) or len(values[key]) > limit:
            raise HTTPException(422, 'نوع، دوره یا کالای هدف طول یا قالب نامعتبر دارد.')
    if 'status' in values and values['status'] not in ('active', 'archived'):
        raise HTTPException(422, 'وضعیت تارگت معتبر نیست.')
    if 'salesperson_id' in values and values['salesperson_id'] is not None:
        sid = str(values['salesperson_id']).translate(DIGITS)
        if len(sid) > 10 or not sid.isascii() or not sid.isdecimal() or not 0 < int(sid) <= 2147483647:
            raise HTTPException(422, 'ویزیتور معتبر انتخاب کنید.')
        values['salesperson_id'] = int(sid)

    date_keys = ('start_date', 'end_date')
    if any(key in values for key in date_keys):
        from treasury_excel import day
        for key in date_keys:
            if key in values:
                values[key] = day(str(values[key]))
        merged = {**(existing or {}), **values}
        try:
            begin, end = (date.fromisoformat(str(merged.get(key))) for key in date_keys)
        except (TypeError, ValueError):
            raise HTTPException(422, 'تاریخ شروع و پایان تارگت را کامل وارد کنید.') from None
        if begin > end or (end - begin).days > 366:
            raise HTTPException(422, 'تاریخ پایان باید پس از شروع یا همان روز و بازه حداکثر یک سال باشد.')
        import jdatetime
        calendar = jdatetime.date.fromgregorian(date=begin)
        for key in ('month', 'year'):
            if ('start_date' in values and key not in data) or (key in values and values[key] is None):
                values[key] = getattr(calendar, key)
    for key, low, high in (('month', 1, 12), ('year', 1, 9999)):
        if key in values and values[key] is not None:
            value = str(values[key]).translate(DIGITS)
            if len(value) > 4 or not value.isascii() or not value.isdecimal() or not low <= int(value) <= high:
                raise HTTPException(422, 'ماه یا سال تارگت معتبر نیست.')
            values[key] = int(value)
    return values


def validate_target_person(conn, values):
    sid = values.get('salesperson_id')
    if sid is not None and not conn.execute(text('SELECT 1 FROM salespersons WHERE id=:id'), {'id': sid}).scalar():
        raise HTTPException(422, 'ویزیتور معتبر انتخاب کنید.')


def ensure_person_target_columns(conn) -> None:
    """ستون‌های مفقود را در تراکنش فراخواننده و بدون مقدار پیش‌فرض اضافه کند."""
    for statement in (
        "ALTER TABLE targets ADD COLUMN IF NOT EXISTS period_type VARCHAR(50)",
        "ALTER TABLE targets ADD COLUMN IF NOT EXISTS product_focus VARCHAR(150)",
        "ALTER TABLE targets ADD COLUMN IF NOT EXISTS bonus_reward NUMERIC(15,2)",
    ):
        conn.execute(text(statement))
