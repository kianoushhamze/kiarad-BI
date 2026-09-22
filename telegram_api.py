
# -*- coding: utf-8 -*-
import secrets
from fastapi import APIRouter, Depends
from sqlalchemy import text
from db import engine
from operations import current_user

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/bind-code")
def make_bind_code(user: dict = Depends(current_user)):
    """کد یک‌بارمصرف ۶ رقمی برای اتصال اکانت تلگرام - ۱۰ دقیقه اعتبار"""
    code = str(secrets.randbelow(900000) + 100000)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM telegram_bind_codes WHERE user_id = :u OR expires_at < NOW()"),
                     dict(u=user.get("id")))
        conn.execute(text("INSERT INTO telegram_bind_codes (code, user_id, expires_at) "
                          "VALUES (:c, :u, NOW() + INTERVAL '10 minutes')"),
                     dict(c=code, u=user.get("id")))
    return dict(code=code, expires_minutes=10)
