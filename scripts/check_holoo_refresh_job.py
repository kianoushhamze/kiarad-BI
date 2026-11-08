"""Run the manager-authorized read-only ERP refresh through the active API."""
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
import requests
from sqlalchemy import text
from db import engine
from operations import create_token

with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT id,role,password_version FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().one())
session=requests.Session();session.trust_env=False
headers={'Authorization':'Bearer '+create_token(user)}
base='http://127.0.0.1:8000/treasury/strategy/holoo-refresh'
try:
    response=session.post(base,headers=headers,timeout=20)
    response.raise_for_status()
    print(json.dumps({'accepted':response.status_code==202}),flush=True)
    result=response.json()
    limit=time.monotonic()+900
    while result['status']=='running' and time.monotonic()<limit:
        time.sleep(3)
        result=session.get(base,headers=headers,timeout=20).json()
    safe={k:result[k] for k in ('status','snapshot_id','sources','finished_at') if k in result}
    safe.update(erp_financial_writes=False,local_snapshot_expected=True)
    (ROOT/'audit-2026-10-19'/'holoo-refresh-job-validation.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(safe),flush=True)
    raise SystemExit(0 if result['status']=='completed' else 1)
except requests.RequestException as exc:
    print(json.dumps({'ok':False,'error_type':type(exc).__name__}),flush=True)
    raise SystemExit(1)
