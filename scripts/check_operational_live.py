"""Reconcile the real local mirror with raw Holoo headers, without ERP writes."""
from pathlib import Path
import sys,json
from datetime import date,datetime,timedelta
from decimal import Decimal
import jdatetime,requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from db import engine
from sqlalchemy import text
from operations import create_token
from iran_time import iran_today

def number(v):return Decimal(str(v).replace(',','').replace('٬',''))
def day(v):
    y,m,d=map(int,str(v)[:10].replace('/','-').split('-'))
    return jdatetime.date(y,m,d).togregorian() if y<1700 else date(y,m,d)
def close(a,b):return abs(number(a)-number(b))<=Decimal('0.51')

checks=[]
def record(name,ok):checks.append({'name':name,'passed':bool(ok)})
session=requests.Session();session.trust_env=False
base='http://127.0.0.1:8000'
with engine.connect() as conn:
    users=[dict(r) for r in conn.execute(text('SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1 ORDER BY id')).mappings()]
    run=conn.execute(text('SELECT snapshot_id,receipt FROM holoo_operational_runs ORDER BY snapshot_id DESC LIMIT 1')).mappings().one()
    p=conn.execute(text('SELECT payload FROM holoo_financial_snapshots WHERE id=:id'),{'id':run['snapshot_id']}).scalar_one()
    rows=[dict(r) for r in conn.execute(text('SELECT * FROM sales ORDER BY id')).mappings()]
    items={r['sale_id']:dict(r) for r in conn.execute(text('SELECT sale_id,SUM(quantity*price) AS net,SUM(quantity) AS qty FROM sale_items GROUP BY sale_id')).mappings()}
    before={t:conn.execute(text('SELECT count(*) FROM '+t)).scalar() for t in ('sales','sale_items','payments','financial_documents','cash_accounts','holoo_operational_audit')}
    ar=conn.execute(text('SELECT total_amount,row_count,imported_by FROM receivable_snapshots WHERE id=:id'),{'id':run['receipt']['receivable_snapshot_id']}).mappings().one()
factor=number(p['currency_factor']);expected={}
for kind,num,sign in (('sales',2,1),('sales_returns',4,-1)):
    for r in p['sources'][kind]['rows']:
        expected[(num,str(r['ErpCode']))]={'date':day(r['Date']),'amount':(number(r['SumPrice'])-number(r['SumDiscount']))*factor*sign,'qty':sum((number(d['Few']) for d in r['Detail']),Decimal(0))*sign}
managed={(r['holoo_kind'],r['holoo_erp_code']):r for r in rows if r['holoo_erp_code'] is not None}
record('exact-document-identity-set',set(managed)==set(expected))
for key,value in expected.items():
    row=managed.get(key)
    record('header-'+str(key),row is not None and close(row['total_amount'],value['amount']) and row['date'].date()==value['date'])
    item=items.get(row['id']) if row else None
    record('details-'+str(key),item is not None and close(item['net'],value['amount']) and abs(number(item['qty'])-value['qty'])<Decimal('0.000001'))
record('no-duplicate-erp-keys',len(managed)==sum(r['holoo_erp_code'] is not None for r in rows))
record('legacy-rows-archived',run['receipt']['archived_legacy']==0 or run['receipt']['archived_legacy']==298)
debt=sum((max(Decimal(0),number(r['Mandeh'])*factor) for r in p['sources']['customers']['rows']),Decimal(0))
record('receivables-reconcile',close(ar['total_amount'],debt))
record('automatic-import-not-human-approval',ar['imported_by'] is None)
today=iran_today();j=jdatetime.date.fromgregorian(date=today);month_start=jdatetime.date(j.year,j.month,1).togregorian()
for user in users:
    headers={'Authorization':'Bearer '+create_token(user)}
    manager=user['role'] in {'ceo','sales_manager'};personal=user['role'] in {'salesperson','visitor'}
    for window,start in (('month',month_start),('30d',today-timedelta(days=29)),('90d',today-timedelta(days=89))):
        response=session.get(base+'/dashboard/full?range='+window,headers=headers,timeout=30)
        record(f"role-{user['id']}-{window}",response.status_code==(200 if manager or personal else 403))
        if response.status_code!=200:continue
        result=response.json();k=result['ceo_kpi']
        relevant=[r for r in rows if start<=r['date'].date()<=today and (manager or r['salesperson_id']==user['salesperson_id'])]
        record(f"scoped-sum-{user['id']}-{window}",close(k['total_sales'],sum((number(r['total_amount']) for r in relevant),Decimal(0))))
        record(f"scoped-count-{user['id']}-{window}",k['invoice_count']==len(relevant))
        record(f"jalali-window-{user['id']}-{window}",result['period']['from_date']==start.isoformat())
        record(f"sync-fresh-{user['id']}-{window}",result['data_sync']['status']=='fresh')
        if manager:
            net=sum((v['amount'] for v in expected.values() if start<=v['date']<=today),Decimal(0))
            record(f"raw-holoo-company-net-{window}",close(k['total_sales'],net))
            record('headline-debt',close(k['total_debt'],debt))
        if personal:
            record(f"no-company-sync-count-{user['id']}",'unattributed_documents' not in result['data_sync'])
            record(f"personal-view-{user['id']}",result['view_mode']=='salesperson')
    if personal:
        for path in ('/holoo/status','/dashboard/powerbi','/reports/sales-trend'):
            record(f"company-read-denied-{user['id']}-{path}",session.get(base+path,headers=headers,timeout=20).status_code==403)
ceo=next(u for u in users if u['role']=='ceo');headers={'Authorization':'Bearer '+create_token(ceo)}
trend=session.get(base+'/reports/sales-trend',headers=headers,timeout=30).json()
record('trend-is-jalali',trend.get('calendar')=='jalali')
record('trend-net-reconciles',close(sum(r['sales_amount'] for r in trend['trend']),sum(v['amount'] for v in expected.values())))
for path in ('/management','/newdash_online.html'):
    record('private-page-'+path,session.get('https://kiarad.taile287ae.ts.net'+path,timeout=30).status_code==200)
with engine.connect() as conn:
    after={t:conn.execute(text('SELECT count(*) FROM '+t)).scalar() for t in before}
record('read-only-checks-no-row-changes',before==after)
report={'checks':len(checks),'failures':sum(not r['passed'] for r in checks),'snapshot_id':run['snapshot_id'],'sales':run['receipt']['sales'],'returns':run['receipt']['returns'],'real_holoo_writes':False,'checker_writes':False,'visual_review':'not_verified_browser_disabled','cases':checks}
(ROOT/'audit-2026-10-20/operational-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
for r in checks:
    if not r['passed']:print(json.dumps(r))
raise SystemExit(bool(report['failures']))
