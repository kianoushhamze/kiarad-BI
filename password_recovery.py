"""One-use email password recovery for Kiarad accounts."""

import hashlib
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from config import _env
from db import engine
from operations import hash_password


router = APIRouter(prefix="/auth/recovery", tags=["authentication"])
GENERIC_REPLY = {"message": "If this email is registered, a recovery link will be sent."}


class RecoveryRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)


class RecoveryConfirm(BaseModel):
    token: str = Field(min_length=30, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


def _smtp_settings():
    sender = _env("KIARAD_SMTP_USER")
    password = _env("KIARAD_SMTP_APP_PASSWORD")
    if not sender or not password:
        raise HTTPException(status_code=503, detail="Email recovery is not configured")
    return sender, password


def _send_link(address: str, token: str) -> None:
    sender, password = _smtp_settings()
    origin = _env("KIARAD_PUBLIC_ORIGIN", "http://127.0.0.1:3000").rstrip("/")
    link = f"{origin}/reset-password.html#token={token}"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = address
    message["Subject"] = "Kiarad password recovery"
    message.set_content(
        "A password reset was requested for your Kiarad account.\n\n"
        f"Open this one-time link within 15 minutes:\n{link}\n\n"
        "If you did not request this, ignore this message."
    )
    host = _env("KIARAD_SMTP_HOST", "smtp.gmail.com")
    port = int(_env("KIARAD_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(sender, password)
        smtp.send_message(message)


@router.post("/request")
def request_recovery(data: RecoveryRequest):
    _smtp_settings()
    address = data.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address):
        raise HTTPException(status_code=422, detail="Invalid email")

    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with engine.begin() as conn:
        user = conn.execute(text("""
            SELECT id FROM users
            WHERE lower(recovery_email) = :email AND is_active = 1
        """), {"email": address}).mappings().first()
        if not user:
            return GENERIC_REPLY
        recent = conn.execute(text("""
            SELECT COUNT(*) FROM password_reset_tokens
            WHERE user_id = :user_id AND created_at > now() - interval '1 hour'
        """), {"user_id": user["id"]}).scalar_one()
        if recent >= 3:
            return GENERIC_REPLY
        conn.execute(text("""
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (:user_id, :token_hash, :expires_at)
        """), {
            "user_id": user["id"], "token_hash": digest,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
        })

    try:
        _send_link(address, token)
    except (OSError, smtplib.SMTPException):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM password_reset_tokens WHERE token_hash = :hash"), {"hash": digest})
        raise HTTPException(status_code=503, detail="Email delivery unavailable")
    return GENERIC_REPLY


@router.post("/confirm")
def confirm_recovery(data: RecoveryConfirm):
    digest = hashlib.sha256(data.token.encode("utf-8")).hexdigest()
    with engine.begin() as conn:
        record = conn.execute(text("""
            SELECT t.user_id FROM password_reset_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token_hash = :hash AND t.expires_at > now() AND u.is_active = 1
            FOR UPDATE OF t
        """), {"hash": digest}).mappings().first()
        if not record:
            raise HTTPException(status_code=400, detail="Invalid or expired recovery link")
        conn.execute(text("""
            UPDATE users
            SET password_hash = :hash, password_version = password_version + 1
            WHERE id = :user_id
        """), {"hash": hash_password(data.new_password), "user_id": record["user_id"]})
        conn.execute(text("DELETE FROM password_reset_tokens WHERE user_id = :user_id"), {"user_id": record["user_id"]})
    return {"message": "Password updated"}
