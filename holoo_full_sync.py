
# -*- coding: utf-8 -*-
"""Kiarad full holoo sync: customers + products + invoices(90d). Runs hourly via Task Scheduler."""
import io
import os
import json
import time
import urllib.request
from datetime import date, timedelta
from iran_time import iran_now, iran_today

ROOT = r"D:\project\kiaradbi"


def env_get(key, default=""):
    try:
        for line in io.open(os.path.join(ROOT, ".env"), "r", encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith(key + "="):
                k, sep, v = line.partition("=")
                return v.strip()
    except Exception:
        pass
    return default


def holoo_login():
    base = env_get("HOLO_API_URL", "http://192.168.1.105:8080/TncHoloo/api").rstrip("/")
    body = dict(userinfo=dict(username=env_get("HOLO_USERNAME", "web"),
                              userpass=env_get("HOLO_PASSWORD", "MQ=="),
                              dbname="Holoo2"))
    req = urllib.request.Request(base + "/Login",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers=dict(Content_Type="application/json"), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    tok = (d.get("Login") or dict()).get("Token", "")
    return base, tok


def api_key():
    return env_get("KIARAD_API_KEY", "")


def backend_sync():
    headers = dict()
    headers.setdefault("X-API-Key", api_key())
    headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request("http://127.0.0.1:8000/holoo/sync",
                                 data=b"{}", headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def invoice_sync():
    base, token = holoo_login()
    headers = dict()
    headers.setdefault("Authorization", token)
    today = iran_today()
    start = today - timedelta(days=90)
    win_start = start.isoformat()
    win_end = today.isoformat()
    req = urllib.request.Request(
        base + "/Invoice/Invoice?type=1&date.from=" + win_start + "&date.to=" + win_end,
        headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    invs = data.get("invoice") or list()
    return len(invs)


def main():
    now_str = iran_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        d = backend_sync()
        print("[" + now_str + "] customers/products sync: " + json.dumps(d, ensure_ascii=False)[:180], flush=True)
    except Exception as e:
        print("[" + now_str + "] cp sync ERROR: " + type(e).__name__ + " " + str(e)[:150], flush=True)
    try:
        n = invoice_sync()
        print("[" + now_str + "] invoices fetched(90d, counted): " + str(n), flush=True)
        headers = dict()
        headers.setdefault("X-API-Key", api_key())
        headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request("http://127.0.0.1:8000/holoo/sync",
                                     data=b"{}", headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            d2 = json.loads(r.read().decode("utf-8"))
        print("[" + now_str + "] final: " + json.dumps(d2, ensure_ascii=False)[:180], flush=True)
    except Exception as e:
        print("[" + now_str + "] invoice sync ERROR: " + type(e).__name__ + " " + str(e)[:150], flush=True)


if __name__ == "__main__":
    main()
