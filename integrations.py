"""Connection preparation and evidence-based channel status.

No credentials are accepted here and saving a draft never enables a sync.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, func, select, text

from db import engine
from operations import current_user, require_manager

router = APIRouter(prefix="/integrations", tags=["integrations"])

CHANNELS = {
    "digikala": ("دیجی‌کالا", "فروش"),
    "basalam": ("باسلام", "فروش"),
    "snappshop": ("اسنپ‌شاپ", "فروش"),
    "isam": ("ایسام", "فروش"),
    "divar": ("دیوار", "آگهی"),
    "emalls": ("ایمالز", "مقایسهٔ قیمت"),
    "torob": ("ترب", "مقایسهٔ قیمت"),
    "instagram": ("اینستاگرام", "شبکهٔ اجتماعی"),
    "youtube": ("یوتیوب", "شبکهٔ اجتماعی"),
    "tiktok": ("تیک‌تاک", "شبکهٔ اجتماعی"),
    "linkedin": ("لینکدین", "شبکهٔ اجتماعی"),
    "telegram": ("تلگرام", "پیام‌رسان"),
    "bale": ("بله", "پیام‌رسان"),
    "rubika": ("روبیکا", "پیام‌رسان"),
    "whatsapp": ("واتس‌اپ", "پیام‌رسان"),
}

metadata = MetaData()
drafts = Table(
    "integration_drafts", metadata,
    Column("channel", String(40), primary_key=True),
    Column("account_label", String(160), nullable=False, default=""),
    Column("notes", Text, nullable=False, default=""),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
content_calendar = Table(
    "social_content_calendar", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("channel", String(40), nullable=False),
    Column("title", String(200), nullable=False),
    Column("body", Text, nullable=False),
    Column("scheduled_at", DateTime(timezone=True), nullable=False),
    Column("status", String(20), nullable=False, default="pending"),
    Column("created_by", Integer, nullable=False),
    Column("reviewed_by", Integer),
    Column("review_note", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("reviewed_at", DateTime(timezone=True)),
)

CONTENT_CHANNELS = {"instagram", "youtube", "tiktok", "linkedin", "telegram", "bale", "rubika", "whatsapp"}


def ensure_table():
    metadata.create_all(engine, tables=[drafts, content_calendar], checkfirst=True)
    with engine.begin() as conn:
        migrate_draft_schema(conn)
        conn.execute(text('''CREATE TABLE IF NOT EXISTS integration_connection_checks (
            channel TEXT PRIMARY KEY,status TEXT NOT NULL,http_status INT,
            checked_at TIMESTAMPTZ NOT NULL,checked_by INT NOT NULL)'''))


def migrate_draft_schema(conn):
    """Preserve existing legacy public identifiers when upgrading a draft table."""
    had_label = conn.execute(text("""SELECT EXISTS (SELECT 1 FROM pg_attribute
        WHERE attrelid='integration_drafts'::regclass AND attname='account_label' AND NOT attisdropped)""")).scalar()
    conn.execute(text("ALTER TABLE integration_drafts ADD COLUMN IF NOT EXISTS account_label VARCHAR(160) NOT NULL DEFAULT ''"))
    legacy = conn.execute(text("""SELECT EXISTS (SELECT 1 FROM pg_attribute
        WHERE attrelid='integration_drafts'::regclass AND attname='public_identifier' AND NOT attisdropped)""")).scalar()
    if legacy:
        if not had_label:
            conn.execute(text("""UPDATE integration_drafts SET account_label=COALESCE(public_identifier,'')
                WHERE account_label='' AND COALESCE(public_identifier,'')<>''"""))
        conn.execute(text("ALTER TABLE integration_drafts ALTER COLUMN public_identifier SET DEFAULT ''"))


def channel_status(channel: str, draft: Optional[dict], sync: Optional[dict], mapped: int, check:Optional[dict]=None):
    last_success = sync.get("last_success") if sync else None
    age=(datetime.now(timezone.utc)-check['checked_at']).total_seconds() if check else None
    fresh=age is not None and -60<=age<=600
    return {
        "id": channel,
        "label": CHANNELS[channel][0],
        "kind": CHANNELS[channel][1],
        "account_label": draft["account_label"] if draft else "",
        "notes": draft["notes"] if draft else "",
        "prepared_at": draft["updated_at"] if draft else None,
        "last_sync_at": last_success,
        "last_attempt_at": sync.get("last_attempt") if sync else None,
        "last_attempt_status": sync.get("last_status") if sync else None,
        "mapped_products": mapped,
        # A draft, token file, or legacy script alone is not proof of a live connector.
        "connected": bool(check and check['status']=='verified' and fresh),
        "connection_check_status": check['status'] if check else 'not_checked',
        "connection_checked_at": check['checked_at'] if check else None,
        "connection_check_fresh": fresh,
        "connection_http_status": check.get('http_status') if check else None,
        "sync_enabled": False,
        "stock_push_enabled": False,
        "price_push_enabled": False,
    }


@router.get("")
def list_integrations(_: dict = Depends(require_manager)):
    with engine.connect() as conn:
        saved = {r["channel"]: dict(r) for r in conn.execute(select(drafts)).mappings()}
        sync_rows = conn.execute(text("""
            SELECT channel,
                   max(started_at) AS last_attempt,
                   (array_agg(status ORDER BY started_at DESC))[1] AS last_status,
                   max(finished_at) FILTER (WHERE status = 'success') AS last_success
            FROM sync_runs GROUP BY channel
        """)).mappings().all()
        sync = {r["channel"]: dict(r) for r in sync_rows}
        mapping_rows = conn.execute(text(
            "SELECT channel, count(*) AS n FROM product_channels GROUP BY channel"
        )).mappings().all()
        mappings = {r["channel"]: r["n"] for r in mapping_rows}
        checks={r['channel']:dict(r) for r in conn.execute(text('SELECT * FROM integration_connection_checks')).mappings()}
    return [channel_status(c, saved.get(c), sync.get(c), mappings.get(c, 0),checks.get(c)) for c in CHANNELS]


def probe_digikala():
    """Only the configured vendor profile is read; no order/stock/price mutations."""
    import requests
    from digikala_api import DigikalaClient
    try:
        client=DigikalaClient()
        response=client.get_profile()
        code=response.status_code
        if code in (401,403):return {'status':'authentication_failed','http_status':code}
        if code!=200:return {'status':'endpoint_error','http_status':code}
        body=response.json()
        payload=body.get('data') if isinstance(body,dict) else None
        status=body.get('status') if isinstance(body,dict) else None
        valid_status=status in ('ok','success',200,'200',True)
        profile=payload.get('profile',payload) if isinstance(payload,dict) else None
        identity=any(profile.get(key) not in (None,'') for key in ('id','seller_id','seller_code','business_name','name','shop_name')) if isinstance(profile,dict) else False
        if not valid_status or not identity or body.get('error') or body.get('errors'):
            return {'status':'unverified_response','http_status':code}
        return {'status':'verified','http_status':code}
    except FileNotFoundError:return {'status':'credentials_missing','http_status':None}
    except requests.HTTPError as exc:return {'status':'authentication_failed','http_status':exc.response.status_code if exc.response is not None else None}
    except requests.RequestException:return {'status':'network_error','http_status':None}
    except (ValueError,KeyError,TypeError):return {'status':'credentials_or_response_invalid','http_status':None}


@router.post('/digikala/check')
def check_digikala(user:dict=Depends(require_manager)):
    result=probe_digikala();checked=datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text('''INSERT INTO integration_connection_checks(channel,status,http_status,checked_at,checked_by)
            VALUES('digikala',:s,:h,:at,:u) ON CONFLICT(channel) DO UPDATE SET
            status=EXCLUDED.status,http_status=EXCLUDED.http_status,checked_at=EXCLUDED.checked_at,checked_by=EXCLUDED.checked_by'''),
            {'s':result['status'],'h':result['http_status'],'at':checked,'u':user['id']})
    return {**result,'checked_at':checked,'read_only':True,'price_push_enabled':False,'stock_push_enabled':False}


class DraftInput(BaseModel):
    account_label: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=1000)


class ContentDraftInput(BaseModel):
    channel: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    scheduled_at: datetime


class ContentReviewInput(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(default="", max_length=1000)


@router.get("/content-calendar")
def list_content_calendar(user: dict = Depends(current_user)):
    query = select(content_calendar).order_by(content_calendar.c.scheduled_at, content_calendar.c.id)
    if user.get("role") not in {"ceo", "sales_manager"}:
        query = query.where(content_calendar.c.created_by == int(user["id"]))
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    return {"items": [dict(row) for row in rows], "can_review": user.get("role") in {"ceo", "sales_manager"}, "publishing_enabled": False}


@router.post("/content-calendar")
def create_content_draft(data: ContentDraftInput, user: dict = Depends(current_user)):
    if data.channel not in CONTENT_CHANNELS:
        raise HTTPException(status_code=422, detail="کانال محتوایی پشتیبانی نمی‌شود.")
    if not data.title.strip() or not data.body.strip():
        raise HTTPException(status_code=422, detail="عنوان و متن پیش‌نویس نمی‌تواند خالی باشد.")
    if data.scheduled_at.tzinfo is None or data.scheduled_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="زمان انتشار باید با منطقهٔ زمانی صریح ارسال شود.")
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        row = conn.execute(content_calendar.insert().values(
            channel=data.channel, title=data.title.strip(), body=data.body.strip(),
            scheduled_at=data.scheduled_at.astimezone(timezone.utc), status="pending",
            created_by=int(user["id"]), created_at=now,
        ).returning(content_calendar.c.id, content_calendar.c.status, content_calendar.c.scheduled_at)).mappings().one()
    return {"item": dict(row), "publishing_enabled": False}


@router.post("/content-calendar/{item_id}/review")
def review_content_draft(item_id: int, data: ContentReviewInput,
                         user: dict = Depends(require_manager)):
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        row = conn.execute(select(content_calendar.c.status).where(content_calendar.c.id == item_id).with_for_update()).first()
        if not row:
            raise HTTPException(status_code=404, detail="پیش‌نویس محتوا پیدا نشد.")
        if row[0] != "pending":
            raise HTTPException(status_code=409, detail="این پیش‌نویس قبلاً بررسی شده است.")
        conn.execute(content_calendar.update().where(content_calendar.c.id == item_id).values(
            status=data.decision, reviewed_by=int(user["id"]), reviewed_at=now,
            review_note=data.note.strip(),
        ))
    return {"id": item_id, "status": data.decision, "publishing_enabled": False}


@router.put("/{channel}/draft")
def save_draft(channel: str, data: DraftInput, _: dict = Depends(require_manager)):
    if channel not in CHANNELS:
        raise HTTPException(status_code=404, detail="Unknown channel")
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        existing = conn.execute(select(drafts.c.channel).where(drafts.c.channel == channel)).first()
        values = {"account_label": data.account_label.strip(), "notes": data.notes.strip(), "updated_at": now}
        if existing:
            conn.execute(drafts.update().where(drafts.c.channel == channel).values(**values))
        else:
            conn.execute(drafts.insert().values(channel=channel, **values))
    return {"saved": True, "connected": False, "sync_enabled": False}
