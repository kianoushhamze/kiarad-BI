"""Step 3 — Proactive layer: deterministic morning brief for the CEO.

Facts are computed directly from live tables (sales, financial_documents,
site_orders, products stock, Holoo sync log). No LLM joins the chain: every
number is reproducible and every uncertain figure is flagged MANUL_OVERRIDE.
Built once per Iranian business day, re-rendered on demand, stale-marked when
a source (Holoo sync) looks unhealthy.
"""
import json
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from iran_time import IRAN_TIMEZONE, iran_now, iran_today
from operations import current_user

router = APIRouter(prefix='/morning-brief', tags=['morning_brief'])

SYNC_LOG = Path(__file__).resolve().parent / 'logs' / 'holoo_invoice_sync.log'
MAX_SYNC_LAG_HOURS = 26
LOW_STOCK_THRESHOLD = 5
LOW_STOCK_LIMIT = 8
CHECK_WINDOW_DAYS = 7
BRIEF_HOUR = 7  # Tehran hour when the brief should exist

_TIMER: Thread | None = None
_TIMER_STOP = Event()
_TIMER_LOCK = Lock()


# ---------------------------------------------------------------- persistence
def ensure(conn) -> None:
    conn.execute(text('''CREATE TABLE IF NOT EXISTS morning_briefs(
        id SERIAL PRIMARY KEY,biz_date DATE NOT NULL UNIQUE,payload JSONB NOT NULL,
        is_stale BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS morning_brief_views(
        id SERIAL PRIMARY KEY,biz_date DATE NOT NULL,viewed_by INT NOT NULL,
        viewed_by_name TEXT NOT NULL DEFAULT '',viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(biz_date,viewed_by))'''))


# ---------------------------------------------------------------- sync log
def parse_sync_line(line: str) -> dict[str, Any] | None:
    """One log line = '<iso ts> <json receipt>'. Garbage-tolerant by design."""
    line = (line or '').strip()
    if not line:
        return None
    stamp_txt, _, rest = line.partition(' ')
    entry: dict[str, Any] = {'at': stamp_txt if stamp_txt else None, 'raw': rest[:400]}
    try:
        from datetime import datetime as _dt
        entry['at_dt'] = _dt.fromisoformat(stamp_txt)
    except Exception:
        entry['at_dt'] = None
    blob = rest.strip()
    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(blob)
        if not isinstance(parsed, dict):
            parsed = None
    except Exception:
        parsed = None
    if parsed:
        entry.update(parsed)
    status = ''
    for key in ('status', 'state', 'result', 'outcome'):
        if parsed and parsed.get(key):
            status = str(parsed[key])
            break
    if not status:
        low = line.lower()
        status = 'completed' if 'completed' in low else ('stale_source' if 'stale' in low else 'unknown')
    entry['status'] = status
    return entry


def sync_health() -> dict[str, Any]:
    info: dict[str, Any] = {'source': 'holoo_invoice_sync.log', 'healthy': False}
    try:
        if not SYNC_LOG.exists():
            info['error'] = 'فایل لاگ سینک یافت نشد'
            info['status'] = 'missing'
            return info
        lines = [ln for ln in SYNC_LOG.read_text(encoding='utf-8', errors='replace').splitlines() if ln.strip()][-3:]
        entries = [e for e in (parse_sync_line(ln) for ln in lines) if e]
        if not entries:
            info['error'] = 'لاگ سینک خالی است'
            info['status'] = 'empty'
            return info
        last = entries[-1]
        at_dt = last.get('at_dt')
        info['last_sync_at'] = last.get('at')
        info['status'] = last.get('status', 'unknown')
        if at_dt is not None:
            hours = (iran_now() - at_dt).total_seconds() / 3600.0
            info['hours_ago'] = round(hours, 1)
        else:
            info['hours_ago'] = None
        info['healthy'] = bool(
            'completed' in str(info['status'])
            and isinstance(info['hours_ago'], (int, float))
            and info['hours_ago'] <= MAX_SYNC_LAG_HOURS
        )
        return info
    except Exception as error:  # never let the brief die on one source
        info['error'] = f'خواندن لاگ ناموفق: {error}'
        return info


