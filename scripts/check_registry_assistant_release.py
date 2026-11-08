"""Read-only live acceptance of registry, customer directory and contract handoff."""
import json
from pathlib import Path
import sys
import requests
from sqlalchemy import text
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from db import engine
from operations import create_token
from assistant_reports import execute_report_tool


def main():
    with engine.connect() as conn:
        users=[dict(r) for r in conn.execute(text('SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1')).mappings()]
        person=conn.execute(text('SELECT id FROM salespersons ORDER BY id LIMIT 1')).scalar()
        before=conn.execute(text('SELECT COUNT(*) FROM customers')).scalar()
    ceo=next(u for u in users if u['role']=='ceo')
    session=requests.Session();session.trust_env=False
    checks=[]
    for origin,prefix in [('http://127.0.0.1:8000',''),('http://host.docker.internal:3000','/api')]:
        for path in ['/kerman/coach/public-registry?limit=1','/directory/customers']:
            response=session.get(origin+prefix+path,headers={'Authorization':'Bearer '+create_token(ceo)},timeout=25)
            checks.append({'name':origin+path,'passed':response.status_code==200})
        for user in users:
            if user['role'] not in {'visitor','salesperson'}:continue
            response=session.post(origin+prefix+'/kerman/coach/public-registry/import',
                headers={'Authorization':'Bearer '+create_token(user)},json={'source_id':'acceptance-no-write','confirm':True},timeout=25)
            checks.append({'name':origin+' staff import denied '+str(user['id']),'passed':response.status_code==403})
    proposal=execute_report_tool('prepare_contract_review',{'salesperson_id':person,'description':'شرح آزمایشی برای بررسی انتقال به فرم؛ هیچ قراردادی ذخیره نشود.'},ceo)
    checks.append({'name':'contract review no save','passed':proposal.get('saved') is False and proposal.get('status')=='review_only'})
    with engine.connect() as conn:
        after=conn.execute(text('SELECT COUNT(*) FROM customers')).scalar()
    checks.append({'name':'customer count unchanged','passed':before==after})
    report={'checks':checks,'failures':sum(not c['passed'] for c in checks),'business_writes':False}
    target=ROOT/'audit-2026-11-02/registry-assistant-live.json';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(checks),'failures':report['failures'],'business_writes':False}))
    raise SystemExit(bool(report['failures']))


if __name__=='__main__':main()
