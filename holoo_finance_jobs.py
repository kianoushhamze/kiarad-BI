"""Bounded in-process read-only financial refresh, with no credentials in status."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock, Event, Thread
from datetime import timedelta
import os
from holoo_finance import refresh_financial_snapshot
from holoo_operational_sync import sync_operational_snapshot

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="holoo-finance")
_LOCK = Lock()
_STATE = {"status": "idle", "sources": [], "snapshot_id": None}
_AUTO_LOCK = Lock()
_STOP = Event()
_THREAD = None
_AUTO = {"enabled": False, "running": False, "interval_seconds": 300, "next_attempt_at": None}
# A refresh is bounded by holoo_finance.REFRESH_DEADLINE_SECONDS; anything still
# marked running past this window is a lost job, not a real one, and must not
# block every later attempt forever.
STALE_SECONDS = max(600, int(os.getenv('HOLO_REFRESH_STALE_SECONDS', '1800')))


def _stale(started_at):
    if not started_at:
        return True
    try:
        started = datetime.fromisoformat(str(started_at))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return (datetime.now(timezone.utc) - started).total_seconds() > STALE_SECONDS


def automatic_refresh_status():
    with _AUTO_LOCK:
        return dict(_AUTO)


def automatic_config():
    # Never start a background ERP request in an isolated test process.
    testing = any(k.startswith('KIARAD_TEST_') and v == '1' for k, v in os.environ.items())
    enabled = os.getenv('HOLO_AUTO_REFRESH_ENABLED', '0').lower() in {'1', 'true', 'yes'}
    try:
        interval = max(300, min(86400, int(os.getenv('HOLO_AUTO_REFRESH_SECONDS', '300'))))
    except ValueError:
        interval = 300
    return enabled and bool(os.getenv('HOLO_API_URL')) and not testing, interval


RETRY_BACKOFF_FACTOR = 3
MAX_BACKOFF_SECONDS = 3600


def _next_delay(interval):
    """Back off after an unsuccessful run so a struggling ERP is not hammered."""
    with _LOCK:
        status = _STATE.get('status')
    if status in {'failed', 'partial'}:
        return min(MAX_BACKOFF_SECONDS, max(interval, 300) * RETRY_BACKOFF_FACTOR)
    return interval


def _automatic_loop(interval):
    try:
        while not _STOP.is_set():
            delay = _next_delay(interval)
            try:
                start_financial_refresh()
            except Exception:
                # Keep retrying after transient errors without logging upstream secrets.
                pass
            with _AUTO_LOCK:
                _AUTO['next_attempt_at'] = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            if _STOP.wait(delay):
                break
    finally:
        with _AUTO_LOCK:
            _AUTO.update(running=False, next_attempt_at=None)


def start_automatic_refresh():
    global _THREAD
    enabled, interval = automatic_config()
    with _AUTO_LOCK:
        if _THREAD and _THREAD.is_alive():
            return
        _AUTO.update(enabled=enabled, interval_seconds=interval, next_attempt_at=None)
        if not enabled:
            return
        _STOP.clear()
        _THREAD = Thread(target=_automatic_loop, args=(interval,), daemon=True, name='holoo-auto-refresh')
        _AUTO['running'] = True
        try:
            _THREAD.start()
        except Exception:
            _AUTO['running'] = False


def stop_automatic_refresh():
    _STOP.set()
    if _THREAD:
        _THREAD.join(timeout=2)


def financial_refresh_status():
    with _LOCK:
        state = {**_STATE, "sources": [dict(item) for item in _STATE["sources"]]}
    return {**state, "automatic": automatic_refresh_status()}


def _run_refresh():
    def progress(kind, source):
        item = {"kind": kind, "ok": bool(source.get("ok")), "complete": bool(source.get("complete")), "count": len(source.get("rows", []))}
        with _LOCK:
            _STATE["sources"].append(item)
    try:
        result = refresh_financial_snapshot(progress)
        good = result["currency_verified"] and all(item["ok"] and item["complete"] for item in result["sources"])
        operational = {"status": "blocked_incomplete_source"}
        if good:
            try:
                operational = sync_operational_snapshot(result['id'])
            except Exception:
                operational = {"status":"failed","message":"نسخهٔ مالی دریافت شد؛ تطبیق گزارش‌های عملیاتی کامل نشد و باید بررسی شود."}
                good = False
        with _LOCK:
            _STATE.update(status="completed" if good else "partial", snapshot_id=result["id"], operational=operational, finished_at=datetime.now(timezone.utc).isoformat())
    except Exception:
        # Upstream errors can contain tokens or private URLs. Do not expose them.
        with _LOCK:
            _STATE.update(status="failed", message="دریافت هلو کامل نشد؛ اتصال و سرویس هلو را بررسی کنید.", finished_at=datetime.now(timezone.utc).isoformat())


def start_financial_refresh():
    with _LOCK:
        if _STATE["status"] == "running":
            if not _stale(_STATE.get("started_at")):
                return {**_STATE, "sources": [dict(item) for item in _STATE["sources"]], "already_running": True}
            # The worker died or exceeded the deadline without reporting back.
            _STATE.clear()
            _STATE.update(status="running", started_at=datetime.now(timezone.utc).isoformat(), sources=[],
                          snapshot_id=None, stale_run_discarded=True)
        else:
            _STATE.clear()
            _STATE.update(status="running", started_at=datetime.now(timezone.utc).isoformat(), sources=[], snapshot_id=None)
    try:
        _POOL.submit(_run_refresh)
    except Exception:
        with _LOCK:
            _STATE.update(status="failed", message="شروع دریافت ممکن نشد؛ دوباره تلاش کنید.")
    return financial_refresh_status()