# ---------------------------------------------------------------- collectors
def _ok(section: dict[str, Any]) -> dict[str, Any]:
    return section


def _fail(section: str, error: Exception) -> dict[str, Any]:
    return {'error': f'{section}: {error}'}


def collect_sales_yesterday(conn) -> dict[str, Any]:
    today = iran_today()
    yest = today - timedelta(days=1)
    prev = yest - timedelta(days=1)
    row = conn.execute(text(
        'SELECT COALESCE(SUM(total_amount),0) AS amount,COUNT(*) AS documents '
        'FROM sales WHERE date=:d'), {'d': yest}).mappings().first()
    prow = conn.execute(text(
        'SELECT COALESCE(SUM(total_amount),0) AS amount FROM sales WHERE date=:d'),
        {'d': prev}).mappings().first()
    top = conn.execute(text(
        '''SELECT p.code,p.name,SUM(si.quantity) AS qty,SUM(si.quantity*si.price) AS amount
           FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
           WHERE s.date=:d GROUP BY p.id,p.code,p.name ORDER BY amount DESC LIMIT 1'''),
        {'d': yest}).mappings().first()
    return _ok({
        'date': yest.isoformat(),
        'net_sales_irr': int(row['amount'] or 0),
        'documents': int(row['documents'] or 0),
        'prev_day_net_sales_irr': int(prow['amount'] or 0),
        'top_product': (dict(top) if top else None),
    })


def collect_due_checks(conn) -> dict[str, Any]:
    today = iran_today()
    edge = today + timedelta(days=CHECK_WINDOW_DAYS)
    overdue = conn.execute(text(
        '''SELECT COUNT(*) AS n,COALESCE(SUM(amount),0) AS amount FROM financial_documents
           WHERE status='open' AND due_date<:t AND document_type='receivable' '''), {'t': today}).mappings().first()
    week = conn.execute(text(
        '''SELECT COUNT(*) AS n,COALESCE(SUM(amount),0) AS amount FROM financial_documents
           WHERE status='open' AND due_date>=:t AND due_date<=:e AND document_type='receivable' '''),
        {'t': today, 'e': edge}).mappings().first()
    nearest = conn.execute(text(
        '''SELECT document_type,counterparty,amount,due_date FROM financial_documents
           WHERE status='open' AND due_date<=:e ORDER BY due_date LIMIT 3'''),
        {'e': edge}).mappings().all()
    return _ok({
        'overdue_count': int(overdue['n'] or 0),
        'overdue_amount_irr': int(overdue['amount'] or 0),
        'week_count': int(week['n'] or 0),
        'week_amount_irr': int(week['amount'] or 0),
        'nearest': [dict(r) for r in nearest],
        'window_days': CHECK_WINDOW_DAYS,
    })


def collect_site_orders(conn) -> dict[str, Any]:
    yest = iran_today() - timedelta(days=1)
    row = conn.execute(text(
        '''SELECT COUNT(*) AS n,COALESCE(SUM(total_irr),0) AS amount FROM site_orders
           WHERE created_at::date=:d AND status='جدید' '''), {'d': yest}).mappings().first()
    today_n = conn.execute(text(
        '''SELECT COUNT(*) AS n FROM site_orders WHERE created_at::date=:t AND status='جدید' '''),
        {'t': iran_today()}).mappings().first()
    return _ok({
        'date': yest.isoformat(),
        'new_orders': int(row['n'] or 0),
        'new_orders_amount_irr': int(row['amount'] or 0),
        'today_so_far': int(today_n['n'] or 0),
    })


