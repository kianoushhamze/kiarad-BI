"""Conservative observed dwell/travel: missing telemetry never becomes misconduct."""
from collections import defaultdict
from datetime import date,datetime,time,timedelta,timezone
from math import cos,radians,ceil,isfinite
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy import text
from db import engine
from operations import current_user,MANAGER_ROLES
from iran_time import IRAN_TIMEZONE,iran_today
from agent_route_planner import distance_km

router=APIRouter(prefix='/tracking',tags=['tracking_analytics'])
BASE_SOURCES=('pharmacies','cosmetics_shops','kerman_bases_manual')
MAX_GAP_SECONDS=120
MIN_STOP_SECONDS=300


def valid_number(value):
    try:return isfinite(float(value))
    except (ValueError,TypeError):return False


def summarize(points,bases,sessions,*,begin,end):
    """Credit only bounded intervals with two valid observations in one session.

    Dwell includes both endpoints' uncertainty inside a base radius. Overlapping
    possible bases remain ambiguous. Travel is a straight-line lower estimate.
    No interpolation across poor fixes, session boundaries or telemetry gaps.
    """
    index=defaultdict(list);eligible=[];missing=[]
    for b in bases:
        lat,lon=b.get('latitude'),b.get('longitude')
        if not valid_number(lat) or not valid_number(lon) or not -90<=float(lat)<=90 or not -180<=float(lon)<=180:
            missing.append({'source':b['source'],'id':b['id'],'name':b.get('name')});continue
        b={**b,'latitude':float(lat),'longitude':float(lon),'radius_m':min(1000,max(25,float(b.get('visit_radius_m') or 150)))}
        eligible.append(b);index[(int(b['latitude']//.01),int(b['longitude']//.01))].append(b)
    def locate(p):
        lat,lon=p['latitude'],p['longitude'];cell=(int(lat//.01),int(lon//.01))
        delta_lat=ceil(1000/111000/.01)+1;delta_lon=ceil(1000/(111000*max(.001,abs(cos(radians(lat)))))/.01)+1
        candidates=eligible if delta_lon>100 else [b for i in range(-delta_lat,delta_lat+1) for j in range(-delta_lon,delta_lon+1) for b in index.get((cell[0]+i,cell[1]+j),[])]
        contained=[b for b in candidates if distance_km((lat,lon),(b['latitude'],b['longitude']))*1000+p['accuracy_m']<=b['radius_m']]
        return (contained[0]['source'],contained[0]['id']) if len(contained)==1 else None,len(contained)>1
    raw=sorted(points,key=lambda p:(str(p['session_id']),p['recorded_at'],p.get('id',0)))
    windows=[]
    for s in sessions:
        a=max(begin,s['started_at']);z=min(end,s.get('ended_at') or s['expires_at'],s['expires_at'])
        if z>a:windows.append((a,z))
    # Union prevents overlapping migrated sessions from inflating expected time.
    merged=[]
    for a,z in sorted(windows):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(z,merged[-1][1]))
        else:merged.append((a,z))
    expected=sum((z-a).total_seconds() for a,z in merged)
    sessions_by_id={str(s['id']):s for s in sessions}
    filtered=[];bad=0;ambiguous=0
    for p in raw:
        s=sessions_by_id.get(str(p['session_id']));at=p['recorded_at']
        inside=s and begin<=at<end and s['started_at']<=at<=min(s.get('ended_at') or end,s['expires_at'])
        good=bool(inside and not p.get('mocked') and valid_number(p.get('accuracy_m')) and 0<float(p['accuracy_m'])<=100 and valid_number(p.get('latitude')) and valid_number(p.get('longitude')) and -90<=float(p['latitude'])<=90 and -180<=float(p['longitude'])<=180)
        if good:
            p={**p,'latitude':float(p['latitude']),'longitude':float(p['longitude']),'accuracy_m':float(p['accuracy_m'])};key,overlap=locate(p);ambiguous+=int(overlap);filtered.append((p,key,True))
        else:bad+=1;filtered.append((p,None,False))
    observed=0.;travel_km=0.;gap_seconds=0.;implausible=0;dwell=defaultdict(float);stops=[];segment=None;previous=None
    def close():
        nonlocal segment
        if segment and segment['observed_seconds']>=MIN_STOP_SECONDS:stops.append(segment)
        segment=None
    for p,key,good in filtered:
        if previous:
            q,qkey,qgood=previous;seconds=(p['recorded_at']-q['recorded_at']).total_seconds()
            same=str(p['session_id'])==str(q['session_id'])
            if same and seconds>MAX_GAP_SECONDS:gap_seconds+=seconds
            linked=same and good and qgood and 0<seconds<=MAX_GAP_SECONDS
            km=distance_km((q['latitude'],q['longitude']),(p['latitude'],p['longitude'])) if linked else 0
            if linked and km*1000/seconds>55:implausible+=1;linked=False
            if linked:
                observed+=seconds;travel_km+=km
                if key and key==qkey:
                    dwell[key]+=seconds
                    if not segment or segment['base_key']!=key or segment['session_id']!=str(p['session_id']):
                        close();segment={'base_key':key,'session_id':str(p['session_id']),'started_at':q['recorded_at'],'ended_at':p['recorded_at'],'observed_seconds':seconds}
                    else:segment['ended_at']=p['recorded_at'];segment['observed_seconds']+=seconds
                else:close()
            else:close()
        previous=(p,key,good)
    close()
    lookup={(b['source'],b['id']):b for b in eligible};counts=defaultdict(int)
    for stop in stops:
        key=stop.pop('base_key');b=lookup[key];stop.update(base_source=key[0],base_id=key[1],name=b.get('name'));counts[key]+=1
    summaries=[{'base_source':b['source'],'base_id':b['id'],'name':b.get('name'),'observed_dwell_seconds':round(dwell[(b['source'],b['id'])]),'observed_stop_count':counts[(b['source'],b['id'])]} for b in eligible]
    summaries.sort(key=lambda b:(-b['observed_dwell_seconds'],b['base_source'],b['base_id']))
    return {'sample_count':len(raw),'usable_samples':len(raw)-bad,'excluded_samples':bad,'ambiguous_samples':ambiguous,'implausible_segments':implausible,
            'shift_window_seconds':round(expected),'observed_interval_seconds':round(observed),'unknown_seconds':round(max(0,expected-observed)),
            'telemetry_gap_seconds':round(gap_seconds),'coverage_ratio':round(min(1,observed/expected),4) if expected else None,
            'straight_line_travel_km':round(travel_km,3),'stops':stops,'bases':summaries,'missing_coordinates':missing,
            'thresholds':{'maximum_gap_seconds':MAX_GAP_SECONDS,'minimum_stop_seconds':MIN_STOP_SECONDS,'maximum_accuracy_m':100},
            'interpretation':'observed proximity and straight-line movement; not verified visits, productive hours, payroll or misconduct',
            'unknown_is_not_idle':True,'road_distance_estimated':False}


@router.get('/analytics')
def analytics(user_id:int,from_day:date|None=None,to_day:date|None=None,user=Depends(current_user)):
    if user.get('role') not in MANAGER_ROLES and user_id!=user['id']:raise HTTPException(403,'فقط تحلیل مسیر خودتان قابل مشاهده است.')
    first=from_day or iran_today();last=to_day or first
    if first<iran_today()-timedelta(days=30) or last>iran_today() or last<first or (last-first).days>30:raise HTTPException(422,'بازه باید در سی روز اخیر باشد.')
    begin=datetime.combine(first,time.min,IRAN_TIMEZONE);end=min(datetime.combine(last+timedelta(days=1),time.min,IRAN_TIMEZONE),datetime.now(timezone.utc))
    with engine.connect() as c:
        sessions=[dict(s) for s in c.execute(text('SELECT id,started_at,ended_at,expires_at FROM tracking_sessions WHERE user_id=:uid AND started_at<:end AND expires_at>:begin ORDER BY started_at'),{'uid':user_id,'begin':begin,'end':end}).mappings()]
        points=[dict(p) for p in c.execute(text('SELECT id,session_id,recorded_at,latitude,longitude,accuracy_m,mocked FROM tracking_points WHERE user_id=:uid AND recorded_at>=:begin AND recorded_at<:end ORDER BY recorded_at,id LIMIT 20001'),{'uid':user_id,'begin':begin,'end':end}).mappings()]
        if len(points)>20000:raise HTTPException(422,'بازه بیش از سقف تحلیل است؛ بازهٔ کوتاه‌تری انتخاب کنید تا زمان ناقص گزارش نشود.')
        bases=[]
        for source in BASE_SOURCES:
            chunk=c.execute(text('SELECT id,name,latitude,longitude,visit_radius_m FROM '+source+' ORDER BY id LIMIT 5001')).mappings().all()
            if len(chunk)>5000:raise HTTPException(422,'تعداد پایگاه‌ها بیش از سقف این تحلیل است؛ محدوده را تفکیک کنید.')
            bases.extend(dict(b,source=source) for b in chunk)
    result=summarize(points,bases,sessions,begin=begin,end=end)
    return result|{'user_id':user_id,'from_day':first,'to_day':last,'as_of':datetime.now(timezone.utc),'recommendations':[
        'برای پایگاه‌های کم‌پوشش، گزارش ویزیت معتبر و علت ثبت‌شده را جدا بررسی کنید.',
        'فاصله‌های بی‌داده را با وضعیت اینترنت، مجوز و توضیح فرد تطبیق دهید؛ آن‌ها زمان کم‌کاری نیستند.',
        'برای کاهش سفر، ترتیب پایگاه‌های روزهای آینده را در برنامهٔ مسیر بازبینی کنید.']}
