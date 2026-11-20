"""Trusted Traccar JSON forwarding into explicit, consented Kiarad work shifts."""
from datetime import datetime,timedelta,timezone
from typing import Literal
from uuid import UUID,uuid4,uuid5,NAMESPACE_URL
from urllib.parse import urlsplit
import hmac,json,os,re,secrets
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field,ValidationError,field_validator
from sqlalchemy import text
from db import engine
from operations import current_user,require_manager,MANAGER_ROLES,role_has_module_permission
from live_tracking import ensure as ensure_tracking,Start,start_session_in_connection,staff,require_map_permission

router=APIRouter(prefix='/tracking/traccar',tags=['traccar_bridge'])
FORWARD_PATH='/tracking/traccar/positions'
BODY_LIMIT=32768


def ensure(c):
    ensure_tracking(c)
    for statement in (
        '''ALTER TABLE tracking_sessions ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'kiarad' ''',
        '''CREATE TABLE IF NOT EXISTS traccar_devices(id UUID PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
        identifier TEXT NOT NULL UNIQUE,platform TEXT NOT NULL,label TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),revoked_at TIMESTAMPTZ,last_received_at TIMESTAMPTZ,last_recorded_at TIMESTAMPTZ)''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS traccar_active_owner ON traccar_devices(user_id) WHERE revoked_at IS NULL''',
        '''CREATE TABLE IF NOT EXISTS traccar_shifts(session_id UUID PRIMARY KEY REFERENCES tracking_sessions(id),
        device_id UUID NOT NULL REFERENCES traccar_devices(id),auth_version INTEGER NOT NULL DEFAULT 0)''',
        '''ALTER TABLE traccar_shifts ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 0''',
        '''CREATE INDEX IF NOT EXISTS traccar_shifts_device ON traccar_shifts(device_id)''',
        '''CREATE TABLE IF NOT EXISTS traccar_device_events(id BIGSERIAL PRIMARY KEY,device_id UUID NOT NULL REFERENCES traccar_devices(id),
        actor_id INTEGER NOT NULL REFERENCES users(id),kind TEXT NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW())''',
    ):c.execute(text(statement))


def token():return os.getenv('KIARAD_TRACCAR_FORWARD_TOKEN','')
def configured():return bool(re.fullmatch(r'[A-Za-z0-9_-]{32,200}',token()))
def enabled():return os.getenv('KIARAD_TRACCAR_ENABLED','0').lower() in {'1','true','yes'} and configured()
def authorize_forward(request):
    if not enabled():raise HTTPException(503,'Traccar receiver is disabled or not configured')
    supplied=request.headers.get('x-kiarad-traccar-token','')
    if len(supplied)>200 or not hmac.compare_digest(supplied.encode(),token().encode()):raise HTTPException(401,'Invalid forwarding credential')


def client_url():
    value=os.getenv('KIARAD_TRACCAR_CLIENT_URL','').strip().rstrip('/')
    try:
        url=urlsplit(value)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment: return None
        return value
    except ValueError:return None


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Binding(Strict):
    user_id:int=Field(gt=0)
    platform:Literal['ios','android']
    label:str=Field(min_length=2,max_length=100)
class Shift(Strict):
    device_id:UUID
    consent_version:Literal['work-shift-location-v1']
    max_hours:int=Field(default=8,ge=1,le=12)

@router.get('/devices')
def devices(user=Depends(current_user)):
    require_map_permission(user, 'can_read')
    manager=user.get('role') in MANAGER_ROLES
    with engine.begin() as c:
        rows=c.execute(text('''SELECT d.*,u.full_name,s.id AS session_id,s.device_id AS session_device_id,s.expires_at,s.started_at
        FROM traccar_devices d JOIN users u ON u.id=d.user_id
        LEFT JOIN LATERAL(SELECT ts.* FROM tracking_sessions ts JOIN traccar_shifts x ON x.session_id=ts.id
        WHERE x.device_id=d.id AND ts.ended_at IS NULL AND ts.expires_at>NOW() ORDER BY ts.started_at DESC LIMIT 1) s ON TRUE
        WHERE (:manager OR d.user_id=:uid) ORDER BY d.created_at DESC LIMIT 200'''),{'manager':manager,'uid':user['id']}).mappings().all()
    return {'items':[dict(r) for r in rows],'manager':manager,'receiver_enabled':enabled(),'receiver_configured':configured(),'client_url':client_url(),'continuous_delivery_guaranteed':False}

