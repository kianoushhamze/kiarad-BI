"""Immutable reviewed recurring recipes, durable cycles and bounded automation."""
from datetime import date,datetime,time,timedelta,timezone
from threading import Event,Thread
from typing import Literal
from uuid import UUID,uuid4,uuid5,NAMESPACE_URL
import hashlib,json,calendar,os
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator
from sqlalchemy import text
from db import engine
from operations import current_user
from iran_time import IRAN_TIMEZONE,iran_today
from agent_center import ceo,encode,Approval,Objective,Policy

router=APIRouter(prefix='/agent-routines',tags=['agent_routines'])
_STOP=Event();_THREAD=None

class Strict(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Schedule(Strict):
    kind:Literal['daily','weekly','monthly','interval']='daily'
    local_time:time=time(8,30)
    weekdays:list[int]=Field(default_factory=lambda:[5],min_length=1,max_length=7)
    month_day:int=Field(default=1,ge=1,le=31)
    calendar:Literal['jalali','gregorian']='jalali'
    interval_hours:int=Field(default=24,ge=6,le=168)
    @field_validator('weekdays')
    @classmethod
    def valid_days(cls,v):
        if len(set(v))!=len(v) or any(d<0 or d>6 for d in v):raise ValueError('Distinct weekdays 0..6 required')
        return v
    @field_validator('local_time')
    @classmethod
    def local_only(cls,v):
        if v.tzinfo is not None or v.second or v.microsecond:raise ValueError('Use local Tehran HH:MM')
        return v
class PlanRecipe(Strict):
    objective:str=Field(min_length=10,max_length=6000)
    domains:list[str]=Field(min_length=1,max_length=9)
    source_ids:list[UUID]=Field(default_factory=list,max_length=10)
    allowed_user_ids:list[int]=Field(default_factory=list,max_length=50)
    auto_low_risk:bool=False
    daily_action_limit:int=Field(default=20,ge=1,le=50)
class DiscoveryRecipe(Strict):
    city:str|None=Field(default=None,max_length=100)
    max_items:int=Field(default=2000,ge=1,le=5000)
class RouteRecipe(Strict):
    month_mode:Literal['current','next']='next'
    routing:dict
    weekdays:list[int]=Field(default_factory=lambda:[0,1,2,3,5,6],min_length=1,max_length=7)
    auto_publish:bool=False
    @model_validator(mode='after')
    def validate_routing(self):
        if len(set(self.weekdays))!=len(self.weekdays) or any(d<0 or d>6 for d in self.weekdays):raise ValueError('Weekdays must be distinct 0..6')
        if set(self.routing)&{'dates','month'}:raise ValueError('Month and dates are generated from the reviewed recurring calendar')
        from agent_route_planner import RoutePolicy
        RoutePolicy.model_validate({**self.routing,'month':'1405-09','dates':['2026-11-23']})
        return self
class TemplateRecipe(Strict):
    contact_ids:list[UUID]=Field(min_length=1,max_length=20)
    purpose:Literal['service','settlement','order','marketing']
    subject:str=Field(default='پیام شرکت کیاراد',min_length=3,max_length=160)
    body:str=Field(min_length=3,max_length=3000)
    @model_validator(mode='after')
    def closed_template(self):
        if len(set(self.contact_ids))!=len(self.contact_ids):raise ValueError('Distinct contacts required')
        import string
        for template in (self.subject,self.body):
            try:fields=list(string.Formatter().parse(template))
            except ValueError:raise ValueError('Invalid template') from None
            if any(field is not None and (field!='customer_name' or fmt or conversion) for _,field,fmt,conversion in fields):raise ValueError('Only {customer_name} is supported; amounts cannot be invented')
        if '\r' in self.subject or '\n' in self.subject:raise ValueError('Subject cannot contain line breaks')
        return self
class TrainingRecipe(Strict):
    programme_id:UUID
    roles:list[Literal['visitor','salesperson','finance','sales_manager']]=Field(default_factory=lambda:['visitor','salesperson'],min_length=1,max_length=4)
    due_days:int=Field(default=7,ge=1,le=60)
    max_people_per_cycle:int=Field(default=20,ge=1,le=20)

class Routine(Strict):
    name:str=Field(min_length=3,max_length=120)
    kind:Literal['professional_plan','lead_discovery','monthly_routes','customer_messages','training_enrollment']
    schedule:Schedule=Field(default_factory=Schedule)
    recipe:dict
    @model_validator(mode='after')
    def valid_recipe(self):
        cls={'professional_plan':PlanRecipe,'lead_discovery':DiscoveryRecipe,'monthly_routes':RouteRecipe,'customer_messages':TemplateRecipe,'training_enrollment':TrainingRecipe}[self.kind]
        self.recipe=cls.model_validate(self.recipe).model_dump(mode='json')
        if self.kind=='professional_plan':
            from agent_playbooks import PLAYBOOKS
            if any(d not in PLAYBOOKS for d in self.recipe['domains']):raise ValueError('Unknown specialist domain')
            if self.recipe['auto_low_risk'] and not self.recipe['allowed_user_ids']:raise ValueError('Auto task assignment requires explicit team scope')
        if self.kind in {'lead_discovery','customer_messages'} and self.schedule.kind=='interval' and self.schedule.interval_hours<24:raise ValueError('Discovery/customer messaging interval must be at least 24h')
        return self


def next_time(schedule,after):
    s=Schedule.model_validate(schedule);local=after.astimezone(IRAN_TIMEZONE)
    if s.kind=='interval':return after+timedelta(hours=s.interval_hours)
    for offset in range(0,370):
        day=local.date()+timedelta(days=offset)
        if s.calendar=='jalali':
            import jdatetime
            jd=jdatetime.date.fromgregorian(date=day);month_days=31 if jd.month<=6 else 30 if jd.month<=11 or jd.isleap() else 29;month_match=jd.day==min(s.month_day,month_days)
        else:month_match=day.day==min(s.month_day,calendar.monthrange(day.year,day.month)[1])
        allowed=s.kind=='daily' or s.kind=='weekly' and day.weekday() in s.weekdays or s.kind=='monthly' and month_match
        candidate=datetime.combine(day,s.local_time,IRAN_TIMEZONE)
        if allowed and candidate>local:return candidate.astimezone(timezone.utc)
    raise ValueError('No next occurrence')


def ensure(c):
    for statement in (
        '''CREATE TABLE IF NOT EXISTS agent_routines(id UUID PRIMARY KEY,owner_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,
        kind TEXT NOT NULL,spec JSONB NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft',created_at TIMESTAMPTZ DEFAULT NOW(),
        approved_at TIMESTAMPTZ,next_run_at TIMESTAMPTZ,lease_until TIMESTAMPTZ,UNIQUE(owner_id,name))''',
        '''CREATE TABLE IF NOT EXISTS agent_routine_cycles(id UUID PRIMARY KEY,routine_id UUID NOT NULL REFERENCES agent_routines(id),
        scheduled_for TIMESTAMPTZ NOT NULL,state TEXT NOT NULL DEFAULT 'running',started_at TIMESTAMPTZ DEFAULT NOW(),finished_at TIMESTAMPTZ,
        result JSONB,error_code TEXT,UNIQUE(routine_id,scheduled_for))''',
        '''CREATE TABLE IF NOT EXISTS agent_routine_events(id BIGSERIAL PRIMARY KEY,routine_id UUID NOT NULL REFERENCES agent_routines(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,detail JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW())''',
        "CREATE INDEX IF NOT EXISTS routines_due ON agent_routines(next_run_at) WHERE state='active'",
    ):c.execute(text(statement))


def audit(c,rid,uid,kind,detail=None):c.execute(text('INSERT INTO agent_routine_events(routine_id,actor_id,kind,detail) VALUES(:id,:uid,:kind,CAST(:detail AS JSONB))'),{'id':str(rid),'uid':uid,'kind':kind,'detail':encode(detail or {})})


def owned(c,ident,user,lock=False):
    ceo(user);r=c.execute(text('SELECT * FROM agent_routines WHERE id=:id AND owner_id=:uid'+(' FOR UPDATE' if lock else '')),{'id':str(ident),'uid':user['id']}).mappings().first()
    if not r:raise HTTPException(404,'برنامهٔ تکرارشونده متعلق به این حساب پیدا نشد.')
    return dict(r)


@router.post('',status_code=201)
def create(data:Routine,user=Depends(current_user)):
    ceo(user);spec=data.model_dump(mode='json');sha=hashlib.sha256(encode(spec).encode()).hexdigest()
    with engine.begin() as c:
        c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'routine:{user["id"]}:{data.name}'})
        old=c.execute(text('SELECT id,digest FROM agent_routines WHERE owner_id=:uid AND name=:name'),{'uid':user['id'],'name':data.name}).mappings().first()
        if old:
            if old['digest']!=sha:raise HTTPException(409,'این نام برای تنظیمات دیگری ثبت شده؛ نسخهٔ قبلی را متوقف و نام نسخهٔ جدید را مشخص کنید.')
            return {'id':str(old['id']),'digest':sha,'replayed':True}
        if data.kind=='professional_plan':
            for uid in data.recipe['allowed_user_ids']:
                if not c.execute(text("SELECT 1 FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),{'id':uid}).scalar():raise HTTPException(422,'فرد مجاز باید حساب فعال واقعی داشته باشد.')
        if data.kind=='training_enrollment':
            from training_workflows import ensure as ensure_training
            ensure_training(c)
            if not c.execute(text("SELECT 1 FROM training_programmes WHERE id=:id AND owner_id=:uid AND state='published'"),{'id':data.recipe['programme_id'],'uid':user['id']}).scalar():raise HTTPException(422,'دورهٔ منتشرشده و بازبینی‌شدهٔ متعلق به شما لازم است.')
        if data.kind=='customer_messages':
            from outbound_messages import ensure as ensure_outbound
            ensure_outbound(c)
            for cid in data.recipe['contact_ids']:
                contact=c.execute(text('SELECT active,consent_scope FROM outbound_contacts WHERE id=:id'),{'id':str(cid)}).mappings().first()
                if not contact or not contact['active'] or data.recipe['purpose']=='marketing' and contact['consent_scope']!='marketing':raise HTTPException(422,'فهرست مخاطب و رضایت هر تماس را بازبینی کنید.')
        ident=uuid4();c.execute(text('INSERT INTO agent_routines(id,owner_id,name,kind,spec,digest) VALUES(:id,:uid,:name,:kind,CAST(:spec AS JSONB),:digest)'),{'id':str(ident),'uid':user['id'],'name':data.name,'kind':data.kind,'spec':encode(spec),'digest':sha});audit(c,ident,user['id'],'draft_created')
    return {'id':str(ident),'digest':sha,'replayed':False,'state':'draft'}


@router.get('')
def listing(user=Depends(current_user)):
    ceo(user)
    with engine.begin() as c:rows=c.execute(text('SELECT * FROM agent_routines WHERE owner_id=:uid ORDER BY created_at DESC LIMIT 100'),{'uid':user['id']}).mappings().all()
    return {'items':[dict(r) for r in rows],'scheduler_enabled':enabled()}


@router.get('/{ident}/cycles')
def cycles(ident:UUID,user=Depends(current_user)):
    with engine.begin() as c:
        owned(c,ident,user);rows=c.execute(text('SELECT * FROM agent_routine_cycles WHERE routine_id=:id ORDER BY scheduled_for DESC LIMIT 100'),{'id':str(ident)}).mappings().all()
    return {'items':[dict(r) for r in rows]}


@router.post('/{ident}/approve')
def approve(ident:UUID,data:Approval,user=Depends(current_user)):
    with engine.begin() as c:
        r=owned(c,ident,user,True)
        if r['digest']!=data.expected_digest:raise HTTPException(409,'نسخهٔ تنظیمات تغییر کرده است.')
        if r['state']=='review_required':raise HTTPException(409,'ابتدا نتیجهٔ چرخهٔ نامعلوم را تطبیق و ثبت کنید.')
        if r['state']=='active':return {'state':'active','next_run_at':r['next_run_at']}
        if r['kind']=='customer_messages':
            from outbound_messages import connected
            channels=c.execute(text('SELECT channel FROM outbound_contacts WHERE id=ANY(:ids)'),{'ids':[UUID(x) for x in r['spec']['recipe']['contact_ids']]}).scalars().all()
            if not channels or not all(connected(ch) for ch in channels):raise HTTPException(503,'کانال ارسال تنظیم نشده؛ ارسال خودکار فعال نشد.')
        nxt=next_time(r['spec']['schedule'],datetime.now(timezone.utc));c.execute(text("UPDATE agent_routines SET state='active',approved_at=NOW(),next_run_at=:next WHERE id=:id"),{'id':str(ident),'next':nxt});audit(c,ident,user['id'],'approved',{'digest':r['digest'],'next_run_at':nxt})
    return {'state':'active','next_run_at':nxt,'scheduler_enabled':enabled()}


@router.post('/{ident}/pause')
def pause(ident:UUID,user=Depends(current_user)):
    with engine.begin() as c:owned(c,ident,user,True);c.execute(text("UPDATE agent_routines SET state='paused' WHERE id=:id"),{'id':str(ident)});audit(c,ident,user['id'],'paused')
    return {'state':'paused','in_flight_may_finish':True}


def auto_scope(plan,recipe):
    safe={'team_signals','analyze_domain','market_research','grade_customers','create_task','create_content_draft','notify_user','target_scenarios','contract_review','tracking_analytics','training_progress','training_generate','prospect_discover','outbound_preview','training_my_courses'};team=set(recipe['allowed_user_ids'])
    if plan.get('blockers') or len(plan['steps'])>recipe['daily_action_limit']:return False
    for step in plan['steps']:
        if step['operation'] not in safe:return False
        if step['operation'] in {'create_task','notify_user'}:
            uid=step['payload'].get('assigned_to' if step['operation']=='create_task' else 'user_id')
            if type(uid) is not int or uid not in team:return False
    return True


def execute_recipe(r,cycle,user):
    spec=r['spec'];recipe=spec['recipe']
    if r['kind'] in {'professional_plan','monthly_routes'}:
        with engine.connect() as c:
            prior=c.execute(text("SELECT result->>'mission_id' FROM agent_routine_cycles WHERE routine_id=:id AND state='completed' AND result ? 'mission_id' ORDER BY scheduled_for DESC LIMIT 1"),{'id':str(r['id'])}).scalar()
            if prior:
                pending=c.execute(text("SELECT 1 FROM agent_missions m WHERE m.id=:id AND m.state IN ('draft','active','paused') AND EXISTS(SELECT 1 FROM agent_steps s WHERE s.mission_id=m.id AND s.state<>'applied')"),{'id':prior}).scalar()
                if pending:return {'mission_id':prior,'state':'previous_mission_pending','new_mission_created':False}
    key=uuid5(NAMESPACE_URL,'kiarad-routine:'+str(cycle['id']))
    if r['kind']=='lead_discovery':
        from prospect_pipeline import run_discovery,Discovery
        return run_discovery(Discovery(submission_key=key,**recipe),user)
    if r['kind']=='professional_plan':
        from agent_center import plan_objective,approve as approve_mission
        policy=Policy(mode='bounded_auto' if recipe['auto_low_risk'] else 'assisted',daily_action_limit=recipe['daily_action_limit'],monitor_user_ids=recipe['allowed_user_ids'],notify_employees=recipe['auto_low_risk'])
        mission=plan_objective(Objective(objective=recipe['objective'],domains=recipe['domains'],source_ids=recipe['source_ids'],policy=policy),user)
        with engine.connect() as c:plan=c.execute(text('SELECT plan FROM agent_missions WHERE id=:id'),{'id':mission['id']}).scalar()
        automatic=recipe['auto_low_risk'] and auto_scope(plan,recipe)
        if automatic:approve_mission(UUID(mission['id']),Approval(confirm=True,expected_digest=mission['digest']),user)
        return {'mission_id':mission['id'],'review_href':mission['review_href'],'automatically_approved_low_risk':automatic,'sensitive_steps_require_review':True}
    if r['kind']=='monthly_routes':
        import jdatetime
        from monthly_visit_plans import month_window
        from agent_center import route_mission,RouteMission,approve as approve_mission
        today=iran_today();jalali=jdatetime.date.fromgregorian(date=today);year,month=jalali.year,jalali.month
        if recipe['month_mode']=='next':month+=1
        if month==13:year+=1;month=1
        label=f'{year:04d}-{month:02d}';begin,end=month_window(label);dates=[];day=begin
        while day<end:
            if day>today and day.weekday() in recipe['weekdays']:dates.append(day.isoformat())
            day+=timedelta(days=1)
        result=route_mission(RouteMission(routing={**recipe['routing'],'month':label,'dates':dates},policy=Policy(mode='bounded_auto',allow_route_publication=recipe['auto_publish'])),user)
        automatic=recipe['auto_publish'] and result['routing']['feasible']
        if automatic:approve_mission(UUID(result['id']),Approval(confirm=True,expected_digest=result['digest']),user)
        return {'mission_id':result['id'],'review_href':result['review_href'],'routing':result['routing'],'auto_publication_authorized':automatic}
    if r['kind']=='training_enrollment':
        from training_workflows import publish as publish_training,Publish
        with engine.connect() as c:
            programme=c.execute(text("SELECT digest,state FROM training_programmes WHERE id=:id AND owner_id=:uid"),{'id':recipe['programme_id'],'uid':user['id']}).mappings().first()
            if not programme or programme['state']!='published':raise HTTPException(409,'دوره فعال و منتشرشده نیست؛ فراگیر جدید ثبت نشد.')
            people=c.execute(text("SELECT id FROM users u WHERE role=ANY(:roles) AND is_active::text IN ('1','true','t') AND NOT EXISTS(SELECT 1 FROM training_enrollments e WHERE e.programme_id=:programme AND e.user_id=u.id) ORDER BY id LIMIT :limit"),{'roles':recipe['roles'],'programme':recipe['programme_id'],'limit':recipe['max_people_per_cycle']}).scalars().all()
        if not people:return {'new_enrollments':0,'state':'no_unenrolled_staff'}
        result=publish_training(UUID(recipe['programme_id']),Publish(confirm=True,expected_digest=programme['digest'],user_ids=list(people),due_date=datetime.now(timezone.utc)+timedelta(days=recipe['due_days'])),user)
        return result|{'new_enrollments':len(result['enrollments'])}
    if r['kind']=='customer_messages':
        from outbound_messages import preview,approve as approve_message,Message,Approve
        receipts=[]
        for cid in recipe['contact_ids']:
            with engine.connect() as c:contact=c.execute(text('SELECT o.active,c.name FROM outbound_contacts o JOIN customers c ON c.id=o.customer_id WHERE o.id=:id'),{'id':str(cid)}).mappings().first()
            if not contact or not contact['active']:receipts.append({'contact_id':cid,'state':'revoked_skipped'});continue
            variables={'customer_name':contact['name'] or 'مشتری گرامی'}
            try:
                msg=preview(Message(submission_key=uuid5(key,str(cid)),contact_id=cid,purpose=recipe['purpose'],subject=recipe['subject'].format(**variables),body=recipe['body'].format(**variables)),user)
            except HTTPException as exc:
                if exc.status_code!=409:raise
                receipts.append({'contact_id':cid,'state':'precondition_skipped','reason':str(exc.detail),'external_message_sent':False});continue
            if msg['state']=='draft':approve_message(UUID(msg['id']),Approve(confirm=True,expected_digest=msg['digest']),user)
            receipts.append({'message_id':msg['id'],'contact_id':cid,'state':'approved_queue','delivery_confirmed':False})
        return {'messages':receipts,'template_digest':r['digest'],'external_sending_separate_worker':True}
    raise HTTPException(422,'نوع برنامهٔ تکراری معتبر نیست.')


def run(ident,user,*,manual=False):
    ceo(user);now=datetime.now(timezone.utc)
    with engine.begin() as c:
        r=owned(c,ident,user,True)
        if r['state']!='active' or not r['approved_at']:raise HTTPException(409,'برنامهٔ تکراری فعال و مصوب لازم است.')
        if r['lease_until'] and r['lease_until']>now:raise HTTPException(409,'اجرای دیگری هنوز در حال انجام است.')
        if not manual and r['next_run_at']>now:return {'state':'not_due'}
        start=datetime.combine(now.astimezone(IRAN_TIMEZONE).date(),time.min,IRAN_TIMEZONE)
        count=c.execute(text('SELECT COUNT(*) FROM agent_routine_cycles x JOIN agent_routines r ON r.id=x.routine_id WHERE r.owner_id=:uid AND x.started_at>=:start'),{'uid':user['id'],'start':start}).scalar()
        if count>=20:raise HTTPException(429,'سقف روزانهٔ اجرای برنامه‌های تکراری تکمیل شده است.')
        recent=c.execute(text("SELECT 1 FROM agent_routine_cycles WHERE routine_id=:id AND started_at>NOW()-INTERVAL '20 minutes' LIMIT 1"),{'id':str(ident)}).scalar()
        if recent:raise HTTPException(429,'برای جلوگیری از تکرار، اجرای دوباره حداقل بیست دقیقه فاصله دارد.')
        slot=now if manual else r['next_run_at'];cycle={'id':uuid4(),'scheduled_for':slot}
        old=c.execute(text('SELECT state,result FROM agent_routine_cycles WHERE routine_id=:id AND scheduled_for=:slot'),{'id':str(ident),'slot':slot}).mappings().first()
        if old:return {'state':old['state'],'result':old['result'],'replayed':True}
        c.execute(text('INSERT INTO agent_routine_cycles(id,routine_id,scheduled_for) VALUES(:id,:routine,:slot)'),{'id':str(cycle['id']),'routine':str(ident),'slot':slot})
        nxt=next_time(r['spec']['schedule'],now);c.execute(text("UPDATE agent_routines SET lease_until=NOW()+INTERVAL '30 minutes',next_run_at=:next WHERE id=:id"),{'id':str(ident),'next':nxt});audit(c,ident,user['id'],'cycle_started',{'cycle_id':cycle['id'],'manual':manual})
    try:
        # Deactivation or role changes revoke recurring authority before any recipe action.
        with engine.connect() as c:active=c.execute(text("SELECT id,username,full_name,role,salesperson_id,password_version FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),{'id':user['id']}).mappings().first()
        if not active or active['role']!='ceo':raise HTTPException(403,'اختیار مالک برنامه تغییر کرده است.')
        result=execute_recipe(r,cycle,dict(active));state='completed';error=None
    except Exception as exc:
        result=None;state='failed' if r['kind']=='lead_discovery' else 'review_required';error='source_unavailable' if r['kind']=='lead_discovery' else 'cycle_failed_or_outcome_unknown'
        if isinstance(exc,HTTPException):result={'message':exc.detail,'status_code':exc.status_code}
    with engine.begin() as c:
        c.execute(text('UPDATE agent_routine_cycles SET state=:state,result=CAST(:result AS JSONB),error_code=:error,finished_at=NOW() WHERE id=:id'),{'id':str(cycle['id']),'state':state,'result':encode(result),'error':error});c.execute(text("UPDATE agent_routines SET lease_until=NULL,state=CASE WHEN :review THEN 'review_required' ELSE state END WHERE id=:id"),{'id':str(ident),'review':state=='review_required'});audit(c,ident,user['id'],'cycle_'+state,{'cycle_id':cycle['id'],'error_code':error})
    return {'cycle_id':str(cycle['id']),'state':state,'result':result,'error_code':error}


class Reconciliation(Strict):
    reviewed:Literal[True]
    note:str=Field(min_length=20,max_length=2000)

@router.post('/{ident}/reconcile')
def reconcile(ident:UUID,data:Reconciliation,user=Depends(current_user)):
    with engine.begin() as c:
        r=owned(c,ident,user,True)
        if r['state']!='review_required':raise HTTPException(409,'این برنامه منتظر تطبیق نتیجه نیست.')
        c.execute(text("UPDATE agent_routines SET state='paused',lease_until=NULL WHERE id=:id"),{'id':str(ident)})
        audit(c,ident,user['id'],'outcome_reviewed_no_retry',{'note':data.note})
    return {'state':'paused','old_cycle_retried':False,'new_schedule_requires_reapproval':True}

@router.post('/{ident}/run')
def run_now(ident:UUID,user=Depends(current_user)):return run(ident,user,manual=True)


def enabled():
    from agent_center import scheduler_enabled
    return scheduler_enabled() and os.getenv('KIARAD_ROUTINES_DISABLED','0').lower() not in {'1','true','yes'}


def loop():
    while not _STOP.wait(30):
        try:
            with engine.begin() as c:
                c.execute(text("UPDATE agent_routine_cycles SET state='review_required',error_code='interrupted_cycle' WHERE state='running' AND started_at<NOW()-INTERVAL '35 minutes'"))
                due=c.execute(text("SELECT id,owner_id FROM agent_routines WHERE state='active' AND next_run_at<=NOW() AND (lease_until IS NULL OR lease_until<NOW()) ORDER BY next_run_at LIMIT 5")).mappings().all()
            for r in due:
                with engine.connect() as c:u=c.execute(text("SELECT id,role FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),{'id':r['owner_id']}).mappings().first()
                if u and u['role']=='ceo':
                    try:run(r['id'],dict(u))
                    except HTTPException:pass
        except Exception:pass

@router.on_event('startup')
def startup():
    global _THREAD
    if enabled() and (_THREAD is None or not _THREAD.is_alive()):_STOP.clear();_THREAD=Thread(target=loop,daemon=True,name='kiarad-routines');_THREAD.start()

@router.on_event('shutdown')
def shutdown():_STOP.set()
