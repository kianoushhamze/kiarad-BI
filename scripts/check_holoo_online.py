"""Observe the automatic refresh, without starting a manual refresh or ERP write."""
from pathlib import Path
import json, sys, time
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
import requests
from sqlalchemy import text
from db import engine
from operations import create_token
from iran_time import iran_today

before=json.loads((ROOT/'audit-2026-10-20/online-before.json').read_text(encoding='utf-8'))
with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT id,role,password_version FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().one())
session=requests.Session();session.trust_env=False
headers={'Authorization':'Bearer '+create_token(user)}
url='http://127.0.0.1:8000/treasury/strategy/holoo-refresh'
limit=time.monotonic()+900;last=None;state={}
while time.monotonic()<limit:
    response=session.get(url,headers=headers,timeout=20);response.raise_for_status();state=response.json()
    signature=(state['status'],len(state['sources']))
    if signature!=last:
        print(json.dumps({'status':signature[0],'sources_processed':signature[1]}),flush=True);last=signature
    if state.get('snapshot_id',0) and state['snapshot_id']>before['previous_snapshot_id'] and state['status']!='running':break
    if state['status']=='failed':break
    time.sleep(3)
with engine.connect() as conn:
    snapshot=conn.execute(text('SELECT id,captured_at,payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1')).mappings().one()
    counts={t:conn.execute(text('SELECT count(*) FROM '+t)).scalar() for t in before['counts']}
age=(datetime.now(timezone.utc)-snapshot['captured_at']).total_seconds()
automatic=state.get('automatic',{})
checks={
    'automatic_enabled':automatic.get('enabled') is True,
    'scheduler_running':automatic.get('running') is True,
    'interval_300_seconds':automatic.get('interval_seconds')==300,
    'next_attempt_recorded':bool(automatic.get('next_attempt_at')),
    'automatic_refresh_completed':state.get('status')=='completed',
    'new_snapshot_created':snapshot['id']>before['previous_snapshot_id'],
    'source_through_today':snapshot['payload']['to_date']==iran_today().isoformat(),
    'recent_capture':0<=age<600,
    'all_sources_complete':all(s.get('ok') and s.get('complete') for s in snapshot['payload']['sources'].values()),
    'no_financial_entry_or_approval_created':counts==before['counts'],
}
report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'passed':all(checks.values()),'snapshot_id':snapshot['id'],'captured_at':snapshot['captured_at'].isoformat(),'to_date':snapshot['payload']['to_date'],'automatic':automatic,'sources':state.get('sources',[]),'manual_refresh_started':False,'erp_financial_writes':False,'visual_review':'not_verified_browser_disabled'}
(ROOT/'audit-2026-10-20/holoo-online.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
raise SystemExit(0 if report['passed'] else 1)