@router.get('/people')
def people(user=Depends(require_manager)):
    require_map_permission(user, 'can_read')
    with engine.connect() as c:rows=c.execute(text("SELECT id,full_name FROM users WHERE is_active::text IN ('1','true','t') AND salesperson_id IS NOT NULL ORDER BY full_name LIMIT 500")).mappings().all()
    return {'items':[dict(r) for r in rows]}

@router.post('/devices',status_code=201)
def bind(data:Binding,user=Depends(require_manager)):
    require_map_permission(user, 'can_write')
    with engine.begin() as c:
        c.execute(text('SELECT pg_advisory_xact_lock(819731,:uid)'),{'uid':data.user_id})
        if not c.execute(text("SELECT id FROM users WHERE id=:uid AND is_active::text IN ('1','true','t') AND salesperson_id IS NOT NULL"),{'uid':data.user_id}).scalar():raise HTTPException(422,'حساب فعال متصل به پرسنل لازم است.')
        if c.execute(text('SELECT id FROM traccar_devices WHERE user_id=:uid AND revoked_at IS NULL'),{'uid':data.user_id}).scalar():raise HTTPException(409,'این فرد دستگاه فعال دارد؛ ابتدا همان اتصال را لغو کنید.')
        ident=uuid4();identifier=secrets.token_hex(16)
        c.execute(text('INSERT INTO traccar_devices(id,user_id,identifier,platform,label,created_by) VALUES(:id,:uid,:identifier,:platform,:label,:actor)'),{'id':str(ident),'uid':data.user_id,'identifier':identifier,'platform':data.platform,'label':data.label,'actor':user['id']})
        c.execute(text("INSERT INTO traccar_device_events(device_id,actor_id,kind) VALUES(:id,:actor,'bound')"),{'id':str(ident),'actor':user['id']})
    return {'id':str(ident),'identifier':identifier,'user_id':data.user_id,'platform':data.platform,'gps_started':False}

@router.post('/devices/{ident}/revoke')
def revoke(ident:UUID,user=Depends(require_manager)):
    require_map_permission(user, 'can_write')
    with engine.begin() as c:
        row=c.execute(text('SELECT * FROM traccar_devices WHERE id=:id FOR UPDATE'),{'id':str(ident)}).mappings().first()
        if not row:raise HTTPException(404,'اتصال دستگاه پیدا نشد.')
        c.execute(text('SELECT pg_advisory_xact_lock(819731,:uid)'),{'uid':row['user_id']})
        c.execute(text('UPDATE traccar_devices SET revoked_at=COALESCE(revoked_at,NOW()) WHERE id=:id'),{'id':str(ident)})
        c.execute(text("UPDATE tracking_sessions s SET ended_at=COALESCE(ended_at,NOW()),last_device_status='stopped' FROM traccar_shifts x WHERE x.session_id=s.id AND x.device_id=:id AND s.ended_at IS NULL"),{'id':str(ident)})
        if not row['revoked_at']:c.execute(text("INSERT INTO traccar_device_events(device_id,actor_id,kind) VALUES(:id,:actor,'revoked')"),{'id':str(ident),'actor':user['id']})
    return {'revoked':True,'new_and_buffered_positions_blocked':True}

