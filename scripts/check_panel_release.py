"""Read-only panel release checks. No browser automation or external model calls."""
from pathlib import Path
import json
import re
import sys
import requests
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env')
from db import engine
from sqlalchemy import text
from operations import create_token


def main():
    session=requests.Session();session.trust_env=False
    cases=[]
    def check(name,value):cases.append({'name':name,'passed':bool(value)})
    with engine.connect() as conn:
        users=[dict(row) for row in conn.execute(text('SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1 ORDER BY id')).mappings()]
        media=[dict(row) for row in conn.execute(text('SELECT file_path FROM product_media ORDER BY id DESC LIMIT 2')).mappings()]
        prices=dict(conn.execute(text('SELECT COUNT(*) AS products,COUNT(price2) AS with_price2 FROM products')).mappings().one())
        check('suggestion-storage-created',conn.execute(text("SELECT to_regclass('ai_suggestions') IS NOT NULL")).scalar())
    ceo=next(user for user in users if user['role']=='ceo')
    for origin,prefix in [('http://127.0.0.1:8000',''),('http://127.0.0.1:3000','/api'),('https://kiarad.taile287ae.ts.net','/api')]:
        headers={'Authorization':'Bearer '+create_token(ceo)}
        for path in ['/crud/pharmacies','/crud/cosmetics_shops','/campaigns/ai/pending','/campaigns','/targets/person-targets','/catalog/products','/operations/products-list','/operations/proformas/exports','/integrations']:
            response=session.get(origin+prefix+path,headers=headers,timeout=30)
            check(origin+path,response.status_code==200)
            if path=='/operations/products-list' and response.status_code==200:
                data=response.json()
                check(origin+'-all-products-available',len(data)==prices['products'])
                check(origin+'-second-price-returned',all('price2' in row for row in data))
        check(origin+'-anonymous-campaign-denied',session.get(origin+prefix+'/campaigns/ai/pending',timeout=20).status_code==401)
        for user in users:
            if user['role'] not in {'visitor','salesperson'}:continue
            response=session.get(origin+prefix+'/campaigns/ai/pending',headers={'Authorization':'Bearer '+create_token(user)},timeout=20)
            check(origin+f"-staff-{user['id']}-campaign-ai-denied",response.status_code==403)
        for index,row in enumerate(media):
            path=row['file_path'].removeprefix('/api')
            response=session.get(origin+prefix+path,headers=headers,timeout=20)
            check(origin+f'-media-{index}-authorized',response.status_code==200)
            check(origin+f'-media-{index}-private',session.get(origin+prefix+path,timeout=20).status_code==401)
    for origin in ['http://127.0.0.1:3000','https://kiarad.taile287ae.ts.net']:
        chunks=set()
        for path in ['/newdash_online.html','/management','/person-targets','/proformas','/assistant','/personnel','/catalog','/capability-center','/visitors']:
            response=session.get(origin+path,timeout=30)
            check(origin+'-page-'+path,response.status_code==200)
            check(origin+'-no-iframe-'+path,re.search(r'<iframe(?:\s|>)',response.text,re.I) is None)
            chunks.update(re.findall(r'<script[^>]+src="([^\"]+)"',response.text))
        for path in sorted(chunks):
            if not path.startswith('/_next/'):continue
            response=session.get(origin+path,timeout=30)
            check(origin+'-asset-'+path,response.status_code==200 and 'javascript' in response.headers.get('Content-Type',''))
        for legacy,target in [('/manager','/personnel'),('/advisory','/assistant'),('/','/management')]:
            response=session.get(origin+legacy,timeout=30)
            check(origin+'-redirect-'+legacy,response.url.endswith(target) or ('NEXT_REDIRECT' in response.text and target in response.text))
        check(origin+'-uploads-anonymous-denied',session.get(origin+'/uploads/catalog/nonexistent.png',timeout=20).status_code==401)
    report={'checks':len(cases),'failures':sum(not row['passed'] for row in cases),'cases':cases,
            'product_price_coverage':prices,'existing_media_samples':len(media),
            'browser_visual_review':'not_performed_by_this_api_check','financial_writes':False,
            'holoo_writes':False,'external_model_called':False}
    (ROOT/'audit-2026-10-20/panel-release-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='cases'}))
    for row in cases:
        if not row['passed']:print(json.dumps(row))
    return int(report['failures']>0)


if __name__=='__main__':raise SystemExit(main())
