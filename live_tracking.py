"""Authenticated, shift-scoped mobile location ingestion. GPS is evidence, not payroll."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from db import engine
from iran_time import IRAN_TIMEZONE, iran_today
from operations import current_user, MANAGER_ROLES, role_has_module_permission

router = APIRouter(prefix='/tracking', tags=['live_tracking'])
STALE_SECONDS = 120


def ensure(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS tracking_sessions(
        id UUID PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),device_id TEXT NOT NULL,
        platform TEXT NOT NULL,started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL,ended_at TIMESTAMPTZ,consent_version TEXT NOT NULL,
        last_upload_at TIMESTAMPTZ,last_device_status TEXT NOT NULL DEFAULT 'starting',source TEXT NOT NULL DEFAULT 'kiarad')'''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS tracking_sessions_owner_time ON tracking_sessions(user_id,started_at DESC)'))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS tracking_points(
        id BIGSERIAL PRIMARY KEY,session_id UUID NOT NULL REFERENCES tracking_sessions(id),
        event_id UUID NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),
        recorded_at TIMESTAMPTZ NOT NULL,received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        latitude DOUBLE PRECISION NOT NULL,longitude DOUBLE PRECISION NOT NULL,
        accuracy_m DOUBLE PRECISION NOT NULL,speed_mps DOUBLE PRECISION,battery_level DOUBLE PRECISION,
        mocked BOOLEAN,UNIQUE(session_id,event_id))'''))
    conn.execute(text('CREATE INDEX IF NOT EXISTS tracking_points_owner_time ON tracking_points(user_id,recorded_at DESC,id DESC)'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS tracking_points_session_time ON tracking_points(session_id,recorded_at DESC)'))


@router.on_event('startup')
def startup():
    with engine.begin() as conn:
        ensure(conn)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Start(Strict):
    device_id: str = Field(min_length=8, max_length=120)
    platform: Literal['android', 'ios', 'web']
    consent_version: Literal['work-shift-location-v1']
    max_hours: int = Field(default=8, ge=1, le=12)


class Sample(Strict):
    event_id: UUID
    recorded_at: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float = Field(gt=0, le=50000)
    speed_mps: float | None = Field(default=None, ge=0, le=100)
    battery_level: float | None = Field(default=None, ge=0, le=1)
    mocked: bool | None = None

    @field_validator('recorded_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Timestamp must include a timezone')
        return value


class Upload(Strict):
    session_id: UUID
    device_id: str = Field(min_length=8, max_length=120)
    samples: list[Sample] = Field(min_length=1, max_length=100)


class Heartbeat(Strict):
    session_id: UUID
    device_id: str = Field(min_length=8, max_length=120)
    status: Literal['tracking', 'permission_denied', 'gps_disabled', 'offline_queue', 'stopping']


class Stop(Strict):
    session_id: UUID
    device_id: str = Field(min_length=8, max_length=120)


def require_map_permission(user, action):
    if not role_has_module_permission(str(user.get('role', '')), 'map', action):
        raise HTTPException(403, 'برای این عملیات دسترسی ماژول نقشه فعال نیست.')


def staff(user):
    if not user.get('id') or not user.get('salesperson_id'):
        raise HTTPException(403, 'ردیابی شیفت به حساب پرسنلی متصل نیاز دارد.')
    # Enforce the same map-module grant for native GPS as for Traccar.
    # A revoked grant must stop new sessions, heartbeats and point uploads.
    require_map_permission(user, 'can_write')


def own_session(conn, session_id, device_id, user, lock=False):
    row = conn.execute(text('SELECT * FROM tracking_sessions WHERE id=:id AND user_id=:uid' + (' FOR UPDATE' if lock else '')),
                       {'id': str(session_id), 'uid': user['id']}).mappings().first()
    if not row or row['device_id'] != device_id:
        raise HTTPException(404, 'نشست ردیابی متعلق به این حساب و دستگاه نیست.')
    return row


@router.post('/sessions', status_code=201)
def start_session(data: Start, user=Depends(current_user)):
    staff(user)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        return start_session_in_connection(conn,data,user,now=now)


def start_session_in_connection(conn,data,user,*,now=None):
    staff(user);now=now or datetime.now(timezone.utc)
    conn.execute(text('SELECT pg_advisory_xact_lock(819731,:uid)'), {'uid': user['id']})
    existing = conn.execute(text('''SELECT * FROM tracking_sessions WHERE user_id=:uid
        AND ended_at IS NULL AND expires_at>NOW() ORDER BY started_at DESC FOR UPDATE'''), {'uid': user['id']}).mappings().first()
    if existing:
        if existing['device_id'] != data.device_id:
            raise HTTPException(409, 'ردیابی روی دستگاه دیگری فعال است؛ ابتدا همان نشست را پایان دهید.')
        return {'session_id': str(existing['id']), 'expires_at': existing['expires_at'], 'reused': True, 'sample_interval_seconds': 30}
    ident = str(uuid4())
    expires = now + timedelta(hours=data.max_hours)
    conn.execute(text('''INSERT INTO tracking_sessions(id,user_id,device_id,platform,expires_at,consent_version)
        VALUES (:id,:uid,:device,:platform,:expires,:consent)'''),
        dict(id=ident, uid=user['id'], device=data.device_id, platform=data.platform, expires=expires, consent=data.consent_version))
    return {'session_id': ident, 'expires_at': expires, 'reused': False, 'sample_interval_seconds': 30,
            'continuous_delivery_guaranteed': False, 'purpose': 'work_shift_location_only'}


@router.post('/locations')
def upload(data: Upload, user=Depends(current_user)):
    staff(user)
    now = datetime.now(timezone.utc)
    accepted = []
    with engine.begin() as conn:
        session = own_session(conn, data.session_id, data.device_id, user, True)
        for sample in data.samples:
            timestamp = sample.recorded_at.astimezone(timezone.utc)
            end = min(session['expires_at'], session['ended_at'] or now + timedelta(seconds=90))
            if timestamp < session['started_at'] - timedelta(seconds=5) or timestamp > end or timestamp < now - timedelta(days=7):
                raise HTTPException(422, 'زمان موقعیت خارج از شیفت یا مهلت ارسال آفلاین است.')
            if timestamp > now + timedelta(seconds=90):
                raise HTTPException(422, 'ساعت دستگاه معتبر نیست.')
            conn.execute(text('''INSERT INTO tracking_points(session_id,event_id,user_id,recorded_at,latitude,longitude,
                accuracy_m,speed_mps,battery_level,mocked) VALUES(:session,:event,:uid,:at,:lat,:lng,:accuracy,:speed,:battery,:mocked)
                ON CONFLICT(session_id,event_id) DO NOTHING'''),
                dict(session=str(data.session_id), event=str(sample.event_id), uid=user['id'], at=timestamp,
                     lat=sample.latitude, lng=sample.longitude, accuracy=sample.accuracy_m,
                     speed=sample.speed_mps, battery=sample.battery_level, mocked=sample.mocked))
            accepted.append(str(sample.event_id))
        conn.execute(text("UPDATE tracking_sessions SET last_upload_at=NOW(),last_device_status='tracking' WHERE id=:id"), {'id': str(data.session_id)})
    return {'accepted_event_ids': accepted, 'received_at': now, 'offline_backfill_is_not_live': True}


@router.post('/heartbeat')
def heartbeat(data: Heartbeat, user=Depends(current_user)):
    staff(user)
    with engine.begin() as conn:
        row = own_session(conn, data.session_id, data.device_id, user, True)
        if row['ended_at'] or row['expires_at'] <= datetime.now(timezone.utc):
            raise HTTPException(409, 'نشست ردیابی پایان یافته است.')
        conn.execute(text('UPDATE tracking_sessions SET last_upload_at=NOW(),last_device_status=:s WHERE id=:id'),
                     {'s': data.status, 'id': str(data.session_id)})
    return {'ok': True}


@router.post('/sessions/stop')
def stop_session(data: Stop, user=Depends(current_user)):
    with engine.begin() as conn:
        row = own_session(conn, data.session_id, data.device_id, user, True)
        conn.execute(text("UPDATE tracking_sessions SET ended_at=COALESCE(ended_at,NOW()),last_device_status='stopped' WHERE id=:id"), {'id': str(data.session_id)})
    return {'ok': True, 'already_stopped': row['ended_at'] is not None}


def freshness(point, now=None):
    now = now or datetime.now(timezone.utc)
    if not point or point.get('recorded_at') is None:
        return {'state': 'no_fix', 'age_seconds': None, 'is_live': False}
    age = max(0, int((now - point['recorded_at']).total_seconds()))
    state = 'possible_mock' if point.get('mocked') else 'approximate' if point['accuracy_m'] > 100 else 'live' if age <= STALE_SECONDS else 'stale'
    return {'state': state, 'age_seconds': age, 'is_live': state == 'live', 'stale': age > STALE_SECONDS}


@router.get('/live')
def live(user=Depends(current_user)):
    require_map_permission(user, 'can_read')
    manager = user.get('role') in MANAGER_ROLES
    with engine.connect() as conn:
        rows = conn.execute(text('''SELECT u.id AS user_id,u.full_name,u.salesperson_id,
            s.id AS session_id,s.started_at,s.expires_at,s.last_upload_at,s.last_device_status,s.source,
            p.recorded_at,p.received_at,p.latitude,p.longitude,p.accuracy_m,p.mocked,p.battery_level
            FROM users u
            LEFT JOIN LATERAL (SELECT * FROM tracking_sessions WHERE user_id=u.id AND ended_at IS NULL
                AND expires_at>NOW() ORDER BY started_at DESC LIMIT 1) s ON TRUE
            LEFT JOIN LATERAL (SELECT * FROM tracking_points WHERE session_id=s.id
                ORDER BY recorded_at DESC,id DESC LIMIT 1) p ON TRUE
            WHERE u.is_active::text IN ('1','true','t') AND u.salesperson_id IS NOT NULL
            AND (:manager OR u.id=:uid) ORDER BY u.full_name'''), {'manager': manager, 'uid': user['id']}).mappings().all()
    now = datetime.now(timezone.utc)
    return {'as_of': now, 'stale_after_seconds': STALE_SECONDS, 'items': [dict(row) | freshness(row, now) for row in rows],
            'basis': 'consented_shift_samples; not verified visits or payroll'}


@router.get('/history')
def history(user_id: int, day: date | None = None, user=Depends(current_user)):
    require_map_permission(user, 'can_read')
    if user.get('role') not in MANAGER_ROLES and user_id != user['id']:
        raise HTTPException(403, 'فقط مسیر کاری خودتان را می‌توانید بخوانید.')
    day = day or iran_today()
    if day < iran_today() - timedelta(days=30) or day > iran_today():
        raise HTTPException(422, 'روز باید در سی روز گذشته باشد.')
    begin = datetime.combine(day, time.min, IRAN_TIMEZONE)
    with engine.connect() as conn:
        rows = conn.execute(text('''SELECT recorded_at,received_at,latitude,longitude,accuracy_m,mocked,session_id
            FROM tracking_points WHERE user_id=:uid AND recorded_at>=:begin AND recorded_at<:end
            ORDER BY recorded_at,id LIMIT 5001'''), {'uid': user_id, 'begin': begin, 'end': begin + timedelta(days=1)}).mappings().all()
    return {'items': [dict(row) for row in rows[:5000]], 'truncated': len(rows) > 5000, 'day': day, 'not_a_payroll_verdict': True}