@router.post('/shift/start',status_code=201)
def start(data:Shift,user=Depends(current_user)):
    staff(user)
    if not enabled() or not client_url():raise HTTPException(503,'نشانی امن Traccar و دریافت‌کننده هنوز فعال نشده‌اند.')
    with engine.begin() as c:
        row=c.execute(text('SELECT * FROM traccar_devices WHERE id=:id AND user_id=:uid AND revoked_at IS NULL FOR UPDATE'),{'id':str(data.device_id),'uid':user['id']}).mappings().first()
        if not row:raise HTTPException(404,'دستگاه فعال متعلق به شما پیدا نشد.')
        version=int(user.get('password_version',0))
        c.execute(text("UPDATE tracking_sessions s SET ended_at=NOW(),last_device_status='permission_revoked' FROM traccar_shifts x WHERE x.session_id=s.id AND x.device_id=:device AND x.auth_version<>:version AND s.ended_at IS NULL"),{'device':str(row['id']),'version':version})
        session=start_session_in_connection(c,Start(device_id='traccar:'+str(row['id']),platform=row['platform'],consent_version=data.consent_version,max_hours=data.max_hours),user)
        c.execute(text('INSERT INTO traccar_shifts(session_id,device_id,auth_version) VALUES(:session,:device,:version) ON CONFLICT DO NOTHING'),{'session':session['session_id'],'device':str(row['id']),'version':version})
        c.execute(text("UPDATE tracking_sessions SET source='traccar' WHERE id=:id"),{'id':session['session_id']})
    return session|{'device_id':'traccar:'+str(row['id']),'source':'traccar','phone_app_must_be_enabled':True}


class ForwardModel(BaseModel):model_config=ConfigDict(extra='ignore',allow_inf_nan=False)
class Device(ForwardModel):
    id:int=Field(gt=0)
    uniqueId:str=Field(min_length=1,max_length=128)
class Position(ForwardModel):
    deviceId:int=Field(gt=0)
    fixTime:datetime
    latitude:float=Field(ge=-90,le=90)
    longitude:float=Field(ge=-180,le=180)
    valid:bool
    accuracy:float|None=Field(default=None,ge=0,le=50000)
    speed:float|None=Field(default=None,ge=0,le=194.3845)
    attributes:dict=Field(default_factory=dict)
    @field_validator('fixTime')
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None or v.utcoffset() is None:raise ValueError('Timezone required')
        return v
class Forward(ForwardModel):
    device:Device
    position:Position


