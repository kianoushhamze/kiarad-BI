"""Versioned monthly visit plans. CEO approval publishes routes; payroll is separate."""
from datetime import date, time
from typing import Literal
import json,re
import jdatetime
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import text
from db import engine
from operations import current_user,MANAGER_ROLES
from iran_time import iran_today

router=APIRouter(prefix='/monthly-visit-plans',tags=['monthly_visit_plans'])
BASES={'pharmacies','cosmetics_shops','kerman_bases_manual'}
MAX_STOPS_PER_DAY=12


def ensure(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS monthly_visit_plans(
        id BIGSERIAL PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
        salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),month TEXT NOT NULL,
        revision INTEGER NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),
        status TEXT NOT NULL DEFAULT 'draft',note TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),reviewed_by INTEGER REFERENCES users(id),
        reviewed_at TIMESTAMPTZ,review_note TEXT,UNIQUE(user_id,month,revision))'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS monthly_visit_plan_stops(
        id BIGSERIAL PRIMARY KEY,plan_id BIGINT NOT NULL REFERENCES monthly_visit_plans(id),
        visit_date DATE NOT NULL,base_source TEXT NOT NULL,base_id INTEGER NOT NULL,
        stop_order INTEGER NOT NULL,objective TEXT NOT NULL,route_id INTEGER REFERENCES visit_route_assignments(id),
        outcome_status VARCHAR(50),holoo_preinvoice_code VARCHAR(100),order_amount_rial BIGINT DEFAULT 0,
        outcome_notes TEXT,follow_up_date DATE,
        UNIQUE(plan_id,visit_date,base_source,base_id),UNIQUE(plan_id,visit_date,stop_order))'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS monthly_visit_plan_events(
        id BIGSERIAL PRIMARY KEY,plan_id BIGINT NOT NULL REFERENCES monthly_visit_plans(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),event TEXT NOT NULL,note TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS monthly_visit_workday_reviews(
        id BIGSERIAL PRIMARY KEY,plan_id BIGINT NOT NULL REFERENCES monthly_visit_plans(id),
        work_date DATE NOT NULL,credited_days NUMERIC(5,3) NOT NULL CHECK(credited_days>=0 AND credited_days<=1),
        evidence JSONB NOT NULL,review_note TEXT NOT NULL,reviewed_by INTEGER NOT NULL REFERENCES users(id),
        reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),fact_id INTEGER,
        UNIQUE(plan_id,work_date))'''))
    conn.execute(text('ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS start_time TIME'))
    conn.execute(text('ALTER TABLE monthly_visit_plan_stops ADD COLUMN IF NOT EXISTS end_time TIME'))
    if conn.execute(text("SELECT to_regclass('visit_route_assignments') IS NOT NULL")).scalar():
        conn.execute(text('ALTER TABLE visit_route_assignments ADD COLUMN IF NOT EXISTS start_time TIME'))
        conn.execute(text('ALTER TABLE visit_route_assignments ADD COLUMN IF NOT EXISTS end_time TIME'))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS monthly_visit_one_approved ON monthly_visit_plans(user_id,month) WHERE status='approved'"))


@router.on_event('startup')
def startup():
    with engine.begin() as conn:ensure(conn)


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class Stop(Strict):
    visit_date:date
    base_source:Literal['pharmacies','cosmetics_shops','kerman_bases_manual']
    base_id:int=Field(gt=0)
    stop_order:int=Field(ge=1,le=100)
    objective:str=Field(min_length=3,max_length=500)
    start_time:time|None=None
    end_time:time|None=None


class Draft(Strict):
    user_id:int=Field(gt=0)
    month:str
    stops:list[Stop]=Field(min_length=1,max_length=600)
    note:str=Field(default='',max_length=2000)


class Decision(Strict):
    decision:Literal['approved','returned']
    note:str=Field(min_length=3,max_length=2000)
    allow_shared:bool=False


class OrderStop(Strict):
    base_source:Literal['pharmacies','cosmetics_shops','kerman_bases_manual']
    base_id:int=Field(gt=0)


class OrderRequest(Strict):
    stops:list[OrderStop]=Field(min_length=1,max_length=MAX_STOPS_PER_DAY)


class Workday(Strict):
    work_date:date
    credited_days:float=Field(ge=0,le=1)
    note:str=Field(min_length=8,max_length=2000)


def month_window(month):
    if not re.fullmatch(r'14\d{2}-(0[1-9]|1[0-2])',month):raise HTTPException(422,'ماه شمسی معتبر مانند ۱۴۰۵-۰۹ لازم است؛ ارقام را انگلیسی وارد کنید.')
    y,m=map(int,month.split('-'))
    start=jdatetime.date(y,m,1).togregorian()
    end=jdatetime.date(y+1,1,1).togregorian() if m==12 else jdatetime.date(y,m+1,1).togregorian()
    return start,end


def ceo(user):
    if user.get('role')!='ceo':raise HTTPException(403,'تأیید برنامه و کارکرد فقط با مدیرعامل است.')


def plan(conn,ident,user,lock=False):
    row=conn.execute(text('SELECT * FROM monthly_visit_plans WHERE id=:id'+(' FOR UPDATE' if lock else '')),{'id':ident}).mappings().first()
    if not row:raise HTTPException(404,'برنامه پیدا نشد.')
    if user.get('role') not in MANAGER_ROLES and row['user_id']!=user['id']:raise HTTPException(403,'این برنامه متعلق به شما نیست.')
    return dict(row)


def event(conn,ident,user,kind,note):
    conn.execute(text('INSERT INTO monthly_visit_plan_events(plan_id,actor_id,event,note) VALUES(:id,:actor,:kind,:note)'),{'id':ident,'actor':user['id'],'kind':kind,'note':note})


def schedule_guard(stops):
    """Optional per-day time windows: all stops of a day are timed or none is."""
    days={}
    for stop in stops:days.setdefault(stop.visit_date,[]).append(stop)
    for day,items in days.items():
        if len(items)>MAX_STOPS_PER_DAY:raise HTTPException(422,f'هر روز حداکثر {MAX_STOPS_PER_DAY} توقف می‌پذیرد؛ روز {day.isoformat()} بیشتر دارد.')
        timed=[s for s in items if s.start_time is not None or s.end_time is not None]
        if not timed:continue
        if len(timed)!=len(items):raise HTTPException(422,'برای هر روز یا ساعت همهٔ توقف‌ها ثبت شود یا برای هیچ‌کدام؛ زمان‌بندی نیمه‌کاره مجاز نیست.')
        for stop in timed:
            if not stop.start_time or not stop.end_time or stop.end_time<=stop.start_time:
                raise HTTPException(422,'ساعت پایان هر توقف باید بعد از ساعت شروع آن باشد.')
        ordered=sorted(timed,key=lambda s:s.start_time)
        for first,second in zip(ordered,ordered[1:]):
            if second.start_time<first.end_time:
                raise HTTPException(422,'بازهٔ زمانی دو توقف در یک روز هم‌پوشانی دارد؛ ساعت‌ها را اصلاح کنید.')


@router.get('')
def list_plans(month:str,q:str='',user=Depends(current_user)):
    month_window(month)
    with engine.connect() as conn:
        rows=conn.execute(text('''SELECT p.*,u.full_name FROM monthly_visit_plans p JOIN users u ON u.id=p.user_id
            WHERE month=:month AND u.full_name ILIKE :q'''+('' if user.get('role') in MANAGER_ROLES else ' AND p.user_id=:actor')+' ORDER BY p.user_id,p.revision DESC'),{'month':month,'actor':user['id'],'q':'%'+q[:100]+'%'}).mappings().all()
    return {'items':[dict(r) for r in rows],'can_approve':user.get('role')=='ceo'}


@router.get('/options')
def options(q:str='',user=Depends(current_user)):
    with engine.connect() as conn:
        users=[dict(r) for r in conn.execute(text('SELECT id,full_name FROM users WHERE is_active::text IN (\'1\',\'true\',\'t\') AND salesperson_id IS NOT NULL AND full_name ILIKE :q'+('' if user.get('role') in MANAGER_ROLES else ' AND id=:id')+' ORDER BY full_name'),{'id':user['id'],'q':'%'+q[:100]+'%'}).mappings()]
        bases=[dict(r,source=source) for source in sorted(BASES) for r in conn.execute(text("SELECT id,name,city FROM "+source+" WHERE concat_ws(' ',name,city) ILIKE :q ORDER BY name"),{'q':'%'+q[:100]+'%'}).mappings()]
    return {'users':users,'bases':bases,'can_approve':user.get('role')=='ceo'}


def haversine_m(first, second):
    from math import asin, cos, radians, sin, sqrt
    lat1, lng1 = first
    lat2, lng2 = second
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    value = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * 6371000 * asin(sqrt(min(1.0, value)))


@router.post('/order-suggestion')
def order_suggestion(data:OrderRequest,user=Depends(current_user)):
    """Nearest-neighbour order for one day; stops without coordinates keep input order."""
    coords={}
    with engine.connect() as conn:
        for source in sorted({s.base_source for s in data.stops}):
            ids=[s.base_id for s in data.stops if s.base_source==source]
            for row in conn.execute(text('SELECT id,latitude,longitude FROM '+source+' WHERE id=ANY(:ids)'),{'ids':ids}).mappings():
                if row['latitude'] is not None and row['longitude'] is not None:
                    coords[(source,row['id'])]=(float(row['latitude']),float(row['longitude']))
    missing=[{'base_source':s.base_source,'base_id':s.base_id} for s in data.stops if (s.base_source,s.base_id) not in coords]
    remaining=[index for index,s in enumerate(data.stops) if (s.base_source,s.base_id) in coords]
    order=[];current=None;distance=0.0
    while remaining:
        if current is None:pick=remaining[0]
        else:pick=min(remaining,key=lambda i:haversine_m(current,coords[(data.stops[i].base_source,data.stops[i].base_id)]))
        point=coords[(data.stops[pick].base_source,data.stops[pick].base_id)]
        if current is not None:distance+=haversine_m(current,point)
        current=point;order.append(pick);remaining.remove(pick)
    order+=[index for index,s in enumerate(data.stops) if (s.base_source,s.base_id) not in coords]
    note=('ترتیب پیشنهادی بر پایهٔ نزدیک‌ترین پایگاه محاسبه شد.' if not missing else
          f'{len(missing)} پایگاه مختصات ثبت‌شده ندارد و در انتها با ترتیب فعلی می‌ماند؛ ابتدا موقعیت آن‌ها را ثبت کنید.')
    return {'order':order,'distance_m':round(distance),'missing_coordinates':missing,'note':note}


@router.post('',status_code=201)
def create_draft(data:Draft,user=Depends(current_user)):
    start,end=month_window(data.month)
    if data.user_id!=user['id'] and user.get('role') not in MANAGER_ROLES:raise HTTPException(403,'فقط برنامهٔ خودتان را می‌توانید بنویسید.')
    if end<=iran_today():raise HTTPException(422,'برای ماه پایان‌یافته برنامهٔ تازه ساخته نمی‌شود.')
    schedule_guard(data.stops)
    seen=set();orders=set()
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('monthly-visit-plans',0))"))
        person=conn.execute(text('SELECT salesperson_id FROM users WHERE id=:id AND is_active::text IN (\'1\',\'true\',\'t\')'),{'id':data.user_id}).scalar()
        if not person:raise HTTPException(422,'حساب فعال متصل به پروفایل پرسنلی لازم است.')
        for stop in data.stops:
            if not start<=stop.visit_date<end or stop.visit_date<iran_today():raise HTTPException(422,'روزهای برنامه باید در ماه انتخاب‌شده و از امروز به بعد باشند.')
            key=(stop.visit_date,stop.base_source,stop.base_id);order=(stop.visit_date,stop.stop_order)
            if key in seen or order in orders:raise HTTPException(422,'پایگاه یا ترتیب توقف روز تکراری است.')
            seen.add(key);orders.add(order)
            if not conn.execute(text('SELECT 1 FROM '+stop.base_source+' WHERE id=:id'),{'id':stop.base_id}).scalar():raise HTTPException(422,'پایگاه انتخاب‌شده وجود ندارد.')
        revision=conn.execute(text('SELECT COALESCE(MAX(revision),0)+1 FROM monthly_visit_plans WHERE user_id=:u AND month=:m'),{'u':data.user_id,'m':data.month}).scalar()
        ident=conn.execute(text('INSERT INTO monthly_visit_plans(user_id,salesperson_id,month,revision,created_by,note) VALUES(:u,:sp,:m,:r,:a,:n) RETURNING id'),{'u':data.user_id,'sp':person,'m':data.month,'r':revision,'a':user['id'],'n':data.note}).scalar_one()
        for stop in data.stops:conn.execute(text('INSERT INTO monthly_visit_plan_stops(plan_id,visit_date,base_source,base_id,stop_order,objective,start_time,end_time) VALUES(:p,:visit_date,:base_source,:base_id,:stop_order,:objective,:start_time,:end_time)'),{'p':ident,**stop.model_dump()})
        event(conn,ident,user,'draft',data.note)
    return {'id':ident,'status':'draft','revision':revision,'routes_published':False}


def evidence(conn,p):
    return [dict(r) for r in conn.execute(text('''SELECT s.*,COALESCE(b.name,c.name,m.name) AS base_name,
        EXISTS(SELECT 1 FROM base_checkins ci WHERE ci.salesperson_id=:sp AND ci.base_source=s.base_source
            AND ci.base_id=s.base_id AND ci.checked_in_at::date=s.visit_date AND ci.status='verified') AS verified_visit,
        EXISTS(SELECT 1 FROM daily_reports d WHERE d.salesperson_id=:sp AND d.report_date=s.visit_date) AS has_daily_report,
        EXISTS(SELECT 1 FROM monthly_visit_workday_reviews w WHERE w.plan_id=s.plan_id AND w.work_date=s.visit_date) AS workday_reviewed,
        EXISTS(SELECT 1 FROM visit_route_assignments r WHERE r.base_source=s.base_source AND r.base_id=s.base_id
            AND r.visit_date=s.visit_date AND r.user_id<>:u) AS conflict,
        (SELECT string_agg(DISTINCT u2.full_name,'، ') FROM visit_route_assignments r2 JOIN users u2 ON u2.id=r2.user_id
            WHERE r2.base_source=s.base_source AND r2.base_id=s.base_id
            AND r2.visit_date=s.visit_date AND r2.user_id<>:u) AS conflict_with
        FROM monthly_visit_plan_stops s
        LEFT JOIN pharmacies b ON s.base_source='pharmacies' AND b.id=s.base_id
        LEFT JOIN cosmetics_shops c ON s.base_source='cosmetics_shops' AND c.id=s.base_id
        LEFT JOIN kerman_bases_manual m ON s.base_source='kerman_bases_manual' AND m.id=s.base_id
        WHERE s.plan_id=:p ORDER BY s.visit_date,s.stop_order'''),{'sp':p['salesperson_id'],'u':p['user_id'],'p':p['id']}).mappings()]


@router.get('/{ident}')
def detail(ident:int,user=Depends(current_user)):
    with engine.connect() as conn:
        p=plan(conn,ident,user);stops=evidence(conn,p)
        for stop in stops:
            stop['locked_for_revision']=stop['visit_date']<=iran_today() or stop['verified_visit'] or stop['has_daily_report'] or stop['workday_reviewed']
            stop['start_time']=stop['start_time'].strftime('%H:%M') if stop.get('start_time') else None
            stop['end_time']=stop['end_time'].strftime('%H:%M') if stop.get('end_time') else None
        events=[dict(r) for r in conn.execute(text('SELECT event,note,actor_id,created_at FROM monthly_visit_plan_events WHERE plan_id=:id ORDER BY id'),{'id':ident}).mappings()]
        days={s['visit_date'] for s in stops}
        summary={'planned_stops':len(stops),'verified_stops':sum(s['verified_visit'] for s in stops),'planned_days':len(days),'conflicts':sum(s['conflict'] for s in stops),
                 'timed_stops':sum(1 for s in stops if s['start_time']),
                 'fully_completed_days':sum(all(s['verified_visit'] and s['has_daily_report'] for s in stops if s['visit_date']==d) for d in days)}
    return {'plan':p,'stops':stops,'summary':summary,'history':events,'payroll_note':'این گزارش به‌تنهایی کارکرد حقوقی نمی‌سازد؛ بازبینی مدیرعامل و تطبیق منابع لازم است.'}


@router.post('/{ident}/submit')
def submit(ident:int,user=Depends(current_user)):
    with engine.begin() as conn:
        p=plan(conn,ident,user,True)
        if p['status'] not in {'draft','returned'}:raise HTTPException(409,'فقط پیش‌نویس یا برنامهٔ برگشتی قابل ارسال است.')
        conn.execute(text("UPDATE monthly_visit_plans SET status='submitted' WHERE id=:id"),{'id':ident});event(conn,ident,user,'submitted','ارسال برای بازبینی مدیرعامل')
    return {'status':'submitted','routes_published':False}


@router.post('/{ident}/review')
def review(ident:int,data:Decision,user=Depends(current_user)):
    ceo(user)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('monthly-visit-plans',0))"))
        p=plan(conn,ident,user,True)
        if p['status']!='submitted':raise HTTPException(409,'برنامه در انتظار تأیید نیست.')
        if data.decision=='approved':
            previous=conn.execute(text("SELECT id FROM monthly_visit_plans WHERE user_id=:u AND month=:m AND status='approved' FOR UPDATE"),{'u':p['user_id'],'m':p['month']}).scalar()
            retained=[]
            if previous:
                if conn.execute(text('SELECT 1 FROM payroll_approval_history WHERE salesperson_id=:sp AND payroll_month=:m'),{'sp':p['salesperson_id'],'m':p['month']}).scalar():raise HTTPException(409,'فیش این دوره تصویب شده؛ برنامهٔ دورهٔ بسته تغییر نمی‌کند.')
                # Preserve whole days, including pending/rejected evidence and
                # zero-day reviews. Only untouched future days may be replaced.
                old_stops=list(conn.execute(text('SELECT * FROM monthly_visit_plan_stops WHERE plan_id=:id ORDER BY visit_date,stop_order'),{'id':previous}).mappings())
                recorded_days=set(conn.execute(text('''SELECT s.visit_date FROM monthly_visit_plan_stops s
                    WHERE s.plan_id=:id AND (EXISTS(SELECT 1 FROM base_checkins c WHERE c.salesperson_id=:sp
                        AND c.base_source=s.base_source AND c.base_id=s.base_id AND c.checked_in_at::date=s.visit_date)
                    OR EXISTS(SELECT 1 FROM monthly_visit_workday_reviews w WHERE w.plan_id=:id AND w.work_date=s.visit_date)
                    OR EXISTS(SELECT 1 FROM daily_reports d WHERE d.salesperson_id=:sp AND d.report_date=s.visit_date)
                    OR EXISTS(SELECT 1 FROM compensation_facts f WHERE f.salesperson_id=:sp AND f.kind='workday' AND f.event_date=s.visit_date))'''),{'id':previous,'sp':p['salesperson_id']}).scalars())
                locked_days={s['visit_date'] for s in old_stops if s['visit_date']<=iran_today()}|recorded_days
                retained=[dict(s) for s in old_stops if s['visit_date'] in locked_days]
            stops=evidence(conn,p)
            conflicts=[s for s in stops if s['conflict']]
            if conflicts and not data.allow_shared:
                names=sorted({s['conflict_with'] for s in conflicts if s['conflict_with']})
                raise HTTPException(409,f'{len(conflicts)} توقف با مسیر نیروی دیگر در همان روز مشترک است'+(' ('+'، '.join(names)+')' if names else '')+'؛ اگر ویزیت مشترک را می‌پذیرید، گزینهٔ اجازهٔ ویزیت مشترک را با دلیل روشن انتخاب کنید.')
            if conflicts and len(data.note.strip())<8:
                raise HTTPException(422,'برای اجازهٔ ویزیت مشترک، دلیل روشن مدیرعامل (دست‌کم هشت نویسه) لازم است.')
            if any(s['visit_date']<iran_today() for s in stops):raise HTTPException(409,'برنامه شامل روز گذشته است؛ پیش‌نویس تازه بسازید.')
            if previous:
                if any(s['visit_date'] in locked_days or s['visit_date']<=iran_today() for s in stops):raise HTTPException(409,'روزهای گذشته، امروز یا دارای شواهد اجرا قفل‌اند؛ فقط روزهای آیندهٔ بدون شواهد را در اصلاحیه بنویسید.')
                retained_ids={s['id'] for s in retained}
                old_routes=[s['route_id'] for s in old_stops if s['id'] not in retained_ids and s['route_id'] is not None]
                if old_routes:conn.execute(text('UPDATE monthly_visit_plan_stops SET route_id=NULL WHERE plan_id=:id AND route_id=ANY(:routes)'),{'id':previous,'routes':old_routes})
                if old_routes:conn.execute(text('DELETE FROM visit_route_assignments WHERE id=ANY(:ids)'),{'ids':old_routes})
                conn.execute(text("UPDATE monthly_visit_plans SET status='superseded' WHERE id=:id"),{'id':previous})
                event(conn,previous,user,'superseded',f'جایگزین با نسخهٔ مصوب شمارهٔ {ident}؛ ردیف‌های برنامه و تاریخچه حفظ شدند.')
                for old in retained:
                    conn.execute(text('''INSERT INTO monthly_visit_plan_stops(plan_id,visit_date,base_source,base_id,stop_order,objective,route_id,start_time,end_time)
                        VALUES(:p,:visit_date,:base_source,:base_id,:stop_order,:objective,:route_id,:start_time,:end_time)'''),{**old,'p':ident})
                conn.execute(text('''INSERT INTO monthly_visit_workday_reviews(plan_id,work_date,credited_days,evidence,review_note,reviewed_by,reviewed_at,fact_id)
                    SELECT :new,work_date,credited_days,evidence,review_note,reviewed_by,reviewed_at,fact_id FROM monthly_visit_workday_reviews WHERE plan_id=:old'''),{'new':ident,'old':previous})
                if retained:event(conn,ident,user,'history_retained',f'{len(retained)} توقفِ گذشته یا دارای شواهد و کارکرد قبلی بدون تغییر منتقل شدند.')
            for s in stops:
                rid=conn.execute(text('''INSERT INTO visit_route_assignments(user_id,salesperson_id,base_source,base_id,visit_date,stop_order,note,assigned_by,start_time,end_time)
                    VALUES(:u,:sp,:base_source,:base_id,:visit_date,:stop_order,:objective,:actor,:start_time,:end_time)
                    ON CONFLICT(user_id,base_source,base_id,visit_date) DO UPDATE SET stop_order=EXCLUDED.stop_order,note=EXCLUDED.note,start_time=EXCLUDED.start_time,end_time=EXCLUDED.end_time RETURNING id'''),{**s,'u':p['user_id'],'sp':p['salesperson_id'],'actor':user['id']}).scalar_one()
                conn.execute(text('UPDATE monthly_visit_plan_stops SET route_id=:r WHERE id=:id'),{'r':rid,'id':s['id']})
            if conflicts:
                days=sorted({str(s['visit_date']) for s in conflicts})
                event(conn,ident,user,'shared_visit_approved',f'{len(conflicts)} توقف مشترک با مسیر نیروی دیگر با تأیید صریح مدیرعامل مجاز شد: {data.note.strip()[:200]} · روزها: {", ".join(days)[:300]}')
        conn.execute(text('UPDATE monthly_visit_plans SET status=:s,reviewed_by=:a,reviewed_at=NOW(),review_note=:n WHERE id=:id'),{'s':data.decision,'a':user['id'],'n':data.note,'id':ident})
        event(conn,ident,user,data.decision,data.note)
    return {'status':data.decision,'routes_published':data.decision=='approved'}


@router.post('/{ident}/workday-review')
def review_workday(ident:int,data:Workday,user=Depends(current_user)):
    ceo(user)
    with engine.begin() as conn:
        p=plan(conn,ident,user,True)
        if p['status']!='approved':raise HTTPException(409,'فقط اجرای برنامهٔ مصوب می‌تواند مبنای کارکرد شود.')
        if conn.execute(text('SELECT 1 FROM monthly_visit_workday_reviews WHERE plan_id=:p AND work_date=:d'),{'p':ident,'d':data.work_date}).scalar():raise HTTPException(409,'کارکرد این روز قبلاً بازبینی شده است؛ دوباره ثبت نمی‌شود.')
        if data.work_date>=iran_today():raise HTTPException(422,'روز کارکرد باید پایان یافته باشد.')
        stops=[s for s in evidence(conn,p) if s['visit_date']==data.work_date]
        if not stops:raise HTTPException(422,'این روز در برنامه نیست.')
        if data.credited_days>0 and not any(s['verified_visit'] and s['has_daily_report'] for s in stops):raise HTTPException(422,'ویزیت معتبر و گزارش کار برای تأیید کارکرد لازم است.')
        if data.credited_days==1 and not all(s['verified_visit'] and s['has_daily_report'] for s in stops):raise HTTPException(422,'برای کارکرد کامل باید همهٔ ویزیت‌های برنامه تطبیق داشته باشند؛ کارکرد جزئی را مستند تعیین کنید.')
        # Reuse payroll's own locked, closed-period and duplicate-day validation.
        import payroll_service
        raw=conn.connection.driver_connection
        with raw.cursor() as cur:
            fact=payroll_service.record_fact(cur,p['salesperson_id'],{'event_date':data.work_date.isoformat(),'event_key':f'monthly-plan:{ident}:{data.work_date}',
                'kind':'workday','quantity':data.credited_days,'amount':0,'source_note':data.note},user,allow_zero_workday=True)
        conn.execute(text('''INSERT INTO monthly_visit_workday_reviews(plan_id,work_date,credited_days,evidence,review_note,reviewed_by,fact_id)
            VALUES(:p,:d,:q,CAST(:e AS JSONB),:n,:a,:f)'''),{'p':ident,'d':data.work_date,'q':data.credited_days,'e':json.dumps(stops,default=str),'n':data.note,'a':user['id'],'f':fact['id']})
        event(conn,ident,user,'workday_review',data.note)
    return {'status':'reviewed','payroll_fact_id':fact['id'],'payroll_approved':False}
