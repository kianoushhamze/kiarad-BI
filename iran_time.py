"""Iran-local calendar dates and clock values for business logic."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

IRAN_TIMEZONE = ZoneInfo("Asia/Tehran")


def iran_now() -> datetime:
    return datetime.now(IRAN_TIMEZONE)


def iran_today() -> date:
    return iran_now().date()


def iran_month_bounds(day: date | None = None):
    import jdatetime
    local=jdatetime.date.fromgregorian(date=day or iran_today())
    begin=jdatetime.date(local.year,local.month,1)
    end=jdatetime.date(local.year+(local.month==12),1 if local.month==12 else local.month+1,1)
    return begin.togregorian(),end.togregorian()
