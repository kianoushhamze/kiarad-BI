"""Social channel connection infrastructure: store per-channel credentials,
run an honest connection test (real check only for Telegram for now), and
scaffold future publishing. Credentials are never returned in plaintext —
only key names with a masked preview.

Gate: online-sales manager (ceo or can_write on online-sales), same as
the /platforms routers.
"""
import json
import logging

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from db import engine
from operations import current_user, role_has_module_permission

logger = logging.getLogger("kiarad_social_connect")
router = APIRouter(prefix="/social-connect", tags=["social_connect"])

PLATFORMS = ["instagram", "telegram", "bale", "rubika", "youtube", "linkedin", "tiktok", "whatsapp"]

NOT_IMPLEMENTED_MESSAGE = "اتصال این کانال پس از فعال‌سازی API رسمی آن اضافه می‌شود"


def ensure(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS social_channels(
        platform TEXT PRIMARY KEY, credentials JSONB NOT NULL DEFAULT '{}'::jsonb,
        status TEXT NOT NULL DEFAULT 'disconnected',
        last_checked_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))


def _require_manager(user):
    if user.get("role") != "ceo" and not role_has_module_permission(str(user.get("role", "")), "online-sales", "can_write"):
        raise HTTPException(403, "مدیریت اتصال شبکه‌های اجتماعی فقط برای مدیر فروش آنلاین است.")


def _load_channel(conn, platform: str):
    if platform not in PLATFORMS:
        raise HTTPException(404, "پلتفرم نامعتبر است.")
    row = conn.execute(text("SELECT * FROM social_channels WHERE platform=:p"), {"p": platform}).mappings().first()
    return dict(row) if row else None


def _mask(value: str) -> str:
    value = str(value)
    return "•••" + value[-4:] if len(value) >= 4 else "•••"


def _credential_summary(credentials: dict) -> dict:
    return {key: _mask(value) for key, value in credentials.items() if str(value).strip()}


class CredentialsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credentials: dict[str, str]


@router.get("/channels")
def list_channels(user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.connect() as conn:
        ensure(conn)
        rows = conn.execute(text("SELECT * FROM social_channels ORDER BY platform")).mappings().all()
    by_platform = {r["platform"]: r for r in rows}
    channels = []
    for platform in PLATFORMS:
        row = by_platform.get(platform)
        credentials = (row.get("credentials") or {}) if row else {}
        channels.append({
            "platform": platform,
            "status": row["status"] if row else "disconnected",
            "configured": bool(credentials),
            "last_checked_at": row["last_checked_at"] if row else None,
            "credentials": _credential_summary(credentials),
        })
    return {"channels": channels}


@router.put("/channels/{platform}")
def save_credentials(platform: str, data: CredentialsPayload, user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        _load_channel(conn, platform)
        conn.execute(text("""
            INSERT INTO social_channels(platform, credentials, status, updated_at)
            VALUES (:p, CAST(:c AS JSONB), 'disconnected', NOW())
            ON CONFLICT (platform) DO UPDATE SET credentials=CAST(:c AS JSONB),
                status='disconnected', updated_at=NOW()
        """), {"p": platform, "c": json.dumps(data.credentials, ensure_ascii=False)})
    return {"ok": True, "platform": platform, "status": "disconnected"}


def _test_telegram(credentials: dict) -> dict:
    token = str(credentials.get("bot_token") or credentials.get("token") or "").strip()
    if not token:
        return {"status": "error", "message": "bot_token ذخیره نشده است."}
    import re
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{30,}", token):
        return {"status": "error", "message": "شکل توکن ربات تلگرام معتبر نیست (123456:ABC-...)."}
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10, trust_env=False,
        )
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code == 200 and payload.get("ok"):
            bot = payload.get("result", {})
            return {"status": "connected", "message": f"اتصال موفق: @{bot.get('username', '')}"}
        return {"status": "error", "message": f"تلگرام توکن را نپذیرفت (کد {resp.status_code})."}
    except requests.RequestException as exc:
        return {"status": "error", "message": f"خطای شبکه در تماس با تلگرام: {exc}"}


@router.post("/channels/{platform}/test")
def test_channel(platform: str, user: dict = Depends(current_user)):
    _require_manager(user)
    with engine.begin() as conn:
        ensure(conn)
        row = _load_channel(conn, platform)
        credentials = (row.get("credentials") or {}) if row else {}
        if not credentials:
            raise HTTPException(400, "ابتدا اعتبارنامهٔ این کانال را ذخیره کنید.")
        if platform == "telegram":
            result = _test_telegram(credentials)
        else:
            # Honest placeholder: no official API integration exists yet.
            result = {"status": "not_implemented", "message": NOT_IMPLEMENTED_MESSAGE}
        conn.execute(text("""
            UPDATE social_channels SET status=:s, last_checked_at=NOW() WHERE platform=:p
        """), {"s": result["status"] if result["status"] in {"connected", "error"} else row["status"] if row else "disconnected", "p": platform})
    return {"platform": platform, **result}


@router.post("/publish/{platform}")
def publish(platform: str, body: dict, user: dict = Depends(current_user)):
    _require_manager(user)
    draft_id = body.get("draft_id")
    if not draft_id:
        raise HTTPException(400, "شناسهٔ پیش‌نویس محتوا (draft_id) لازم است.")
    with engine.connect() as conn:
        ensure(conn)
        row = _load_channel(conn, platform)
        status = row["status"] if row else "disconnected"
        if status != "connected":
            raise HTTPException(409, f"کانال «{platform}» متصل نیست؛ ابتدا اعتبارنامه را ذخیره و تست کنید.")
        draft = conn.execute(text(
            "SELECT id, channel, title FROM social_content_calendar WHERE id=:i"
        ), {"i": draft_id}).mappings().first()
    if not draft:
        raise HTTPException(404, "پیش‌نویس محتوا با این شناسه پیدا نشد.")
    # Connected, but no real publisher for any channel is implemented yet.
    logger.info("social publish requested: platform=%s draft=%s user=%s", platform, draft_id, user.get("id"))
    raise HTTPException(501, "انتشار خودکار برای این کانال هنوز پیاده‌سازی نشده است؛ انتشار فعلاً دستی است.")
