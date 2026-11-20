"""ثبت‌نام و ورود مشتری سایت (site customer auth) — ایمیل یا موبایل + رمز.

 جدا از حساب‌های کارمندی (operations): توکن JWT با role='site_customer'
 صادر می‌شود و فقط برای مسیرهای /site-auth/me و آیندهٔ سفارش/قیمت پلکانی
 معتبر است. Google OAuth بعداً با اعتبارنامهٔ Google قابل افزودن است.
"""
import hashlib
import hmac
import ipaddress
import os
import re
from itertools import count
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from operations import hash_password, verify_password

router = APIRouter(prefix="/site-auth", tags=["site_auth"])

SITE_CUSTOMER_ROLE = "site_customer"
TOKEN_DAYS = 7

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^09\d{9}$")


_RATE_LIMITS = {
    "login": (10, 15 * 60),
    "register": (5, 60 * 60),
}
_RATE_LIMIT_CLEANUP_COUNTER = count(1)


def _trusted_proxy_networks():
    raw = os.getenv("KIARAD_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return ()
    try:
        return tuple(
            ipaddress.ip_network(item.strip(), strict=False)
            for item in raw.split(",")
            if item.strip()
        )
    except ValueError:
        raise HTTPException(503, "KIARAD_TRUSTED_PROXY_CIDRS contains an invalid network.")


def _parse_ip(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except (AttributeError, ValueError):
        return None


def _is_trusted_proxy(address, networks) -> bool:
    return any(address in network for network in networks)


def _client_ip(request: Request) -> str:
    """Use forwarded headers only when the immediate TCP peer is explicitly trusted."""
    peer = _parse_ip(request.client.host if request.client else None)
    if peer is None:
        raise HTTPException(503, "Client address is unavailable; rate limiting cannot be enforced.")

    networks = _trusted_proxy_networks()
    if not _is_trusted_proxy(peer, networks):
        return peer.compressed

    cloudflare_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cloudflare_ip and "," not in cloudflare_ip:
        parsed = _parse_ip(cloudflare_ip)
        if parsed is not None:
            return parsed.compressed

    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        forwarded = [_parse_ip(item) for item in forwarded_for.split(",")]
        if all(item is not None for item in forwarded):
            # Walk from the trusted peer toward the client. The first untrusted
            # address is the client as observed by the trusted proxy chain.
            for address in reversed(forwarded + [peer]):
                if not _is_trusted_proxy(address, networks):
                    return address.compressed

    return peer.compressed



def _normalize_contact(contact: str) -> tuple[Optional[str], Optional[str]]:
    """Return (email, phone); contact is auto-detected (@ → email, else 09xx mobile)."""
    value = contact.strip()
    if "@" in value:
        email = value.lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(400, "ایمیل واردشده معتبر نیست.")
        return email, None
    phone = re.sub(r"[\s\-()]", "", value)
    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    elif phone.startswith("98") and len(phone) == 12:
        phone = "0" + phone[2:]
    elif len(phone) == 10 and phone.startswith("9"):
        phone = "0" + phone
    if not _PHONE_RE.match(phone):
        raise HTTPException(400, "شماره موبایل باید به شکل 09xxxxxxxxx باشد یا ایمیل معتبر وارد کنید.")
    return None, phone


def _secret() -> str:
    secret = os.getenv("KIARAD_JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "KIARAD_JWT_SECRET must be configured with at least 32 characters.")
    return secret


def _consume_rate_limit(request: Request, action: str) -> int:
    """Atomically consume a shared PostgreSQL IP bucket; return Retry-After seconds."""
    try:
        max_attempts, window_seconds = _RATE_LIMITS[action]
    except KeyError:
        raise ValueError("Unknown site-auth rate-limit action")

    client_ip = _client_ip(request)
    bucket_key = hmac.new(
        _secret().encode("utf-8"),
        f"site-auth:{action}:{client_ip}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO site_auth_rate_limits (
                bucket_key, window_started_at, attempts, updated_at
            )
            VALUES (:bucket_key, NOW(), 1, NOW())
            ON CONFLICT (bucket_key) DO UPDATE
            SET
                window_started_at = CASE
                    WHEN site_auth_rate_limits.window_started_at
                         <= NOW() - (:window_seconds * INTERVAL '1 second')
                    THEN NOW()
                    ELSE site_auth_rate_limits.window_started_at
                END,
                attempts = CASE
                    WHEN site_auth_rate_limits.window_started_at
                         <= NOW() - (:window_seconds * INTERVAL '1 second')
                    THEN 1
                    ELSE site_auth_rate_limits.attempts + 1
                END,
                updated_at = NOW()
            RETURNING attempts,
                GREATEST(
                    1,
                    CEIL(EXTRACT(EPOCH FROM (
                        window_started_at
                        + (:window_seconds * INTERVAL '1 second')
                        - NOW()
                    )))
                )::INTEGER AS retry_after
        """), {
            "bucket_key": bucket_key,
            "window_seconds": window_seconds,
        }).mappings().one()

        # Opportunistically bound storage growth without adding request-time DDL.
        if next(_RATE_LIMIT_CLEANUP_COUNTER) % 256 == 0:
            conn.execute(text("""
                DELETE FROM site_auth_rate_limits
                WHERE updated_at < NOW() - INTERVAL '2 days'
            """))

    return int(row["retry_after"]) if int(row["attempts"]) > max_attempts else 0


def _check_rate_limit(request: Request, action: str) -> None:
    retry_after = _consume_rate_limit(request, action)
    if retry_after > 0:
        label = "ورود" if action == "login" else "ثبت‌نام"
        raise HTTPException(
            status_code=429,
            detail=f"تعداد درخواست‌های {label} بیش از حد مجاز است. کمی بعد دوباره تلاش کنید.",
            headers={"Retry-After": str(retry_after)},
        )


def create_site_token(customer_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(customer_id),
        "role": SITE_CUSTOMER_ROLE,
        "exp": now + timedelta(days=TOKEN_DAYS),
        "iat": now,
    }, _secret(), algorithm="HS256")


def current_site_customer(authorization: str = Header(default="")) -> dict:
    """Dependency for site-customer endpoints. NOT operations.current_user —
    site tokens carry role='site_customer' and no users-table row exists."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "برای ادامه باید وارد حساب خود شوید.")
    try:
        payload = jwt.decode(authorization[7:], _secret(), algorithms=["HS256"])
        customer_id = int(payload["sub"])
        if customer_id <= 0:
            raise ValueError("Invalid customer ID")
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(401, "نشست شما منقضی شده است؛ دوباره وارد شوید.")
    if payload.get("role") != SITE_CUSTOMER_ROLE:
        raise HTTPException(403, "این بخش فقط برای مشتریان سایت است.")
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, email, phone, name FROM site_customers WHERE id = :id"
        ), {"id": customer_id}).mappings().first()
    if not row:
        raise HTTPException(401, "حساب یافت نشد.")
    return dict(row)


class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


@router.post("/register")
def register(data: RegisterIn, request: Request):
    _secret()
    _check_rate_limit(request, "register")
    email, phone = _normalize_contact(data.contact)
    with engine.begin() as conn:
        row = conn.execute(text(
            "INSERT INTO site_customers(email, phone, name, password_hash) "
            "VALUES (:e, :p, :n, :h) ON CONFLICT DO NOTHING RETURNING id"
        ), {"e": email, "p": phone, "n": data.name.strip(),
            "h": hash_password(data.password)}).mappings().first()
        if not row:
            raise HTTPException(409, "این ایمیل یا شماره قبلاً ثبت شده است؛ وارد شوید.")
    return {"token": create_site_token(int(row["id"])), "name": data.name.strip()}


@router.post("/login")
def login(data: LoginIn, request: Request):
    _secret()
    _check_rate_limit(request, "login")
    email, phone = _normalize_contact(data.contact)
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT id, name, password_hash FROM site_customers "
            "WHERE (:e IS NOT NULL AND email = :e) OR (:p IS NOT NULL AND phone = :p) LIMIT 1"
        ), {"e": email, "p": phone}).mappings().first()
    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "ایمیل/شماره یا رمز عبور اشتباه است.")
    return {"token": create_site_token(int(row["id"])), "name": row["name"]}


@router.get("/me")
def me(customer: dict = Depends(current_site_customer)):
    return {"id": customer["id"], "name": customer["name"],
            "email": customer["email"], "phone": customer["phone"]}
