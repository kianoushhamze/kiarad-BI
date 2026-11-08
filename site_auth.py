"""ثبت‌نام و ورود مشتری سایت (site customer auth) — ایمیل یا موبایل + رمز.

 جدا از حساب‌های کارمندی (operations): توکن JWT با role='site_customer'
 صادر می‌شود و فقط برای مسیرهای /site-auth/me و آیندهٔ سفارش/قیمت پلکانی
 معتبر است. Google OAuth بعداً با اعتبارنامهٔ Google قابل افزودن است.
"""
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from operations import hash_password, verify_password

router = APIRouter(prefix="/site-auth", tags=["site_auth"])

SITE_CUSTOMER_ROLE = "site_customer"
TOKEN_DAYS = 7

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^09\d{9}$")


def ensure(conn):
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS site_customers(
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            phone TEXT UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""))


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
def register(data: RegisterIn):
    email, phone = _normalize_contact(data.contact)
    with engine.begin() as conn:
        ensure(conn)
        dup = conn.execute(text(
            "SELECT 1 FROM site_customers WHERE (:e IS NOT NULL AND email = :e) OR (:p IS NOT NULL AND phone = :p)"
        ), {"e": email, "p": phone}).first()
        if dup:
            raise HTTPException(409, "این ایمیل یا شماره قبلاً ثبت شده است؛ وارد شوید.")
        row = conn.execute(text(
            "INSERT INTO site_customers(email, phone, name, password_hash) "
            "VALUES (:e, :p, :n, :h) RETURNING id"
        ), {"e": email, "p": phone, "n": data.name.strip(),
            "h": hash_password(data.password)}).mappings().first()
    return {"token": create_site_token(int(row["id"])), "name": data.name.strip()}


@router.post("/login")
def login(data: LoginIn):
    email, phone = _normalize_contact(data.contact)
    with engine.begin() as conn:
        ensure(conn)
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
