"""Payroll periods are half-open calendar months in Tehran local time."""
import re
from datetime import date, datetime, time

import jdatetime

from iran_time import IRAN_TIMEZONE


def payroll_period(month: str):
    normalized = str(month or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", normalized):
        raise ValueError("ماه باید به شکل سال-ماه باشد")
    year, number = map(int, normalized.split("-"))
    if not 1 <= number <= 12:
        raise ValueError("ماه معتبر نیست")
    next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
    if 1200 <= year <= 1600:
        start = jdatetime.date(year, number, 1).togregorian()
        end = jdatetime.date(next_year, next_month, 1).togregorian()
        calendar = "persian"
    elif 1900 <= year <= 2200:
        start, end = date(year, number, 1), date(next_year, next_month, 1)
        calendar = "gregorian"
    else:
        raise ValueError("سال دورهٔ حقوق معتبر نیست")
    return normalized, datetime.combine(start, time.min), datetime.combine(end, time.min), calendar


def current_payroll_month():
    today = jdatetime.date.fromgregorian(date=datetime.now(IRAN_TIMEZONE).date())
    return f"{today.year:04d}-{today.month:02d}"


def period_is_approved(cur, salesperson_id: int, timestamp: datetime):
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(IRAN_TIMEZONE).replace(tzinfo=None)
    cur.execute("SELECT payroll_month FROM payroll_approvals WHERE salesperson_id=%s AND status='approved'", (salesperson_id,))
    for (month,) in cur.fetchall():
        _, start, end, _ = payroll_period(month)
        if start <= timestamp < end:
            return True
    return False
