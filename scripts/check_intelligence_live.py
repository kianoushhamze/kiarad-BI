"""Read-only checks of live advanced features; no synthetic production writes."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
import requests
from sqlalchemy import text
from db import engine
from operations import create_token

cases=[]
def record(name,passed):cases.append({'name':name,'passed':bool(passed)})
tables=('base_coach_profiles','base_coach_memory','base_coach_actions','inventory_intelligence_policies','inventory_order_drafts','tasks','task_updates','holoo_financial_snapshots')
with engine.connect() as conn:
    users=[dict(r) for r in conn.execute(text('SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1 ORDER BY id')).mappings()]
    before={t:conn.execute(text('SELECT count(*) FROM '+t)).scalar() for t in tables}
session=requests.Session();session.trust_env=False
origins=[('backend','http://127.0.0.1:8000',''),('proxy','http://127.0.0.1:3000','/api')]
observed={}
for name,origin,prefix in origins:
    record(name+'-anonymous-denied',session.get(origin+prefix+'/catalog/intelligence',timeout=40).status_code==401)
    for user in users:
        headers={'Authorization':'Bearer '+create_token(user)}
        inventory_allowed=user['role'] in {'ceo','finance','sales_manager'}
        response=session.get(origin+prefix+'/catalog/intelligence?days=90',headers=headers,timeout=60)
        record(f"{name}-inventory-role-{user['id']}",response.status_code==(200 if inventory_allowed else 403))
        if inventory_allowed and response.status_code==200:
            value=response.json()
            record(name+'-no-automatic-order',value['automatic_purchase'] is False)
            record(name+'-items-present',len(value['items'])>0)
            if user['role']=='sales_manager':record(name+'-manager-costs-hidden',all('estimated_gross_profit_irr' not in r and 'capital_at_current_purchase_price_irr' not in r for r in value['items']))
            if user['role']=='ceo':observed={'products':len(value['items']),'snapshot_id':value.get('snapshot_id'),'source_fresh':value.get('source_fresh'),'policies':sum(r['policy'] is not None for r in value['items']),'valid_order_suggestions':sum(r['order']['status']=='review_order' for r in value['items'])}
        coach_allowed=user['role'] in {'ceo','sales_manager','visitor','salesperson'}
        response=session.get(origin+prefix+'/kerman/coach/bases',headers=headers,timeout=30)
        record(f"{name}-coach-list-role-{user['id']}",response.status_code==(200 if coach_allowed else 403))
        if coach_allowed and response.status_code==200:
            bases=response.json()['items']
            if user['role'] not in {'ceo','sales_manager'}:
                with engine.connect() as conn:
                    owned={(r['base_source'],r['base_id']) for r in conn.execute(text('SELECT base_source,base_id FROM base_portfolio_assignments WHERE salesperson_id=:sp AND ended_at IS NULL'),{'sp':user['salesperson_id']}).mappings()}
                record(f"{name}-staff-own-base-list-{user['id']}",all((b['source'],b['id']) in owned for b in bases))
            if bases:
                b=bases[0]
                dossier=session.get(origin+prefix+f"/kerman/coach/bases/{b['source']}/{b['id']}",headers=headers,timeout=30)
                record(f"{name}-base-dossier-{user['id']}",dossier.status_code==200)
                if dossier.status_code==200:record(f"{name}-dossier-no-financial-fields-{user['id']}",'net_profit' not in dossier.json() and 'bank_balances' not in dossier.json())
        if not inventory_allowed:
            record(f"{name}-staff-policy-denied-{user['id']}",session.post(origin+prefix+'/catalog/intelligence/policies/invalid',headers=headers,json={},timeout=20).status_code==403)
            record(f"{name}-staff-draft-denied-{user['id']}",session.post(origin+prefix+'/catalog/intelligence/orders',headers=headers,json={},timeout=20).status_code==403)
        if user['role'] in {'visitor','salesperson'}:
            record(f"{name}-staff-review-denied-{user['id']}",session.post(origin+prefix+'/kerman/coach/actions/999999/review',headers=headers,json={'decision':'approve','note':'read-only role check'},timeout=20).status_code==403)
for path in ('/catalog','/kerman-bases'):
    record('page-'+path,session.get('https://kiarad.taile287ae.ts.net'+path,timeout=30).status_code==200)
with engine.connect() as conn:after={t:conn.execute(text('SELECT count(*) FROM '+t)).scalar() for t in tables}
record('no-business-or-financial-rows-created',before==after)
report={'checks':len(cases),'failures':sum(not c['passed'] for c in cases),'observed':observed,'production_writes':False,'holoo_requests':False,'browser_visual_review':'not_verified_browser_disabled','cases':cases}
folder=ROOT/'audit-2026-10-20';folder.mkdir(exist_ok=True)
(folder/'intelligence-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
for c in cases:
    if not c['passed']:print(json.dumps(c))
raise SystemExit(bool(report['failures']))