def collect_low_stock(conn) -> dict[str, Any]:
    col = conn.execute(text(
        '''SELECT column_name FROM information_schema.columns
           WHERE table_name='products' AND column_name IN ('stock','stock_qty','quantity','qty','min_stock')
           ORDER BY ordinal_position''')).scalar()
    if not col:
        return _ok({'skipped': 'ستون موجودی روی products یافت نشد — از ماژول هوش موجودی استفاده کنید'})
    rows = conn.execute(text(
        f'''SELECT code,name,{col} AS stock FROM products
            WHERE is_active AND COALESCE({col},0)<=:th ORDER BY COALESCE({col},0) LIMIT :lim'''),
        {'th': LOW_STOCK_THRESHOLD, 'lim': LOW_STOCK_LIMIT}).mappings().all()
    return _ok({'threshold': LOW_STOCK_THRESHOLD, 'items': [dict(r) for r in rows]})


def build_payload() -> dict[str, Any]:
    sections: dict[str, Any] = {}
    warnings: list[str] = []
    try:
        with engine.connect() as conn:
            for name, fn in (
                ('sales_yesterday', collect_sales_yesterday),
                ('due_checks', collect_due_checks),
                ('site_orders', collect_site_orders),
                ('low_stock', collect_low_stock),
            ):
                try:
                    sections[name] = fn(conn)
                except Exception as error:
                    sections[name] = _fail(name, error)
    except Exception as error:
        for name in ('sales_yesterday', 'due_checks', 'site_orders', 'low_stock'):
            sections.setdefault(name, _fail(name, error))
    sync = sync_health()
    sections['holoo_sync'] = sync
    if not sync.get('healthy'):
        warnings.append('سینک هلو سالم نیست؛ اعداد فروش ممکن است به‌روز نباشند (' + str(sync.get('status', '?')) + ')')
    if 'error' in sections['sales_yesterday']:
        warnings.append('بخش فروش دیروز محاسبه نشد: ' + str(sections['sales_yesterday']['error'])[:120])
    if 'error' in sections['due_checks']:
        warnings.append('بخش چک‌ها محاسبه نشد: ' + str(sections['due_checks']['error'])[:120])
    sales = sections.get('sales_yesterday') or {}
    if isinstance(sales.get('prev_day_net_sales_irr'), int) and sales['net_sales_irr'] == 0 and sales.get('documents') == 0:
        warnings.append('فروش ثبت‌شده برای دیروز صفر است — اگر همکاران فاکتور زده‌اند، سینک را بررسی کنید')
    return {
        'generated_for': iran_today().isoformat(),
        'generated_at': iran_now().isoformat(timespec='seconds'),
        'source': 'live-database (deterministic, no LLM)',
        'sections': sections,
        'warnings': warnings,
        'notes': None,
    }


def get_or_build_today(*, force: bool = False) -> dict[str, Any]:
    biz = iran_today()
    payload: dict[str, Any] | None = None
    stale = False
    with engine.begin() as conn:
        row = conn.execute(text('SELECT payload,is_stale FROM morning_briefs WHERE biz_date=:d'), {'d': biz}).mappings().first()
        if row:
            payload = row['payload']
            stale = bool(row['is_stale'])
    if payload is None or force:
        payload = build_payload()
        stale = bool(payload.get('warnings')) or not (payload.get('sections', {}).get('holoo_sync', {}) or {}).get('healthy', False)
        with engine.begin() as conn:
            if force:
                conn.execute(text(
                    '''INSERT INTO morning_briefs(biz_date,payload,is_stale) VALUES(:d,CAST(:p AS JSONB),:s)
                       ON CONFLICT (biz_date) DO UPDATE SET payload=CAST(EXCLUDED.payload AS JSONB),
                       is_stale=EXCLUDED.is_stale,updated_at=NOW()'''),
                    {'d': biz, 'p': json.dumps(payload, ensure_ascii=False), 's': stale})
            else:
                conn.execute(text(
                    '''INSERT INTO morning_briefs(biz_date,payload,is_stale) VALUES(:d,CAST(:p AS JSONB),:s)
                       ON CONFLICT (biz_date) DO NOTHING'''),
                    {'d': biz, 'p': json.dumps(payload, ensure_ascii=False), 's': stale})
    return {'biz_date': biz.isoformat(), 'is_stale': stale, 'brief': payload}


