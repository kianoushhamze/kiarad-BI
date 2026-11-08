"""Manager-authorized local counterpart registration. No ERP requests or financial writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import requests
from dotenv import load_dotenv
from sqlalchemy import text

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
load_dotenv(ROOT/'.env')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    from db import engine
    from operations import create_token
    with engine.connect() as conn:
        user=dict(conn.execute(text("SELECT id,role,password_version FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().one())
    session=requests.Session();session.trust_env=False
    session.headers['Authorization']='Bearer '+create_token(user)
    origin='http://127.0.0.1:8000'
    def request(method,path,**kwargs):
        response=session.request(method,origin+path,timeout=60,**kwargs)
        if not response.ok:
            print(json.dumps({'status':response.status_code,'detail':response.json().get('detail')},ensure_ascii=True));response.raise_for_status()
        return response.json()
    preview=request('GET','/kerman/coach/holoo-customers/import-preview')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'preview':preview,'applied':False,'holoo_writes':False}
    if args.apply:
        report['result']=request('POST','/kerman/coach/holoo-customers/import',json={'snapshot_id':preview['snapshot_id'],'confirm_local_only':True})
        report['applied']=True
        report['after']=request('GET','/kerman/coach/holoo-customers/import-preview')
        assert report['after']['new_bases']==0 and report['after']['reuse_explicit_links']==0,'Import not fully registered'
    report['selectable_bases']=len(request('GET','/api/compensation/bases').get('items',[]))
    folder=ROOT/'audit-2026-10-26';folder.mkdir(exist_ok=True)
    target=folder/('holoo-base-import-'+datetime.now(timezone.utc).strftime('%H%M%S%f')+'.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True));print(str(target))


if __name__=='__main__':main()
