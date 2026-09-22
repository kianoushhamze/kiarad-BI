
# -*- coding: utf-8 -*-
"""Kiarad Telegram Bot v0.1 - auth/bind + identity"""
import io, os, time
import requests
from sqlalchemy import text
from db import engine

ROOT = r"D:\project\kiaradbi"


def env(key, default=""):
    try:
        for line in io.open(os.path.join(ROOT, ".env"), "r", encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith(key + "="):
                keypart, sep, val = line.partition("=")
                return val.strip()
    except Exception:
        pass
    return os.getenv(key, default)


TOKEN = env("TELEGRAM_BOT_TOKEN", "")
API = "https://api.telegram.org/bot" + TOKEN
PROXY = env("TELEGRAM_PROXY", "")
PROXIES = None
if PROXY:
    PROXIES = dict(http=PROXY, https=PROXY)


def send(chat_id, body):
    try:
        payload = dict(chat_id=chat_id, text=body)
        requests.post(API + "/sendMessage", json=payload, proxies=PROXIES, timeout=35)
    except Exception as e:
        print("send error:", e)


def load_user(chat_id):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT username, full_name, role FROM users "
            "WHERE telegram_chat_id = :c AND is_active = 1"), dict(c=chat_id)).mappings().first()
    return dict(row) if row else None


def try_bind(chat_id, code):
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        return None
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT id, user_id FROM telegram_bind_codes "
            "WHERE code = :c AND used_at IS NULL AND expires_at > NOW() "
            "ORDER BY id DESC LIMIT 1"), dict(c=code)).mappings().first()
        if not row:
            return None
        code_id = row.get("id")
        user_id = row.get("user_id")
        conn.execute(text("UPDATE telegram_bind_codes SET used_at = NOW() WHERE id = :i"),
                     dict(i=code_id))
        conn.execute(text("UPDATE users SET telegram_chat_id = :ch WHERE id = :u"),
                     dict(ch=chat_id, u=user_id))
        u = conn.execute(text("SELECT username, full_name, role FROM users WHERE id = :u"),
                         dict(u=user_id)).mappings().first()
    return dict(u) if u else None


def handle(update):
    msg = update.get("message") or dict()
    chat = msg.get("chat") or dict()
    chat_id = chat.get("id")
    t = (msg.get("text") or "").strip()
    if not chat_id:
        return
    user = load_user(chat_id)
    if t.startswith("/start") or t.startswith("/bind"):
        if user:
            send(chat_id, "سلام " + str(user.get("full_name")) + " عزیز!\n"
                 "تو با نقش «" + str(user.get("role")) + "» متصل هستی.\n"
                 "منوهای عملیاتی (فروش، گزارش صوتی، لوکیشن، کمپین) در فاز بعد فعال می‌شوند.")
        else:
            send(chat_id, "سلام! برای اتصال به سیستم کیاراد:\n"
                 "1) در داشبورد وارد شو\n"
                 "2) کد اتصال ۶ رقمی بگیر (بخش پرسنل)\n"
                 "3) کد را همین‌جا بفرست")
        return
    if user is None:
        res = try_bind(chat_id, t)
        if res:
            send(chat_id, "✅ اتصال موفق!\n" + str(res.get("full_name")) + " | نقش: " + str(res.get("role")))
        else:
            send(chat_id, "کد نامعتبر یا منقضی. از داشبورد کد تازه بگیر و بفرست.")
        return
    send(chat_id, "فعلاً: /start\nامکانات عملیاتی به‌زودی (فاز 8B).")


def main():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN missing - abort")
        return
    print("Kiarad bot started | proxy: " + ("YES" if PROXY else "NO"))
    offset = 0
    while True:
        try:
            r = requests.get(API + "/getUpdates",
                             params=dict(offset=offset, timeout=25),
                             proxies=PROXIES, timeout=40)
            data = r.json()
            if not data.get("ok"):
                print("api says not ok:", str(data)[:200])
                time.sleep(3)
                continue
            updates = data.get("result") or list()
            for upd in updates:
                offset = upd.get("update_id", offset) + 1
                try:
                    handle(upd)
                except Exception as e:
                    print("handle error:", e)
        except Exception as e:
            print("poll error:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