def ensure_and_build_today() -> None:
    """Startup / hourly timer: make sure today's brief exists after BRIEF_HOUR."""
    if iran_now().hour >= BRIEF_HOUR:
        get_or_build_today()


def _timer_loop() -> None:
    while not _TIMER_STOP.wait(timeout=1800):
        try:
            ensure_and_build_today()
        except Exception:
            pass


def start_morning_brief_timer() -> None:
    global _TIMER
    with _TIMER_LOCK:
        if _TIMER is not None and _TIMER.is_alive():
            return
        _TIMER_STOP.clear()
        _TIMER = Thread(target=_timer_loop, name='morning-brief-timer', daemon=True)
        _TIMER.start()


# ---------------------------------------------------------------- endpoints
class BriefNote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    notes: str = Field(min_length=3, max_length=2000)


def _ceo(user: dict) -> None:
    if not user or user.get('role') != 'ceo':
        raise HTTPException(403, 'گزارش صبحگاهی فقط برای مدیرعامل است.')


@router.get('')
def get_brief(user: dict = Depends(current_user)):
    _ceo(user)
    return get_or_build_today()


@router.get('/history')
def brief_history(days: int = 14, user: dict = Depends(current_user)):
    _ceo(user)
    days = max(1, min(days, 60))
    with engine.connect() as conn:
        rows = conn.execute(text(
            '''SELECT biz_date,is_stale,created_at,
                      payload->'sections'->'sales_yesterday'->>'net_sales_irr' AS net_sales_irr,
                      payload->'sections'->'site_orders'->>'new_orders' AS new_orders
               FROM morning_briefs ORDER BY biz_date DESC LIMIT :d'''), {'d': days}).mappings().all()
    return {'days': [dict(r) for r in rows]}


@router.post('/refresh')
def refresh_brief(user: dict = Depends(current_user)):
    _ceo(user)
    return get_or_build_today(force=True)


@router.post('/viewed')
def mark_viewed(user: dict = Depends(current_user)):
    _ceo(user)
    if not user.get('id'):
        raise HTTPException(422, 'کاربر بدون شناسه.')
    biz = iran_today()
    with engine.begin() as conn:
        exists = conn.execute(text(
            'SELECT 1 FROM morning_brief_views WHERE biz_date=:d AND viewed_by=:u'),
            {'d': biz, 'u': user['id']}).first()
        if not exists:
            conn.execute(text(
                '''INSERT INTO morning_brief_views(biz_date,viewed_by,viewed_by_name)
                   VALUES(:d,:u,:n)'''),
                {'d': biz, 'u': user['id'], 'n': str(user.get('name') or '')})
    return {'ok': True, 'biz_date': biz.isoformat()}


@router.post('/note')
def set_note(payload: BriefNote, user: dict = Depends(current_user)):
    _ceo(user)
    biz = iran_today()
    with engine.begin() as conn:
        row = conn.execute(text('SELECT payload FROM morning_briefs WHERE biz_date=:d'), {'d': biz}).mappings().first()
        if not row:
            raise HTTPException(404, 'گزارش امروز هنوز ساخته نشده است.')
        doc = dict(row['payload'])
        doc['notes'] = payload.notes
        conn.execute(text(
            '''UPDATE morning_briefs SET payload=CAST(:p AS JSONB),updated_at=NOW() WHERE biz_date=:d'''),
            {'p': json.dumps(doc, ensure_ascii=False), 'd': biz})
    return {'ok': True, 'biz_date': biz.isoformat()}
