"""Check authentication without exposing credentials or response contents."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env')
from holoo_router import login_holoo
from holoo_sync import holoo_login

try:
    token = login_holoo()
    print(json.dumps({'login_ok': bool(token)}))
    legacy_token = holoo_login()
    print(json.dumps({'legacy_login_ok': bool(legacy_token)}))
except Exception as exc:
    response = getattr(exc, 'response', None)
    print(json.dumps({'login_ok': False, 'error_type': type(exc).__name__,
                      'http_status': response.status_code if response is not None else None}))
    raise SystemExit(1)
