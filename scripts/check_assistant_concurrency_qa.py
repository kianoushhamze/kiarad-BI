"""Concurrent confirmations on synthetic data must create exactly one task."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import sys,json,requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import DB_CONFIG
from db import engine
from sqlalchemy import text
from operations import create_token
from assistant_operations import prepare
assert DB_CONFIG['database']=='kiarad_assistant_qa_20261103'
with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
title='آزمون همزمانی '+uuid4().hex
proposal=prepare({'operation':'create_task','payload':{'title':title,'assigned_to':user['id']}},user)
barrier=Barrier(2)
def confirm(_):
    session=requests.Session();session.trust_env=False
    barrier.wait(timeout=10)
    response=session.post('http://127.0.0.1:8000/assistant/actions/'+proposal['proposal_id']+'/confirm',headers={'Authorization':'Bearer '+create_token(user)},json={'confirm':True},timeout=30)
    return response.status_code
with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(confirm,range(2)))
with engine.connect() as conn:count=conn.execute(text('SELECT COUNT(*) FROM tasks WHERE title=:title'),{'title':title}).scalar_one()
passed=count==1 and 200 in statuses and all(s in {200,409} for s in statuses)
report={'passed':passed,'simultaneous_confirmations':2,'http_statuses':statuses,'created_tasks':count,'production_data_changed':False}
(Path(__file__).resolve().parents[1]/'audit-2026-11-03/assistant-concurrency-qa.json').write_text(json.dumps(report),encoding='utf-8')
print(json.dumps(report));raise SystemExit(not passed)
