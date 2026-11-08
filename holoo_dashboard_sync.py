"""Safely import recent Holoo sales totals for command-center reporting."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import re

from sqlalchemy import text

from db import engine
from holoo_sync import holoo_get, holoo_login
from treasury import parse_jalali_date


def _parse_invoice(row):
    sanad = row.get("SanadCode") or row.get("sanad_code")
    customer_code = row.get("customerCodeC") or row.get("CustomerErpCode")
    raw_date = str(row.get("Date") or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if not sanad or not customer_code or not raw_date:
        return None
    try:
        date_match = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw_date)
        if not date_match:
            return None
        year, month, day = map(int, date_match.groups())
        if year >= 1700:
            invoice_date = datetime(year, month, day)
        else:
            _, invoice_date = parse_jalali_date(raw_date)
        if invoice_date is None:
            return None
        amount = float(row.get("SumPrice") or 0)
        return int(sanad), str(customer_code).strip(), invoice_date, amount
    except (TypeError, ValueError):
        return None


def sync_recent_invoices(days=90):
    # The shared source is a complete fiscal-year snapshot. An isolated 90-day
    # importer would otherwise race and double-count records with repeated numbers.
    from holoo_operational_sync import sync_operational_snapshot
    return sync_operational_snapshot()


if __name__ == "__main__":
    print(sync_recent_invoices())