def ingest(c,data,*,now=None):
    now=now or datetime.now(timezone.utc);p=data.position;at=p.fixTime.astimezone(timezone.utc)
    def ignored(reason):return {'accepted':False,'ignored':reason,'position_persisted':False}
    if data.device.id!=p.deviceId:return ignored('device_mismatch')
    if not p.valid:return ignored('invalid_fix')
    if at>now+timedelta(seconds=90) or at<now-timedelta(days=7):return ignored('timestamp_out_of_bounds')
    device=c.execute(text('''SELECT d.*,u.is_active,u.salesperson_id,u.role,u.password_version FROM traccar_devices d JOIN users u ON u.id=d.user_id
        WHERE d.identifier=:identifier AND d.revoked_at IS NULL FOR UPDATE OF d'''),{'identifier':data.device.uniqueId}).mappings().first()
    if not device:return ignored('unmapped_or_inactive_device')
    active=str(device['is_active']).lower() in {'1','true','t'} and bool(device['salesperson_id'])
    allowed=active and role_has_module_permission(device['role'],'map','can_write',connection=c)
    if not allowed:
        c.execute(text("UPDATE tracking_sessions s SET ended_at=NOW(),last_device_status='permission_revoked' FROM traccar_shifts x WHERE x.session_id=s.id AND x.device_id=:device AND s.ended_at IS NULL"),{'device':str(device['id'])})
        return ignored('tracking_permission_revoked' if active else 'unmapped_or_inactive_device')
    # A buffered point can only enter the original, explicitly consented session.
    session=c.execute(text('''SELECT s.*,x.auth_version FROM tracking_sessions s JOIN traccar_shifts x ON x.session_id=s.id
        WHERE x.device_id=:device AND s.user_id=:uid AND s.started_at<=:at
        AND :at<=LEAST(s.expires_at,COALESCE(s.ended_at,s.expires_at)) ORDER BY s.started_at DESC LIMIT 1 FOR UPDATE OF s'''),{'device':str(device['id']),'uid':device['user_id'],'at':at}).mappings().first()
    if not session:return ignored('outside_consented_shift')
    if session['auth_version']!=device['password_version']:
        c.execute(text("UPDATE tracking_sessions SET ended_at=COALESCE(ended_at,NOW()),last_device_status='permission_revoked' WHERE id=:id"),{'id':str(session['id'])})
        return ignored('account_session_changed')
    accuracy=p.accuracy if p.accuracy and p.accuracy>0 else 50000.0
    stable=json.dumps([str(device['id']),at.isoformat(),p.latitude,p.longitude,accuracy],separators=(',',':'))
    event=str(uuid5(NAMESPACE_URL,'kiarad-traccar:'+stable))
    prior=c.execute(text('SELECT 1 FROM tracking_points WHERE session_id=:session AND event_id=:event'),{'session':str(session['id']),'event':event}).scalar()
    if prior:return {'accepted':True,'duplicate':True,'session_id':str(session['id']),'event_id':event}
    count=c.execute(text("SELECT COUNT(*) FROM tracking_points WHERE session_id=:id AND received_at>NOW()-INTERVAL '1 minute'"),{'id':str(session['id'])}).scalar()
    if count>=1200:raise HTTPException(429,'Position rate limit; retry later',headers={'Retry-After':'60'})
    battery=p.attributes.get('batteryLevel');battery=float(battery)/100 if type(battery) in {int,float} and 0<=battery<=100 else None
    mocked=p.attributes.get('mock',p.attributes.get('mocked'));mocked=mocked if isinstance(mocked,bool) else True if str(mocked).lower() in {'1','true'} else False if str(mocked).lower() in {'0','false'} else None
    c.execute(text('''INSERT INTO tracking_points(session_id,event_id,user_id,recorded_at,latitude,longitude,accuracy_m,speed_mps,battery_level,mocked)
    VALUES(:session,:event,:uid,:at,:lat,:lon,:accuracy,:speed,:battery,:mocked) ON CONFLICT DO NOTHING'''),{'session':str(session['id']),'event':event,'uid':device['user_id'],'at':at,'lat':p.latitude,'lon':p.longitude,'accuracy':accuracy,'speed':p.speed*0.514444444444 if p.speed is not None else None,'battery':battery,'mocked':mocked})
    c.execute(text("UPDATE tracking_sessions SET last_upload_at=NOW(),last_device_status=CASE WHEN ended_at IS NULL AND expires_at>NOW() THEN 'tracking' ELSE last_device_status END WHERE id=:id"),{'id':str(session['id'])})
    c.execute(text('UPDATE traccar_devices SET last_received_at=NOW(),last_recorded_at=GREATEST(COALESCE(last_recorded_at,:at),:at) WHERE id=:id'),{'id':str(device['id']),'at':at})
    return {'accepted':True,'duplicate':False,'session_id':str(session['id']),'event_id':event,'offline_backfill_is_not_live':True}

@router.post('/positions')
async def receive(request:Request):
    authorize_forward(request)
    if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':raise HTTPException(415,'JSON required')
    body=bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>BODY_LIMIT:raise HTTPException(413,'Forwarded position too large')
        body.extend(chunk)
    try:data=Forward.model_validate(json.loads(body))
    except (ValueError,ValidationError,UnicodeDecodeError):raise HTTPException(422,'Invalid Traccar position format') from None
    with engine.begin() as c:return ingest(c,data)

@router.on_event('startup')
def startup():
    with engine.begin() as c:ensure(c)
