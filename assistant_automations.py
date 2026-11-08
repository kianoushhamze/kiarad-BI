"""Scheduled assistant automations for the CEO: the assistant runs a prompt on a
recurring schedule with full read access; business writes are only ever stored as
proposals awaiting a separate human confirmation (assistant_operations.prepare)."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from db import engine
from iran_time import IRAN_TIMEZONE, iran_now
from operations import current_user

router = APIRouter(prefix='/automations', tags=['assistant_automations'])

WEEKDAY_LABELS = {0: 'دوشنبه', 1: 'سه‌شنبه', 2: 'چهارشنبه', 3: 'پنجشنبه', 4: 'جمعه', 5: 'شنبه', 6: 'یکشنبه'}

MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 168
MAX_PROMPT_CHARS = 4000
MAX_NAME_CHARS = 120
STALE_RUN_SECONDS = 1800

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='assistant-automations')
_LOOP_LOCK = Lock()
_STOP = Event()
_THREAD = None


def ensure(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS assistant_automations(
        id SERIAL PRIMARY KEY,owner_user_id INT NOT NULL,name TEXT NOT NULL,prompt TEXT NOT NULL,
        schedule_type TEXT NOT NULL DEFAULT 'interval',interval_hours INT,daily_time TEXT,weekdays JSONB,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,next_run_at TIMESTAMPTZ,last_run_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS assistant_automation_runs(
        id SERIAL PRIMARY KEY,automation_id INT NOT NULL REFERENCES assistant_automations(id) ON DELETE CASCADE,
        status TEXT NOT NULL,summary TEXT,proposals JSONB,started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ)'''))


def _ceo(user):
    if not user or user.get('role') != 'ceo' or not user.get('id'):
        raise HTTPException(403, 'مدیریت اتوماسیون‌های خودکار فقط با حساب مدیرعامل است.')


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=MAX_NAME_CHARS)
    prompt: str = Field(min_length=5, max_length=MAX_PROMPT_CHARS)
    schedule_type: Literal['interval', 'daily'] = 'interval'
    interval_hours: int | None = Field(default=None, ge=MIN_INTERVAL_HOURS, le=MAX_INTERVAL_HOURS)
    daily_time: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    weekdays: list[int] | None = Field(default=None, description='0=دوشنبه … 6=یکشنبه (تقویم تهران)')

    @field_validator('weekdays')
    @classmethod
    def valid_weekdays(cls, value):
        if value is None:
            return None
        if not value or any(d not in WEEKDAY_LABELS for d in value):
            raise ValueError('روزهای هفته معتبر نیستند.')
        return sorted(set(value))


def _validate_schedule(data: AutomationCreate):
    if data.schedule_type == 'interval' and not data.interval_hours:
        raise HTTPException(422, 'برای زمان‌بندی فاصله‌ای، interval_hours لازم است.')
    if data.schedule_type == 'daily':
        if not data.daily_time:
            raise HTTPException(422, 'برای زمان‌بندی روزانه، daily_time مانند 08:30 لازم است.')
        if data.weekdays is None:
            data.weekdays = list(WEEKDAY_LABELS)


def compute_next_run(data: AutomationCreate, now: datetime | None = None) -> datetime:
    """Next due moment, in Tehran local time, returned timezone-aware."""
    now = now or iran_now()
    if data.schedule_type == 'interval':
        return now + timedelta(hours=data.interval_hours)
    hour, minute = (int(p) for p in (data.daily_time or '08:00').split(':'))
    allowed = set(data.weekdays if data.weekdays is not None else WEEKDAY_LABELS)
    # Python weekday(): Monday=0 … Sunday=6; WEEKDAY_LABELS follows the same order.
    for offset in range(1, 15):
        candidate = (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.weekday() in allowed and candidate > now:
            return candidate
    return now + timedelta(days=1)


def describe_schedule(data) -> str:
    if data.schedule_type == 'interval':
        return f"هر {data.interval_hours} ساعت"
    days = '،'.join(WEEKDAY_LABELS[d] for d in (data.weekdays or [])) or 'همهٔ روزها'
    return f"روزانه ساعت {data.daily_time} ({days})"


class AutomationUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=2, max_length=MAX_NAME_CHARS)
    prompt: str | None = Field(default=None, min_length=5, max_length=MAX_PROMPT_CHARS)
    enabled: bool | None = None
    schedule_type: Literal['interval', 'daily'] | None = None
    interval_hours: int | None = Field(default=None, ge=MIN_INTERVAL_HOURS, le=MAX_INTERVAL_HOURS)
    daily_time: str | None = Field(default=None, pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    weekdays: list[int] | None = None


def _merge_schedule(existing: dict, update: AutomationUpdate) -> AutomationCreate:
    merged = AutomationCreate(
        name=update.name if update.name is not None else existing['name'],
        prompt=update.prompt if update.prompt is not None else existing['prompt'],
        schedule_type=update.schedule_type or existing['schedule_type'],
        interval_hours=update.interval_hours if update.interval_hours is not None else existing['interval_hours'],
        daily_time=update.daily_time if update.daily_time is not None else existing['daily_time'],
        weekdays=update.weekdays if update.weekdays is not None else existing['weekdays'],
    )
    _validate_schedule(merged)
    return merged


def _row(row):
    return {'id': row['id'], 'name': row['name'], 'prompt': row['prompt'], 'enabled': row['enabled'],
            'schedule_type': row['schedule_type'], 'interval_hours': row['interval_hours'],
            'daily_time': row['daily_time'], 'weekdays': row['weekdays'], 'next_run_at': row['next_run_at'],
            'last_run_at': row['last_run_at'], 'created_at': row['created_at']}


@router.get('')
def list_automations(user: dict = Depends(current_user)):
    _ceo(user)
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text('SELECT * FROM assistant_automations WHERE owner_user_id=:o ORDER BY id'),
                            {'o': user['id']}).mappings().all()
        runs = conn.execute(text('''SELECT DISTINCT ON (automation_id) automation_id, status, finished_at
            FROM assistant_automation_runs ORDER BY automation_id, finished_at DESC NULLS LAST''')).mappings().all()
    last = {r['automation_id']: r for r in runs}
    return {'items': [{**_row(r), 'last_run': last.get(r['id'])} for r in rows]}


@router.post('')
def create_automation(data: AutomationCreate, user: dict = Depends(current_user)):
    _ceo(user)
    _validate_schedule(data)
    next_run = compute_next_run(data)
    with engine.begin() as conn:
        ensure(conn)
        row = conn.execute(text('''INSERT INTO assistant_automations
            (owner_user_id,name,prompt,schedule_type,interval_hours,daily_time,weekdays,next_run_at)
            VALUES(:o,:name,:prompt,:st,:ih,:dt,CAST(:wd AS JSONB),:next) RETURNING *'''),
            {'o': user['id'], 'name': data.name.strip(), 'prompt': data.prompt.strip(), 'st': data.schedule_type,
             'ih': data.interval_hours, 'dt': data.daily_time,
             'wd': json.dumps(data.weekdays) if data.weekdays is not None else None, 'next': next_run}).mappings().first()
    return {**_row(row), 'schedule_label': describe_schedule(data)}


@router.patch('/{automation_id}')
def update_automation(automation_id: int, data: AutomationUpdate, user: dict = Depends(current_user)):
    _ceo(user)
    with engine.begin() as conn:
        ensure(conn)
        existing = conn.execute(text('SELECT * FROM assistant_automations WHERE id=:id AND owner_user_id=:o'),
                                {'id': automation_id, 'o': user['id']}).mappings().first()
        if existing is None:
            raise HTTPException(404, 'اتوماسیون پیدا نشد.')
        merged = _merge_schedule(dict(existing), data)
        recompute = any(getattr(data, f) is not None for f in ('schedule_type', 'interval_hours', 'daily_time', 'weekdays'))
        next_run = compute_next_run(merged) if recompute else existing['next_run_at']
        row = conn.execute(text('''UPDATE assistant_automations SET name=:name,prompt=:prompt,
            schedule_type=:st,interval_hours=:ih,daily_time=:dt,weekdays=CAST(:wd AS JSONB),enabled=:en,next_run_at=:next
            WHERE id=:id RETURNING *'''),
            {'name': merged.name.strip(), 'prompt': merged.prompt.strip(), 'st': merged.schedule_type,
             'ih': merged.interval_hours, 'dt': merged.daily_time,
             'wd': json.dumps(merged.weekdays) if merged.weekdays is not None else None,
             'en': data.enabled if data.enabled is not None else existing['enabled'],
             'next': next_run, 'id': automation_id}).mappings().first()
    return _row(row)


@router.delete('/{automation_id}')
def delete_automation(automation_id: int, user: dict = Depends(current_user)):
    _ceo(user)
    with engine.begin() as conn:
        ensure(conn)
        deleted = conn.execute(text('DELETE FROM assistant_automations WHERE id=:id AND owner_user_id=:o RETURNING id'),
                               {'id': automation_id, 'o': user['id']}).scalar()
    if deleted is None:
        raise HTTPException(404, 'اتوماسیون پیدا نشد.')
    return {'status': 'deleted', 'id': automation_id}


@router.get('/{automation_id}/runs')
def list_runs(automation_id: int, user: dict = Depends(current_user), limit: int = 20):
    _ceo(user)
    with engine.connect() as conn:
        ensure(conn)
        owned = conn.execute(text('SELECT 1 FROM assistant_automations WHERE id=:id AND owner_user_id=:o'),
                             {'id': automation_id, 'o': user['id']}).scalar()
        if owned is None:
            raise HTTPException(404, 'اتوماسیون پیدا نشد.')
        rows = conn.execute(text('''SELECT id,status,summary,proposals,started_at,finished_at
            FROM assistant_automation_runs WHERE automation_id=:id ORDER BY started_at DESC LIMIT :l'''),
            {'id': automation_id, 'l': max(1, min(limit, 50))}).mappings().all()
    return {'items': [dict(r) for r in rows]}


AUTOMATION_FOOTER = (
    "\n\nاین یک اجرای خودکار زمان‌بندی‌شده است؛ خروجی باید یک خلاصهٔ کوتاه فارسی از شواهد واقعی باشد. "
    "اگر بر اساس داده‌ها یک اقدام نوشتنی لازم است، فقط با prepare_panel_operation پیشنهاد بساز؛ "
    "هیچ عملیاتی اجرا نمی‌شود و ادعای ثبت نکن. اگر داده کافی نیست، همان را صریح بگو."
)


def run_automation(automation_id: int, user: dict, trigger: str = 'scheduled') -> dict:
    """Execute one automation as the owner. Writes become proposals, never executions."""
    with engine.connect() as conn:
        ensure(conn)
        row = conn.execute(text('SELECT * FROM assistant_automations WHERE id=:id AND owner_user_id=:o'),
                           {'id': automation_id, 'o': user['id']}).mappings().first()
    if row is None:
        raise HTTPException(404, 'اتوماسیون پیدا نشد.')
    started = datetime.now(timezone.utc)
    status, summary, proposals = 'failed', None, []
    try:
        from assistant_engine import build_live_context, call_gpt
        with engine.connect() as conn:
            ctx = build_live_context(conn, user)
        ctx['_actor'] = user
        result = call_gpt(str(row['prompt']) + AUTOMATION_FOOTER, ctx, [], 'ceo', user.get('full_name'))
        if isinstance(result, dict):
            summary = result.get('answer') or ''
            if result.get('mode') == 'operation_preview' and result.get('action'):
                proposals = [{'label': result['action'].get('label'), 'href': result['action'].get('href')}]
        elif isinstance(result, str):
            summary = result
        else:
            summary = None
        status = 'completed' if summary else 'no_answer'
        if not summary:
            summary = 'مدل پاسخ معتبری تولید نکرد؛ نتیجه نامعلوم است.'
    except Exception:
        summary = 'اجرای خودکار خطا داشت؛ نتیجه نامعلوم است و باید دستی بررسی شود.'
    finished = datetime.now(timezone.utc)
    with engine.begin() as conn:
        ensure(conn)
        run_id = conn.execute(text('''INSERT INTO assistant_automation_runs
            (automation_id,status,summary,proposals,started_at,finished_at)
            VALUES(:a,:s,CAST(:sum AS TEXT),CAST(:pr AS JSONB),:st,:fin) RETURNING id'''),
            {'a': automation_id, 's': status, 'sum': summary, 'pr': json.dumps(proposals, ensure_ascii=False),
             'st': started, 'fin': finished}).scalar()
        conn.execute(text('UPDATE assistant_automations SET last_run_at=:fin WHERE id=:id'),
                     {'fin': finished, 'id': automation_id})
    return {'run_id': run_id, 'status': status, 'trigger': trigger, 'summary': summary, 'proposals': proposals}


@router.post('/{automation_id}/run')
def trigger_automation(automation_id: int, user: dict = Depends(current_user)):
    _ceo(user)
    return run_automation(automation_id, user, trigger='manual')


# ---------------------------------------------------------------- scheduler loop

def _testing_env():
    return any(k.startswith('KIARAD_TEST_') and v == '1' for k, v in os.environ.items())


def _due_and_claim(conn, automation_id):
    """Claim one due automation by bumping next_run_at atomically."""
    row = conn.execute(text('SELECT * FROM assistant_automations WHERE id=:id AND enabled'), {'id': automation_id}).mappings().first()
    if row is None:
        return None
    data = AutomationCreate(name=row['name'], prompt=row['prompt'], schedule_type=row['schedule_type'],
                            interval_hours=row['interval_hours'], daily_time=row['daily_time'], weekdays=row['weekdays'])
    _validate_schedule(data)
    next_run = compute_next_run(data)
    claimed = conn.execute(text('''UPDATE assistant_automations SET next_run_at=:next
        WHERE id=:id AND next_run_at IS NOT DISTINCT FROM :expected RETURNING id'''),
        {'next': next_run, 'id': automation_id, 'expected': row['next_run_at']}).scalar()
    return dict(row) if claimed is not None else None


def _run_due(automation_id: int):
    with engine.begin() as conn:
        ensure(conn)
        row = _due_and_claim(conn, automation_id)
    if row is None:
        return
    try:
        owner = conn_owner(row['owner_user_id'])
    except Exception:
        return
    if owner is None:
        with engine.begin() as conn:
            conn.execute(text("UPDATE assistant_automations SET enabled=FALSE WHERE id=:id"), {'id': automation_id})
        return
    try:
        run_automation(automation_id, owner, trigger='scheduled')
    except Exception:
        pass


def conn_owner(owner_user_id: int):
    with engine.connect() as conn:
        row = conn.execute(text('''SELECT id, username, full_name, role, salesperson_id, is_active, password_version
            FROM users WHERE id=:id AND is_active::text IN ('1','true','t')'''), {'id': owner_user_id}).mappings().first()
    return dict(row) if row else None


def _scheduler_loop():
    while not _STOP.is_set():
        try:
            with engine.connect() as conn:
                ensure(conn)
                due = [r[0] for r in conn.execute(text(
                    '''SELECT id FROM assistant_automations
                       WHERE enabled AND next_run_at IS NOT NULL AND next_run_at<=NOW() LIMIT 5''')).all()]
            for automation_id in due:
                if _STOP.is_set():
                    break
                try:
                    _run_due(automation_id)
                except Exception:
                    continue
        except Exception:
            pass
        _STOP.wait(60)


def start_automations_scheduler():
    global _THREAD
    if _testing_env() or os.getenv('KIARAD_AUTOMATIONS_DISABLED', '') in {'1', 'true', 'yes'}:
        return {'enabled': False}
    with _LOOP_LOCK:
        if _THREAD and _THREAD.is_alive():
            return {'enabled': True, 'already_running': True}
        _STOP.clear()
        _THREAD = Thread(target=_scheduler_loop, daemon=True, name='assistant-automations')
        try:
            _THREAD.start()
        except Exception:
            return {'enabled': False}
        return {'enabled': True}


def stop_automations_scheduler():
    _STOP.set()
    with _LOOP_LOCK:
        if _THREAD:
            _THREAD.join(timeout=2)


# ------------------------------------------------- dynamic notification hooks

def notification_items(conn, user) -> list:
    """Notifications derived from automation runs, in the shared item format.

    Uses its own connection: a failure here must never abort the caller's
    transaction (Postgres aborts the whole transaction on any SQL error).
    """
    items = []
    try:
        with engine.connect() as own:
            ensure(own)
            rows = own.execute(text('''SELECT a.id, a.name,
                    (SELECT status FROM assistant_automation_runs r WHERE r.automation_id=a.id
                     ORDER BY started_at DESC LIMIT 1) AS last_status,
                    (SELECT COUNT(*) FROM assistant_operation_proposals p
                     WHERE p.actor_id=:o AND p.status='preview' AND p.expires_at>NOW()
                       AND p.created_at > NOW() - INTERVAL '7 days') AS pending_proposals
                FROM assistant_automations a WHERE a.owner_user_id=:o AND a.enabled'''),
                {'o': user['id']}).mappings().all()
        for r in rows:
            if r['last_status'] == 'failed':
                items.append({'key': f'automation:failed:{r["id"]}', 'kind': 'assistant', 'severity': 'warning',
                              'title': f'اجرای خودکار «{r["name"]}» ناموفق بود',
                              'message': 'آخرین اجرای این اتوماسیون خطا داشت؛ نتیجه نامعلوم است.',
                              'href': '/assistant-automations'})
            elif r['last_status'] == 'completed' and r['pending_proposals']:
                items.append({'key': f'automation:proposals:{r["id"]}', 'kind': 'assistant', 'severity': 'info',
                              'title': f'پیشنهاد از اجرای خودکار «{r["name"]}»',
                              'message': f"{r['pending_proposals']} پیشنهاد در انتظار تأیید شماست.",
                              'href': '/assistant-actions'})
    except Exception:
        return []
    return items
