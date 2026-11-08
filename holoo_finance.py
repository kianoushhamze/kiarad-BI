"""Documented, read-only Holoo financial extraction; no ERP financial writes."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import threading
import time

import jdatetime
from sqlalchemy import text

from db import engine
from holoo_router import get_holoo, login_holoo
from iran_time import iran_today

REFRESH_LOCK = threading.Lock()


def _seconds(env, default, low=10, high=3600):
    """Bounded timeout so a slow ERP cannot stall a refresh forever."""
    try:
        return max(low, min(high, int(os.getenv(env, default))))
    except (TypeError, ValueError):
        return default


# The Holoo web service answers in seconds normally and in tens of seconds when
# the ERP host is busy; the previous 25-35s budgets produced recurring
# ReadTimeouts that left every snapshot partial.
SETTINGS_TIMEOUT = _seconds('HOLO_SETTINGS_TIMEOUT', 30)
SOURCE_TIMEOUT = _seconds('HOLO_SOURCE_TIMEOUT', 90)
INVOICE_TIMEOUT = _seconds('HOLO_INVOICE_TIMEOUT', 60)
REFRESH_DEADLINE_SECONDS = _seconds('HOLO_REFRESH_DEADLINE', 900, low=60)
RETRY_DELAY_SECONDS = 2


def with_retry(action, attempts=2, delay=RETRY_DELAY_SECONDS):
    """Retry a transient ERP read once; never swallow the final error."""
    last = None
    for attempt in range(max(1, attempts)):
        try:
            return action()
        except Exception as error:  # network timeouts, 502s, truncated JSON
            last = error
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise last


SAFE_KEYS = {
    "cash": {"Code", "Name", "Price"}, "banks": {"Code", "Name", "Price"},
    "customers": {"Code", "ErpCode", "Name", "Mandeh", "Credit", "CustType", "type", "BedSarfasl", "BesSarfasl", "IsPurchaser", "IsSeller", "IsActive", "IsBlackList", "sumFloatCheques", "sumFloatNotCashedCheques", "debtInCheques"},
    "products": {"Code", "ErpCode", "Name", "Few", "BuyPrice", "LastBuyPrice", "SellPrice", "SellPrice2", "IsActive", "MainGroupName", "SideGroupName"},
    "invoices": {"ErpCode", "SanadCode", "Code", "FCode", "CustomerErpCode", "customerCodeC", "Date", "SumPrice", "SumDiscount", "SumLevy", "SumScot", "SumNaghd", "SumCard", "SumNesiyeh", "SumCheck", "Detail"},
    "details": {"ProductErpCode", "ProductCode", "Few", "Price", "SumPrice", "Discount", "PersentDiscount", "Levy", "Scot"},
}


def ensure_financial_snapshot_schema(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS holoo_financial_snapshots (
        id BIGSERIAL PRIMARY KEY, captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        payload JSONB NOT NULL, source_hash VARCHAR(64) NOT NULL)"""))


def safe_rows(rows, kind):
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Unexpected Holoo row")
        item = {key: value for key, value in row.items() if key in SAFE_KEYS[kind] and key != "Detail"}
        if kind == "invoices":
            detail = row.get("Detail", [])
            if detail is None:
                detail = []
            if not isinstance(detail, list):
                raise ValueError("Unexpected invoice detail")
            item["Detail"] = safe_rows(detail, "details")
        clean.append(item)
    return clean


