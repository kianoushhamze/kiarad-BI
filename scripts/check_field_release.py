"""Read-only release checks: real catalog, bases, search, scope and PWA assets."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import struct
import sys
from dotenv import load_dotenv
import requests
from sqlalchemy import text
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));load_dotenv(ROOT/'.env')


def main():
    from db import engine
    from operations import create_token
    with engine.connect() as conn:
        users=[dict(row) for row in conn.execute(text('SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1 ORDER BY id')).mappings()]
        counts={table:conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar() for table in ('customers','products','holoo_customer_bases')}
        base=dict(conn.execute(text('SELECT base_source,base_id FROM holoo_customer_bases ORDER BY customer_id LIMIT 1')).mappings().one())
    ceo=next(user for user in users if user['role']=='ceo')
    session=requests.Session();session.trust_env=False
    cases=[];readiness_summary=None
    registry_file=json.loads((ROOT/'data/public-prospects/registry-review.json').read_text(encoding='utf-8'))
    registry_summary=None
    def check(name,value):cases.append({'name':name,'passed':bool(value)})
    frontend_origin=os.environ.get('KIARAD_CHECK_FRONTEND_ORIGIN','http://127.0.0.1:3000')
    for origin,prefix in [('http://127.0.0.1:8000',''),(frontend_origin,'/api'),('https://kiarad.taile287ae.ts.net','/api')]:
        headers={'Authorization':'Bearer '+create_token(ceo)}
        def get(path):
            r=session.get(origin+prefix+path,headers=headers,timeout=45)
            check(origin+path+'-status',r.status_code==200)
            return r.json() if r.status_code==200 else {}
        catalog=get('/catalog/products');check(origin+'-full-catalog',len(catalog.get('items',[]))==counts['products'])
        bases=get('/api/compensation/bases');check(origin+'-all-imported-selectable',len(bases.get('items',[]))>=counts['holoo_customer_bases'])
        coach=get('/kerman/coach/bases');check(origin+'-coach-count',coach.get('total_matches')==len(bases.get('items',[])))
        registry=get('/kerman/coach/public-registry')
        check(origin+'-registry-count',registry.get('total_source_rows')==len(registry_file['items']))
        check(origin+'-registry-page-limit',len(registry.get('items',[]))<=20)
        check(origin+'-registry-not-confirmed',registry.get('automatic_customer_import') is False and registry.get('province_coverage_percent') is None and all(row.get('identity_confirmed') is False for row in registry.get('items',[])))
        registry_summary={key:registry.get(key) for key in ('total_source_rows','rows_with_possible_matches')}
        filtered=get('/kerman/coach/public-registry?q='+requests.utils.quote('کرمان')+'&limit=1')
        check(origin+'-registry-partial-search',filtered.get('total_matches',0)>0 and len(filtered.get('items',[]))==1)
        readiness=get('/kerman/coach/readiness')
        check(origin+'-readiness-count',readiness.get('total')==coach.get('total_matches'))
        check(origin+'-readiness-items',len(readiness.get('items',[]))==readiness.get('total'))
        check(origin+'-readiness-structural-only',readiness.get('basis')=='local_structural_fields_only')
        if readiness_summary is None:readiness_summary={key:readiness.get(key) for key in ('total','without_structural_gaps','counts')}
        else:check(origin+'-readiness-consistent',readiness_summary=={key:readiness.get(key) for key in ('total','without_structural_gaps','counts')})
        dossier=get(f"/kerman/coach/bases/{base['base_source']}/{base['base_id']}")
        check(origin+'-dossier-opens-with-customer-link',bool(dossier.get('profile',{}).get('payload',{}).get('customer_id')))
        partial=get('/directory/customers?q='+requests.utils.quote('دک'))
        variant=get('/directory/customers?q='+requests.utils.quote('دك'))
        check(origin+'-partial-persian-arabic-search',isinstance(partial,list) and len(partial)>0 and {x['id'] for x in partial}=={x['id'] for x in variant})
        matched=get('/kerman/coach/bases?q='+requests.utils.quote('دك'))
        check(origin+'-coach-partial-search',len(matched.get('items',[]))>0)
        preview=get('/kerman/coach/holoo-customers/import-preview')
        check(origin+'-import-complete-no-duplicates',preview.get('already_registered')==counts['holoo_customer_bases'] and preview.get('new_bases')==0)
        for user in users:
            if user['role'] not in {'visitor','salesperson'}:continue
            r=session.get(origin+prefix+'/kerman/coach/holoo-customers/import-preview',headers={'Authorization':'Bearer '+create_token(user)},timeout=20)
            check(origin+f"-staff-{user['id']}-import-denied",r.status_code==403)
            r=session.get(origin+prefix+'/kerman/coach/readiness',headers={'Authorization':'Bearer '+create_token(user)},timeout=20)
            check(origin+f"-staff-{user['id']}-readiness-denied",r.status_code==403)
            r=session.get(origin+prefix+'/kerman/coach/public-registry',headers={'Authorization':'Bearer '+create_token(user)},timeout=20)
            check(origin+f"-staff-{user['id']}-registry-denied",r.status_code==403)
    for origin in (frontend_origin,'https://kiarad.taile287ae.ts.net'):
        r=session.get(origin+'/manifest.webmanifest',timeout=30)
        check(origin+'-manifest',r.status_code==200)
        if r.status_code==200:
            m=r.json();check(origin+'-standalone',m.get('display')=='standalone' and m.get('start_url')=='/my-plan')
        for path,size in [('/app-icon-192',192),('/icon',512)]:
            r=session.get(origin+path,timeout=30)
            check(origin+path,r.status_code==200 and r.content[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',r.content[16:24])==(size,size))
        r=session.get(origin+'/account',timeout=30)
        check(origin+'-manifest-in-layout','manifest.webmanifest' in r.text)
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':len(cases),'failures':sum(not row['passed'] for row in cases),'counts':counts,'cases':cases,
            'read_only':True,'holoo_writes':False,'real_gps_or_installation_test':False,'readiness':readiness_summary,'public_registry':registry_summary}
    folder=ROOT/'audit-2026-10-27';folder.mkdir(exist_ok=True)
    (folder/'field-release-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
    for row in cases:
        if not row['passed']:print(json.dumps(row))
    return int(report['failures']>0)


if __name__=='__main__':raise SystemExit(main())
