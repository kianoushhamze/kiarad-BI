
# -*- coding: utf-8 -*-
"""Kiarad hourly holoo sync service - calls the real backend route, logs every run."""
import io
import os
import sys
import time
import json
import urllib.request
from datetime import datetime
from iran_time import iran_now

ROOT = r"D:\project\kiaradbi"
INTERVAL = 3600


def api_key():
    try:
        for line in io.open(os.path.join(ROOT, ".env"), "r", encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith("KIARAD_API_KEY="):
                key, sep, val = line.partition("=")
                return val.strip()
    except Exception:
        pass
    return ""


def run_sync():
    headers = dict()
    headers.setdefault("X-API-Key", api_key())
    headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request("http://127.0.0.1:8000/holoo/sync",
                                 data=b"{}", headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=360) as r:
        return json.loads(r.read().decode("utf-8"))


def read_status():
    headers = dict()
    headers.setdefault("X-API-Key", api_key())
    req = urllib.request.Request("http://127.0.0.1:8000/holoo/status", headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("Kiarad holoo auto-sync started | interval: every " + str(INTERVAL) + "s", flush=True)
    while True:
        now_str = iran_now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            d = run_sync()
            print("[" + now_str + "] sync: " + json.dumps(d, ensure_ascii=False)[:200], flush=True)
        except Exception as e:
            print("[" + now_str + "] SYNC ERROR: " + type(e).__name__ + " " + str(e)[:200], flush=True)
        try:
            st = read_status()
            print("[" + now_str + "] status: " + json.dumps(st, ensure_ascii=False)[:200], flush=True)
        except Exception as e:
            print("[" + now_str + "] status read failed: " + type(e).__name__, flush=True)
        time.sleep(INTERVAL)


def run_once():
    """Run one scheduler-friendly sync and return a meaningful exit code."""
    now_str = iran_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        result = run_sync()
        print("[" + now_str + "] sync: " + json.dumps(result, ensure_ascii=False)[:300], flush=True)
        return 0
    except Exception as exc:
        print("[" + now_str + "] SYNC ERROR: " + type(exc).__name__ + " " + str(exc)[:300], flush=True)
        return 1


if __name__ == "__main__":
    if "--once" in sys.argv:
        raise SystemExit(run_once())
    main()