def records(payload, keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                value = payload[key]
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    return [value]
    raise ValueError("Holoo response does not have a documented collection")


def currency_factor(payload):
    for row in records(payload, ("CurrencyUnit",)):
        name = str(row.get("name", "")).lower()
        value = str(row.get("string", "")).replace("ي", "ی").replace("ك", "ک").strip().lower()
        if name == "repvahedpooli":
            if value in {"ریال", "rial", "irr"}:
                return 1, "ریال"
            if value in {"تومان", "toman", "irt"}:
                return 10, "تومان"
    return None, "نامشخص"


def numeric(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Missing financial amount")
    try:
        result = Decimal(str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace(",", "").replace("٬", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid financial amount") from exc
    if not result.is_finite():
        raise ValueError("Nonfinite financial amount")
    return result


def invoice_pages(token, invoice_type, start, end, fetch=get_holoo, deadline=None):
    rows, seen_pages = [], set()
    for page in range(1, 26):
        if deadline is not None and time.monotonic() > deadline:
            return safe_rows(rows, "invoices"), False, "مهلت دریافت تمام شد؛ پاسخ کامل نیست."
        path = f"/Invoice/Invoice?type={invoice_type}&Date.from={start}&Date.to={end}&page={page}&itemsperpage=200"
        payload = with_retry(lambda: fetch(path, token, timeout=INVOICE_TIMEOUT))
        current = records(payload, ("invoice", "Invoice"))
        digest = hashlib.sha256(json.dumps(current, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if current and digest in seen_pages:
            return safe_rows(rows, "invoices"), False, "تکرار صفحه؛ کامل‌بودن پاسخ تأیید نشد."
        seen_pages.add(digest)
        rows.extend(current)
        if len(current) < 200:
            return safe_rows(rows, "invoices"), True, None
    return safe_rows(rows, "invoices"), False, "سقف صفحه‌بندی رسید؛ پاسخ کامل نیست."


def refresh_financial_snapshot(progress=None, fetch=None, login=None):
    if not REFRESH_LOCK.acquire(blocking=False):
        raise RuntimeError("Financial extraction is already running")
    fetch = fetch or get_holoo
    login = login or login_holoo
    lease = None
    acquired = False
    try:
        # Serialize browser, scheduler and command-line refreshes across processes.
        lease = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        acquired = bool(lease.execute(text("SELECT pg_try_advisory_lock(hashtextextended('kiarad:financial-refresh',0))")).scalar())
        if not acquired:
            raise RuntimeError("Financial refresh already active in another process")
        today = iran_today()
        year = jdatetime.date.fromgregorian(date=today).year
        start = jdatetime.date(year, 1, 1).togregorian().isoformat()
        token = login()
        deadline = time.monotonic() + REFRESH_DEADLINE_SECONDS
        result = {"source": "holoo_read_only", "started_at": datetime.now(timezone.utc).isoformat(),
                  "from_date": start, "to_date": today.isoformat(), "sources": {},
                  "currency_factor": None, "currency_label": "نامشخص", "erp_financial_writes": False}
        try:
            factor, label = currency_factor(with_retry(lambda: fetch("/Settings", token, timeout=SETTINGS_TIMEOUT)))
            result.update(currency_factor=factor, currency_label=label)
            result["sources"]["settings"] = {"ok": factor is not None, "rows": [], "path": "/Settings", "complete": factor is not None}
        except Exception as exc:
            result["sources"]["settings"] = {"ok": False, "error_type": type(exc).__name__, "rows": [], "complete": False}
        for kind, path, keys in (
            ("cash", "/Report/GetCash", ("report", "Report")),
            ("banks", "/Report/GetAccound", ("report", "Report")),
            ("customers", "/Customer", ("Customer", "customer")),
            ("products", "/Product", ("product", "Product")),
        ):
            try:
                if time.monotonic() > deadline:
                    raise TimeoutError("refresh deadline reached")
                rows = safe_rows(records(with_retry(lambda: fetch(path, token, timeout=SOURCE_TIMEOUT)), keys), kind)
                result["sources"][kind] = {"ok": True, "path": path, "complete": True, "rows": rows}
            except Exception as exc:
                result["sources"][kind] = {"ok": False, "path": path, "complete": False, "rows": [], "error_type": type(exc).__name__}
            if progress:
                progress(kind, result["sources"][kind])
        for number, kind in ((1, "purchases"), (2, "sales"), (3, "purchase_returns"), (4, "sales_returns")):
            try:
                if time.monotonic() > deadline:
                    raise TimeoutError("refresh deadline reached")
                rows, complete, warning = invoice_pages(token, number, start, today.isoformat(), fetch, deadline=deadline)
                result["sources"][kind] = {"ok": True, "path": f"/Invoice/Invoice?type={number}", "rows": rows, "complete": complete, "warning": warning}
            except Exception as exc:
                result["sources"][kind] = {"ok": False, "path": f"/Invoice/Invoice?type={number}", "rows": [], "complete": False, "error_type": type(exc).__name__}
            if progress:
                progress(kind, result["sources"][kind])
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
        with engine.begin() as conn:
            ensure_financial_snapshot_schema(conn)
            ident = conn.execute(text("INSERT INTO holoo_financial_snapshots(payload,source_hash) VALUES(CAST(:payload AS JSONB),:hash) RETURNING id"),
                                 {"payload": serialized, "hash": hashlib.sha256(serialized.encode()).hexdigest()}).scalar_one()
        return {"id": ident, **summarize_snapshot(result)}
    finally:
        try:
            if lease is not None:
                try:
                    if acquired:
                        lease.execute(text("SELECT pg_advisory_unlock(hashtextextended('kiarad:financial-refresh',0))"))
                except Exception:
                    lease.invalidate()
                finally:
                    lease.close()
        finally:
            REFRESH_LOCK.release()


def latest_financial_snapshot(conn):
    ensure_financial_snapshot_schema(conn)
    row = conn.execute(text("SELECT id,captured_at,payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1")).mappings().first()
    return {"id": row["id"], "captured_at": row["captured_at"], **summarize_snapshot(row["payload"])} if row else None


def latest_financial_payload(conn, snapshot_id=None):
    ensure_financial_snapshot_schema(conn)
    if snapshot_id is not None:
        return conn.execute(text("SELECT payload FROM holoo_financial_snapshots WHERE id=:id"), {"id":snapshot_id}).scalar()
    return conn.execute(text("SELECT payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1")).scalar()


def summarize_snapshot(payload):
    factor = payload.get("currency_factor")
    sources = payload["sources"]
    summaries = []
    for kind, value in sources.items():
        rows = value.get("rows", [])
        total = None
        valid = 0
        amount_key = "SumPrice" if kind in {"purchases", "sales", "purchase_returns", "sales_returns"} else "Price" if kind in {"cash", "banks"} else None
        duplicates = 0
        if amount_key and factor:
            acc, keys = Decimal(0), set()
            for row in rows:
                key = str(row.get("ErpCode") or row.get("SanadCode") or row.get("Code") or "")
                if not key or key in keys:
                    duplicates += 1
                    continue
                keys.add(key)
                try:
                    acc += numeric(row.get(amount_key)) * factor
                    valid += 1
                except ValueError:
                    pass
            if value.get("ok") and value.get("complete") and valid == len(rows) and not duplicates:
                total = float(acc)
        summaries.append({"kind": kind, "ok": value.get("ok", False), "complete": value.get("complete", False),
                          "count": len(rows), "total_irr": total, "duplicate_or_missing_keys": duplicates,
                          "valid_amounts": valid, "detail_count": sum(len(row.get("Detail", [])) for row in rows),
                          "path": value.get("path"), "warning": value.get("warning"), "error_type": value.get("error_type")})
    balances = []
    for kind in ("cash", "banks"):
        source = sources.get(kind, {})
        if factor and source.get("ok") and source.get("complete"):
            for row in source.get("rows", []):
                try:
                    balances.append({"source": kind, "code": str(row["Code"]), "name": str(row.get("Name", "حساب هلو")), "balance": float(numeric(row["Price"]) * factor)})
                except (ValueError, KeyError):
                    continue
    return {"from_date": payload["from_date"], "to_date": payload["to_date"],
            "finished_at": payload.get("finished_at"), "currency_label": payload.get("currency_label"),
            "currency_verified": factor is not None, "sources": summaries, "balances": balances,
            "net_profit_available": False,
            "limitations": ["قیمت خرید فعلی و آخرین خرید، بهای تاریخی کالای فروش‌رفته نیستند؛ سود قطعی از آن‌ها ساخته نمی‌شود.",
                            "ماندهٔ بانک و صندوق با حساب‌های دستی جمع نشده است؛ برای جلوگیری از همپوشانی، در بخش منبع هلو جدا نمایش داده می‌شود.",
                            "ماندهٔ اشخاص و چک‌های شناور، اسناد دارای سررسید نیستند و خودکار به وصول آینده تبدیل نمی‌شوند.",
                            "درگاه کامل چک و گزارش بهای تمام‌شده در قرارداد وب‌سرویس ارائه نشده است؛ دریافتنی/پرداختنی ماهانه هنوز منبع کامل ندارد."]}
