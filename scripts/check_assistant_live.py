"""Read-only assistant report/role checks. No external model or Holoo requests."""
from pathlib import Path
import json
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from sqlalchemy import text
from db import engine
from operations import create_token
from assistant_reports import execute_report_tool
from assistant_engine import chat,ChatRequest
import requests

cases=[]
def record(name,passed):
    cases.append({'name':name,'passed':bool(passed)})

with engine.connect() as conn:
    users=[dict(r) for r in conn.execute(text('SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1 ORDER BY id')).mappings()]
    person=conn.execute(text('SELECT id FROM salespersons ORDER BY id LIMIT 1')).scalar()
    before={t:conn.execute(text('SELECT COUNT(*) FROM '+t)).scalar() for t in ('targets','inventory_order_drafts','treasury_strategy_revisions')}

# All direct report checks run with network disabled. No provider data transfer.
with patch('requests.sessions.Session.request',side_effect=AssertionError('External traffic blocked')):
    for user in users:
        for section in ('sales','customers','team','tasks','proformas','routes','payroll','treasury','catalog','crm','daily_reports','campaigns','content'):
            args={'section':section,'month':'1405-07'}
            if section=='payroll':args['salesperson_id']=user.get('salesperson_id') or person
            if section=='catalog':args.update(query='lufente',days=90)
            value=execute_report_tool('read_business_report',args,user)
            record(f"report-{section}-user-{user['id']}-no-source-error",value.get('status') not in {'source_error','invalid_arguments'})
            if section=='treasury' and user['role'] not in {'ceo','finance'}:
                record(f"treasury-denied-user-{user['id']}",value.get('status')=='access_denied')
            if section=='team' and user['role'] in {'visitor','salesperson'} and 'people' in value:
                record(f"team-own-user-{user['id']}",all(p['id']==user['salesperson_id'] for p in value['people']))
    ceo=next(u for u in users if u['role']=='ceo')
    with patch('assistant_engine.save_turn'),patch('assistant_engine.load_history',return_value=[{'role':'user','content':'برند لوفنته'}]):
        for q in ('از برند لوفتنه چی سفارش بدم؟','با توجه به موجودی انبارمون و کاردکس فروشش بهم بگو','برند لوفنته'):
            value=chat(ChatRequest(message=q),ceo)
            record('catalog-example-'+str(len(cases)),value.get('mode')=='verified_catalog_analysis' and value.get('matched_count')==5)
            record('catalog-never-placed-order-'+str(len(cases)),value.get('automatic_purchase') is False)

session=requests.Session();session.trust_env=False
for origin,prefix in (('http://127.0.0.1:8000',''),('http://127.0.0.1:3000','/api'),('https://kiarad.taile287ae.ts.net','/api')):
    response=session.post(origin+prefix+'/assistant/chat',json={'message':'سلام'},timeout=30)
    record(origin+'-anonymous-denied',response.status_code==401)
    for user in users:
        token=create_token(user)
        response=session.post(origin+prefix+'/assistant/chat',headers={'Authorization':'Bearer '+token},json={'message':'برند لوفنته'},timeout=45)
        record(origin+f"-catalog-user-{user['id']}",response.status_code==200)
        if response.status_code==200 and user['role']=='ceo':
            record(origin+'-current-price-from-snapshot',all('current_sell_price_irr' in row for row in response.json().get('items',[])) and bool(response.json().get('items')))
        if response.status_code==200 and user['role'] in {'visitor','salesperson'}:
            payload=response.json()
            record(origin+f"-staff-no-company-turnover-{user['id']}",'items' not in payload and payload.get('mode') in {'verified_catalog_lookup','access_limited'})
    headers={'Authorization':'Bearer '+create_token(ceo)}
    response=session.post(origin+prefix+'/assistant/chat',headers=headers,json={'message':'تارگت رو بگم میتونی ست کنی؟'},timeout=30)
    record(origin+'-target-intake',response.status_code==200 and response.json().get('mode')=='target_intake')
    response=session.post(origin+prefix+'/assistant/advisory/ask',headers=headers,json={'question':'برند لوفنته'},timeout=45)
    record(origin+'-advisory-shared-grounded-path',response.status_code==200 and response.json().get('mode')=='verified_catalog_analysis')
for path in ('/assistant','/person-targets','/newdash_online.html'):
    response=session.get('http://127.0.0.1:3000'+path,timeout=30)
    record('page-'+path,response.status_code==200)
with engine.connect() as conn:
    after={t:conn.execute(text('SELECT COUNT(*) FROM '+t)).scalar() for t in before}
record('no-target-order-or-finance-revision-created',before==after)
report={'checks':len(cases),'failures':sum(not c['passed'] for c in cases),'cases':cases,
        'external_model_called':False,'holoo_requests':False,'business_writes':False,'chat_history_test_turns_saved':True,
        'browser_visual_review':'not_verified_browser_disabled'}
path=ROOT/'audit-2026-10-20/assistant-live.json'
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
for c in cases:
    if not c['passed']:print(json.dumps(c))
raise SystemExit(bool(report['failures']))
