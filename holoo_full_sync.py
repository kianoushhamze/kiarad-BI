# -*- coding: utf-8 -*-
"""Hourly Holoo sync: one call to the backend (customers + products + invoices).

Run by run_holoo_sync.bat. Exit code 0 = success, 1 = failed or partial (so Task Scheduler can see it).
Settings (.env next to this file): KIARAD_API_KEY (required), KIARAD_API_URL, HOLOO_SYNC_DAYS.
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))


def env_get(key, default=""):
    if os.environ.get(key):
        return os.environ[key]
    try:
        for line in io.open(os.path.join(ROOT, ".env"), "r", encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith(key + "="):
                return line.partition("=")[2].strip()
    except OSError:
        pass
    return default


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    key = env_get("KIARAD_API_KEY")
    if not key:
        print(f"[{stamp}] ERROR: KIARAD_API_KEY is missing in .env", flush=True)
        return 1
    base = env_get("KIARAD_API_URL", "http://127.0.0.1:8000").rstrip("/")
    days = env_get("HOLOO_SYNC_DAYS", "90")
    req = urllib.request.Request(f"{base}/holoo/sync?days={days}", data=b"{}", method="POST",
                                 headers={"X-API-Key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            result = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"[{stamp}] SYNC ERROR HTTP {e.code}: {body}", flush=True)
        return 1
    except Exception as e:
        print(f"[{stamp}] SYNC ERROR {type(e).__name__}: {str(e)[:200]}", flush=True)
        return 1

    inv = result.get("invoices", {})
    print(f"[{stamp}] {result.get('status')}: customers={result.get('customers')} products={result.get('products')} "
          f"invoices(new={inv.get('inserted')}, updated={inv.get('updated')}, errors={inv.get('errors')}, "
          f"missing_in_holoo={inv.get('missing_in_holoo_count')})", flush=True)
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
