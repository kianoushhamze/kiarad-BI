"""Real OsmAnd listener -> Traccar JSON -> consented Kiarad shift; CI fixtures only."""
import argparse,json,os,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
p=argparse.ArgumentParser();p.add_argument('--seed',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args()
if os.getenv('KIARAD_REVIEW_DISPOSABLE_DB')!='1':raise SystemExit('Explicit disposable CI database required')
PASSWORD='CiTraccar-only-2026'
if a.seed:
    from sqlalchemy import text
    from db import engine
    from operations import hash_password
    with engine.begin() as c:
        if not c.execute(text("SELECT id FROM products WHERE code='CI-A'")).scalar():raise SystemExit('Synthetic CI catalog required')
        sp=c.execute(text("INSERT INTO salespersons(name) VALUES('CI GPS worker') RETURNING id")).scalar()
        for name,role,person in [('ci_traccar_manager','ceo',None),('ci_traccar_visitor','visitor',sp)]:
            c.execute(text('INSERT INTO users(username,full_name,password_hash,role,salesperson_id,is_active,password_version,created_at) VALUES(:name,:name,:password,:role,:sp,1,0,NOW())'),{'name':name,'password':hash_password(PASSWORD),'role':role,'sp':person})
    print('Synthetic GPS users seeded')
else:
    import requests
    base='http://127.0.0.1:8800';gateway='http://127.0.0.1:5055'
    def login(name):
        r=requests.post(base+'/auth/login',json={'username':name,'password':PASSWORD},timeout=10);r.raise_for_status();return r.json()
    chief=login('ci_traccar_manager');worker=login('ci_traccar_visitor')
    def call(method,path,data=None,session=worker,expected=200):
        r=requests.request(method,base+path,json=data,headers={'Authorization':'Bearer '+session['access_token']},timeout=10);assert r.status_code==expected,(path,r.status_code,r.text);return r.json()
    binding=call('POST','/tracking/traccar/devices',{'user_id':worker['user']['id'],'platform':'ios','label':'CI synthetic phone'},chief,201)
    def send(at,lat=30.29):
        r=requests.post(gateway,params={'id':binding['identifier'],'timestamp':at,'lat':lat,'lon':57.06,'accuracy':5,'batt':70},timeout=10);r.raise_for_status()
    # Wait for actual Java listener readiness, not just a running container.
    for attempt in range(60):
        try:send(int(time.time())-30);break
        except requests.RequestException:
            if attempt==59:raise
            time.sleep(1)
    time.sleep(1);assert not call('GET','/tracking/history?user_id='+str(worker['user']['id']))['items']
    shift=call('POST','/tracking/traccar/shift/start',{'device_id':binding['id'],'consent_version':'work-shift-location-v1','max_hours':1},expected=201)
    at=int(time.time())+1;send(at)
    for attempt in range(30):
        point=call('GET','/tracking/live')['items'][0]
        if point['recorded_at']:break
        time.sleep(1)
    assert point['source']=='traccar' and point['is_live'] and abs(point['latitude']-30.29)<.00001,point
    send(at);time.sleep(1);assert len(call('GET','/tracking/history?user_id='+str(worker['user']['id']))['items'])==1
    call('POST','/tracking/sessions/stop',{'session_id':shift['session_id'],'device_id':shift['device_id']});send(int(time.time())+3,30.30);time.sleep(2)
    assert len(call('GET','/tracking/history?user_id='+str(worker['user']['id']))['items'])==1
    assert requests.post(base+'/tracking/traccar/positions',json={},timeout=10).status_code==401
    result={'passed':True,'real_traccar_protocol':True,'before_shift_ignored':True,'live_dashboard_point':True,'duplicate_idempotent':True,'after_stop_ignored':True,'unauthenticated_forward_denied':True,'company_or_physical_phone_data_used':False}
    if a.output:a.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
