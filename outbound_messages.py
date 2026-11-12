"""Reviewed customer messaging with durable receipts and no blind send retries."""
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from email.utils import parseaddr
from threading import Event,Thread
from typing import Literal
from uuid import UUID,uuid4
import hashlib,json,os,re,smtplib,ssl
import requests
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import text
from db import engine
from operations import current_user
from iran_time import IRAN_TIMEZONE,iran_today

router=APIRouter(prefix='/outbound',tags=['outbound_messages'])
_STOP=Event();_THREAD=None

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class Contact(Strict):
    customer_id:int=Field(gt=0)
    channel:Literal['sms','email']
    destination:str=Field(min_length=5,max_length=254)
    consent_scope:Literal['transactional','marketing']
    evidence:str=Field(min_length=8,max_length=2000)

class Message(Strict):
    submission_key:UUID
    contact_id:UUID
    purpose:Literal['settlement','order','service','marketing']
    subject:str=Field(default='پیام شرکت کیاراد',min_length=3,max_length=160)
    body:str=Field(min_length=3,max_length=3000)
    scheduled_at:datetime|None=None
    @field_validator('subject')
    @classmethod
    def safe_subject(cls,v):
        if '\r' in v or '\n' in v:raise ValueError('Subject cannot contain line breaks')
        return v.strip()
    @field_validator('body')
    @classmethod
    def nonempty(cls,v):
        if len(v.strip())<3:raise ValueError('Message body is empty')
        return v.strip()
    @field_validator('scheduled_at')
    @classmethod
    def aware(cls,v):
        if v and (v.tzinfo is None or v.utcoffset() is None):raise ValueError('Timezone required')
        return v

class Approve(Strict):
    confirm:Literal[True]
    expected_digest:str=Field(pattern='^[0-9a-f]{64}$')


def chief(user):
    if user.get('role')!='ceo' or not user.get('id'):raise HTTPException(403,'تنظیم و تصویب پیام مشتری فقط برای مدیرعامل مجاز است.')


def ensure(c):
    for sql in (
        '''CREATE TABLE IF NOT EXISTS outbound_contacts(id UUID PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customers(id),
        channel TEXT NOT NULL,destination TEXT NOT NULL,consent_scope TEXT NOT NULL,evidence TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE,created_by INTEGER NOT NULL REFERENCES users(id),created_at TIMESTAMPTZ DEFAULT NOW(),
        revoked_at TIMESTAMPTZ,UNIQUE(customer_id,channel,destination,consent_scope))''',
        '''CREATE TABLE IF NOT EXISTS outbound_messages(id UUID PRIMARY KEY,created_by INTEGER NOT NULL REFERENCES users(id),
        submission_key UUID NOT NULL,contact_id UUID NOT NULL REFERENCES outbound_contacts(id),payload JSONB NOT NULL,digest TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'draft',scheduled_at TIMESTAMPTZ NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW(),
        approved_at TIMESTAMPTZ,approval_expires_at TIMESTAMPTZ,attempted_at TIMESTAMPTZ,finished_at TIMESTAMPTZ,
        receipt JSONB,error_code TEXT,UNIQUE(created_by,submission_key))''',
        '''CREATE TABLE IF NOT EXISTS outbound_events(id BIGSERIAL PRIMARY KEY,message_id UUID REFERENCES outbound_messages(id),
        actor_id INTEGER REFERENCES users(id),kind TEXT NOT NULL,detail JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW())''',
        "CREATE INDEX IF NOT EXISTS outbound_due ON outbound_messages(scheduled_at) WHERE state='approved'",
    ):c.execute(text(sql))


def encoded(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,default=str,allow_nan=False)

def event(c,mid,actor,kind,detail=None):c.execute(text('INSERT INTO outbound_events(message_id,actor_id,kind,detail) VALUES(:id,:actor,:kind,CAST(:detail AS JSONB))'),{'id':str(mid),'actor':actor,'kind':kind,'detail':encoded(detail or {})})


def address(channel,value):
    value=value.strip().translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))
    if channel=='sms':
        value=re.sub(r'[\s()-]','',value)
        if value.startswith('+98'):value='0'+value[3:]
        if not re.fullmatch(r'09\d{9}',value):raise HTTPException(422,'شمارهٔ موبایل معتبر ایران وارد کنید.')
    else:
        if '\r' in value or '\n' in value or parseaddr(value)[1]!=value or not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+',value):raise HTTPException(422,'ایمیل معتبر وارد کنید.')
        value=value.lower()
    return value


def connected(channel):
    if channel=='sms':return bool(re.fullmatch(r'[A-Za-z0-9]{12,200}',os.getenv('KAVENEGAR_API_KEY','')) and os.getenv('KAVENEGAR_SENDER'))
    return bool(os.getenv('KIARAD_SMTP_HOST') and os.getenv('KIARAD_SMTP_USER') and os.getenv('KIARAD_SMTP_PASSWORD') and os.getenv('KIARAD_SMTP_FROM'))


def enabled():return os.getenv('KIARAD_OUTBOUND_ENABLED','0').lower() in {'1','true','yes'} and os.getenv('KIARAD_AUTOMATIONS_DISABLED','1').lower() not in {'1','true','yes'} and not any(k.startswith('KIARAD_TEST_') and k.endswith('_DB') for k in os.environ)


@router.get('/status')
def status(user=Depends(current_user)):
    chief(user)
    return {'worker_enabled':enabled(),'channels':{'sms':{'provider':'Kavenegar','connected':connected('sms')},'email':{'provider':'SMTP STARTTLS','connected':connected('email')}},'quiet_hours_tehran':'20:00–08:00','approval_required':True,'provider_acceptance_is_not_delivery':True,'unknown_results_retried':False}


@router.post('/contacts',status_code=201)
def add_contact(data:Contact,user=Depends(current_user)):
    chief(user);dest=address(data.channel,data.destination)
    with engine.begin() as c:
        ensure(c)
        c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'outbound-contact:{data.customer_id}:{data.channel}:{dest}:{data.consent_scope}'})
        if not c.execute(text('SELECT 1 FROM customers WHERE id=:id'),{'id':data.customer_id}).scalar():raise HTTPException(404,'مشتری پیدا نشد.')
        existing=c.execute(text('SELECT id,active FROM outbound_contacts WHERE customer_id=:cid AND channel=:ch AND destination=:dest AND consent_scope=:scope FOR UPDATE'),{'cid':data.customer_id,'ch':data.channel,'dest':dest,'scope':data.consent_scope}).mappings().first()
        if existing:
            if not existing['active']:raise HTTPException(409,'این مسیر تماس لغو شده است؛ بازفعال‌سازی نیازمند بررسی رضایت جدید است.')
            return {'id':str(existing['id']),'reused':True}
        ident=uuid4();c.execute(text('INSERT INTO outbound_contacts(id,customer_id,channel,destination,consent_scope,evidence,created_by) VALUES(:id,:cid,:ch,:dest,:scope,:evidence,:uid)'),{'id':str(ident),'cid':data.customer_id,'ch':data.channel,'dest':dest,'scope':data.consent_scope,'evidence':data.evidence,'uid':user['id']})
    return {'id':str(ident),'reused':False}


@router.get('/contacts')
def contacts(user=Depends(current_user)):
    chief(user)
    with engine.begin() as c:
        ensure(c);items=c.execute(text('SELECT o.*,c.name AS customer_name FROM outbound_contacts o JOIN customers c ON c.id=o.customer_id ORDER BY o.created_at DESC LIMIT 500')).mappings().all()
    return {'items':[dict(i) for i in items]}


@router.post('/contacts/{ident}/revoke')
def revoke(ident:UUID,user=Depends(current_user)):
    chief(user)
    with engine.begin() as c:
        if not c.execute(text('UPDATE outbound_contacts SET active=FALSE,revoked_at=NOW() WHERE id=:id RETURNING id'),{'id':str(ident)}).scalar():raise HTTPException(404,'مسیر تماس پیدا نشد.')
        c.execute(text("UPDATE outbound_messages SET state='cancelled',error_code='contact_revoked',finished_at=NOW() WHERE contact_id=:id AND state IN ('draft','approved')"),{'id':str(ident)})
    return {'active':False,'queued_messages_cancelled':True}


def settlement_evidence(c,customer_id):
    """Never infer zero debt or fresh balances from missing/ambiguous reports."""
    if not c.execute(text("SELECT to_regclass('receivable_snapshots') IS NOT NULL AND to_regclass('receivable_balances') IS NOT NULL")).scalar():
        raise HTTPException(409,'برای پیام تسویه، گزارش معتبر و تازهٔ مطالبات لازم است.')
    row=c.execute(text('SELECT id,snapshot_date FROM receivable_snapshots WHERE snapshot_date<=:today ORDER BY snapshot_date DESC,id DESC LIMIT 1'),{'today':iran_today()}).mappings().first()
    if not row or (iran_today()-row['snapshot_date']).days>7:raise HTTPException(409,'گزارش مطالبات بیش از هفت روز قدمت دارد یا موجود نیست؛ پیام تسویه ساخته نشد.')
    balances=c.execute(text('SELECT balance FROM receivable_balances WHERE snapshot_id=:sid AND customer_id=:cid'),{'sid':row['id'],'cid':customer_id}).scalars().all()
    from decimal import Decimal
    if len(balances)!=1:raise HTTPException(409,'ماندهٔ مشتری در آخرین گزارش نامشخص یا چندردیفی است؛ ابتدا تطبیق مالی انجام شود.')
    balance=Decimal(str(balances[0]))
    if not balance.is_finite() or balance<=0:raise HTTPException(409,'ماندهٔ مثبت قابل اتکا برای پیام تسویه وجود ندارد.')
    return {'snapshot_id':row['id'],'snapshot_date':str(row['snapshot_date']),'balance':str(balance),'unit':'IRR','max_age_days':7}


def check_settlement(c,payload):
    if payload['purpose']=='settlement' and settlement_evidence(c,payload['customer_id'])!=payload.get('receivable_evidence'):
        raise HTTPException(409,'ماندهٔ مطالبات پس از پیش‌نویس تغییر کرده؛ متن و گیرنده باید با گزارش جدید بازبینی شوند.')


@router.post('/messages',status_code=201)
def preview(data:Message,user=Depends(current_user)):
    chief(user);now=datetime.now(timezone.utc);scheduled=data.scheduled_at or now
    if scheduled<now-timedelta(minutes=5) or scheduled>now+timedelta(days=30):raise HTTPException(422,'زمان ارسال باید در سی روز آینده باشد.')
    with engine.begin() as c:
        ensure(c);c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'outbound-preview:{user["id"]}:{data.submission_key}'});contact=c.execute(text('SELECT * FROM outbound_contacts WHERE id=:id FOR UPDATE'),{'id':str(data.contact_id)}).mappings().first()
        if not contact or not contact['active']:raise HTTPException(409,'مسیر تماس فعال و رضایت معتبر لازم است.')
        if data.purpose=='marketing' and contact['consent_scope']!='marketing':raise HTTPException(409,'رضایت تماس تراکنشی، مجوز پیام بازاریابی نیست.')
        payload={**data.model_dump(mode='json',exclude={'submission_key','scheduled_at'}),'channel':contact['channel'],'destination':contact['destination'],'customer_id':contact['customer_id'],'scheduled_at':scheduled.isoformat()}
        if data.purpose=='settlement':payload['receivable_evidence']=settlement_evidence(c,contact['customer_id'])
        sha=hashlib.sha256(encoded(payload).encode()).hexdigest();old=c.execute(text('SELECT id,digest,state,payload FROM outbound_messages WHERE created_by=:uid AND submission_key=:key'),{'uid':user['id'],'key':str(data.submission_key)}).mappings().first()
        if old:
            # A retry without explicit scheduling must preserve the first preview time.
            compare=dict(payload);compare['scheduled_at']=old['payload']['scheduled_at'] if data.scheduled_at is None else payload['scheduled_at']
            if hashlib.sha256(encoded(compare).encode()).hexdigest()!=old['digest']:raise HTTPException(409,'شناسهٔ تکرار برای متن یا گیرندهٔ دیگری استفاده شده است.')
            return {'id':str(old['id']),'digest':old['digest'],'state':old['state'],'reused':True,'preview':old['payload']}
        ident=uuid4();c.execute(text('INSERT INTO outbound_messages(id,created_by,submission_key,contact_id,payload,digest,scheduled_at) VALUES(:id,:uid,:key,:contact,CAST(:payload AS JSONB),:digest,:scheduled)'),{'id':str(ident),'uid':user['id'],'key':str(data.submission_key),'contact':str(data.contact_id),'payload':encoded(payload),'digest':sha,'scheduled':scheduled});event(c,ident,user['id'],'preview_created')
    return {'id':str(ident),'digest':sha,'state':'draft','reused':False,'sent':False,'preview':payload}


@router.get('/messages')
def messages(user=Depends(current_user)):
    chief(user)
    with engine.begin() as c:
        ensure(c);items=c.execute(text('SELECT * FROM outbound_messages WHERE created_by=:uid ORDER BY created_at DESC LIMIT 200'),{'uid':user['id']}).mappings().all()
    return {'items':[dict(i) for i in items]}


@router.post('/messages/{ident}/approve')
def approve(ident:UUID,data:Approve,user=Depends(current_user)):
    chief(user)
    with engine.begin() as c:
        row=c.execute(text('SELECT * FROM outbound_messages WHERE id=:id AND created_by=:uid FOR UPDATE'),{'id':str(ident),'uid':user['id']}).mappings().first()
        if not row:raise HTTPException(404,'پیام متعلق به این حساب پیدا نشد.')
        if row['digest']!=data.expected_digest:raise HTTPException(409,'متن یا گیرنده با نسخهٔ موردنظر تطبیق ندارد.')
        if row['state']=='approved':return {'id':str(ident),'state':'approved','sent':False}
        if row['state']!='draft':raise HTTPException(409,'این وضعیت دوباره تأیید یا ارسال نمی‌شود؛ ابتدا رسید را تطبیق دهید.')
        check_settlement(c,row['payload'])
        if not connected(row['payload']['channel']):raise HTTPException(503,'کانال ارسال تنظیم نشده است؛ پیام ارسال یا تصویب نشد.')
        if not c.execute(text('SELECT active FROM outbound_contacts WHERE id=:id'),{'id':str(row['contact_id'])}).scalar():raise HTTPException(409,'رضایت یا مسیر تماس لغو شده است.')
        c.execute(text("UPDATE outbound_messages SET state='approved',approved_at=NOW(),approval_expires_at=GREATEST(scheduled_at,NOW())+INTERVAL '1 day' WHERE id=:id"),{'id':str(ident)});event(c,ident,user['id'],'approved',{'digest':row['digest']})
    return {'id':str(ident),'state':'approved','sent':False,'worker_enabled':enabled()}


@router.post('/messages/{ident}/cancel')
def cancel(ident:UUID,user=Depends(current_user)):
    chief(user)
    with engine.begin() as c:
        row=c.execute(text('SELECT state FROM outbound_messages WHERE id=:id AND created_by=:uid FOR UPDATE'),{'id':str(ident),'uid':user['id']}).mappings().first()
        if not row:raise HTTPException(404,'پیام پیدا نشد.')
        if row['state'] not in {'draft','approved','cancelled'}:raise HTTPException(409,'تلاش ارسال شروع شده است؛ برای جلوگیری از تکرار، نتیجه را تطبیق دهید.')
        c.execute(text("UPDATE outbound_messages SET state='cancelled',finished_at=NOW() WHERE id=:id"),{'id':str(ident)});event(c,ident,user['id'],'cancelled')
    return {'state':'cancelled'}


class ProviderRejected(Exception):pass


def deliver(payload,ident):
    if payload['channel']=='sms':
        key=os.getenv('KAVENEGAR_API_KEY','')
        if not connected('sms'):raise ProviderRejected('provider_not_configured')
        r=requests.post('https://api.kavenegar.com/v1/'+key+'/sms/send.json',data={'receptor':payload['destination'],'sender':os.environ['KAVENEGAR_SENDER'],'message':payload['body'],'localid':str(ident)},timeout=(10,25),allow_redirects=False)
        body=r.json()
        if body.get('return',{}).get('status')!=200:raise ProviderRejected('provider_rejected')
        entries=body.get('entries') or []
        if len(entries)!=1 or not entries[0].get('messageid'):raise RuntimeError('missing_provider_receipt')
        return {'provider':'kavenegar','provider_message_id':str(entries[0]['messageid']),'provider_status':entries[0].get('status'),'accepted':entries[0].get('status') not in {6,11,13,14,100},'delivered':entries[0].get('status')==10}
    if not connected('email'):raise ProviderRejected('provider_not_configured')
    sender=address('email',os.environ['KIARAD_SMTP_FROM']);msg=EmailMessage();msg['From']=sender;msg['To']=payload['destination'];msg['Subject']=payload['subject'];msg['Message-ID']='<'+str(ident)+'@'+sender.split('@')[1]+'>';msg.set_content(payload['body'])
    with smtplib.SMTP(os.environ['KIARAD_SMTP_HOST'],int(os.getenv('KIARAD_SMTP_PORT','587')),timeout=25) as smtp:
        smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo();smtp.login(os.environ['KIARAD_SMTP_USER'],os.environ['KIARAD_SMTP_PASSWORD']);refused=smtp.send_message(msg)
        if refused:raise ProviderRejected('recipient_rejected')
    return {'provider':'smtp','provider_message_id':msg['Message-ID'],'accepted':True,'delivered':False}


def dispatch_one(*,now=None):
    now=now or datetime.now(timezone.utc)
    if not enabled():return {'state':'disabled'}
    if not 8<=now.astimezone(IRAN_TIMEZONE).hour<20:return {'state':'quiet_hours'}
    try:limit=max(1,min(1000,int(os.getenv('KIARAD_OUTBOUND_DAILY_LIMIT','100'))))
    except ValueError:limit=100
    with engine.begin() as c:
        # Serialize budget reservation, never the external request.
        c.execute(text('SELECT pg_advisory_xact_lock(819733,1)'))
        c.execute(text("UPDATE outbound_messages SET state='review_required',error_code='interrupted_send' WHERE state='sending' AND attempted_at<NOW()-INTERVAL '10 minutes'"))
        start=datetime.combine(now.astimezone(IRAN_TIMEZONE).date(),datetime.min.time(),IRAN_TIMEZONE)
        count=c.execute(text('SELECT COUNT(*) FROM outbound_messages WHERE attempted_at>=:start'),{'start':start}).scalar()
        if count>=limit:return {'state':'daily_limit'}
        row=c.execute(text("SELECT * FROM outbound_messages WHERE state='approved' AND scheduled_at<=:now ORDER BY scheduled_at FOR UPDATE SKIP LOCKED LIMIT 1"),{'now':now}).mappings().first()
        if not row:return {'state':'idle'}
        contact=c.execute(text('SELECT * FROM outbound_contacts WHERE id=:id FOR UPDATE'),{'id':str(row['contact_id'])}).mappings().first()
        owner=c.execute(text("SELECT role FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),{'id':row['created_by']}).scalar()
        invalid=not contact or not contact['active'] or owner!='ceo' or contact['destination']!=row['payload']['destination'] or (row['payload']['purpose']=='marketing' and contact['consent_scope']!='marketing')
        if invalid or row['approval_expires_at']<now:
            c.execute(text("UPDATE outbound_messages SET state='cancelled',error_code='authorization_expired',finished_at=NOW() WHERE id=:id"),{'id':str(row['id'])});return {'state':'cancelled'}
        try:check_settlement(c,row['payload'])
        except HTTPException:
            c.execute(text("UPDATE outbound_messages SET state='cancelled',error_code='receivable_changed_or_unverified',finished_at=NOW() WHERE id=:id"),{'id':str(row['id'])});event(c,row['id'],row['created_by'],'settlement_cancelled');return {'state':'cancelled'}
        recent=c.execute(text("SELECT COUNT(*) FROM outbound_messages WHERE payload->>'destination'=:dest AND attempted_at>NOW()-INTERVAL '24 hours'"),{'dest':contact['destination']}).scalar()
        if recent>=2:
            c.execute(text("UPDATE outbound_messages SET scheduled_at=NOW()+INTERVAL '1 hour' WHERE id=:id"),{'id':str(row['id'])});return {'state':'recipient_cooldown'}
        if not connected(contact['channel']):return {'state':'not_connected'}
        c.execute(text("UPDATE outbound_messages SET state='sending',attempted_at=NOW() WHERE id=:id"),{'id':str(row['id'])});event(c,row['id'],row['created_by'],'send_started')
    try:
        receipt=deliver(row['payload'],row['id']);state='delivered' if receipt.get('delivered') else 'accepted' if receipt.get('accepted') else 'failed';error=None if receipt.get('accepted') else 'provider_rejected'
    except ProviderRejected as exc:receipt=None;state='failed';error=str(exc)
    except Exception:receipt=None;state='review_required';error='provider_outcome_unknown'
    with engine.begin() as c:
        c.execute(text('UPDATE outbound_messages SET state=:state,receipt=CAST(:receipt AS JSONB),error_code=:error,finished_at=NOW() WHERE id=:id'),{'id':str(row['id']),'state':state,'receipt':encoded(receipt),'error':error});event(c,row['id'],row['created_by'],state,receipt or {'error_code':error})
    return {'id':str(row['id']),'state':state,'receipt':receipt,'external_delivery_confirmed':bool(receipt and receipt.get('delivered'))}


def provider_status(message_id):
    if not connected('sms') or not re.fullmatch(r'[0-9]{1,30}',str(message_id)):raise HTTPException(422,'شناسهٔ عددی معتبر سرویس و اتصال پیامک لازم است.')
    try:
        r=requests.get('https://api.kavenegar.com/v1/'+os.environ['KAVENEGAR_API_KEY']+'/sms/status.json',params={'messageid':str(message_id)},timeout=(10,25),allow_redirects=False)
        b=r.json();entries=b.get('entries') or []
        if b.get('return',{}).get('status')!=200 or len(entries)!=1 or str(entries[0].get('messageid'))!=str(message_id):raise ValueError('Invalid provider status')
        code=int(entries[0]['status'])
        return {'provider':'kavenegar','provider_message_id':str(message_id),'provider_status':code,'accepted':code not in {6,11,13,14,100},'delivered':code==10,'checked_at':datetime.now(timezone.utc).isoformat()}
    except Exception:raise HTTPException(503,'وضعیت سرویس قابل تأیید نبود؛ پیام دوباره ارسال نشد.') from None

@router.post('/messages/{ident}/refresh-receipt')
def refresh_receipt(ident:UUID,user=Depends(current_user)):
    chief(user)
    with engine.connect() as c:row=c.execute(text('SELECT * FROM outbound_messages WHERE id=:id AND created_by=:uid'),{'id':str(ident),'uid':user['id']}).mappings().first()
    if not row:raise HTTPException(404,'پیام پیدا نشد.')
    receipt=row['receipt'] or {}
    if row['payload']['channel']!='sms' or not receipt.get('provider_message_id'):raise HTTPException(409,'این پیام رسید قابل استعلام پیامکی ندارد؛ پذیرش SMTP اثبات تحویل نیست.')
    checked=provider_status(receipt['provider_message_id']);state='delivered' if checked['delivered'] else 'accepted' if checked['accepted'] else 'failed'
    with engine.begin() as c:
        current=c.execute(text('SELECT state,receipt FROM outbound_messages WHERE id=:id FOR UPDATE'),{'id':str(ident)}).mappings().first()
        if current['state'] not in {'accepted','delivered','failed'} or (current['receipt'] or {}).get('provider_message_id')!=receipt['provider_message_id']:raise HTTPException(409,'وضعیت پیام تغییر کرده؛ رسید را دوباره بخوانید.')
        c.execute(text('UPDATE outbound_messages SET state=:state,receipt=CAST(:receipt AS JSONB) WHERE id=:id'),{'id':str(ident),'state':state,'receipt':encoded(checked)});event(c,ident,user['id'],'receipt_refreshed',checked)
    return {'state':state,'receipt':checked,'message_resent':False}

class Reconcile(Strict):
    reviewed:Literal[True]
    outcome:Literal['not_sent','accepted','delivered']
    provider_message_id:str|None=Field(default=None,max_length=200)
    evidence_note:str=Field(min_length=20,max_length=2000)

@router.post('/messages/{ident}/reconcile')
def reconcile(ident:UUID,data:Reconcile,user=Depends(current_user)):
    chief(user)
    with engine.connect() as c:row=c.execute(text('SELECT * FROM outbound_messages WHERE id=:id AND created_by=:uid'),{'id':str(ident),'uid':user['id']}).mappings().first()
    if not row:raise HTTPException(404,'پیام پیدا نشد.')
    if row['state']!='review_required':raise HTTPException(409,'این پیام در انتظار تطبیق نتیجه نیست.')
    if data.outcome=='not_sent':state='reconciled_not_sent';receipt={'manual_review':True,'outcome':'not_sent','accepted':False,'delivered':False}
    elif row['payload']['channel']=='sms':
        if not data.provider_message_id:raise HTTPException(422,'شناسهٔ سرویس را پس از تطبیق گیرنده و متن وارد کنید.')
        receipt=provider_status(data.provider_message_id);state='delivered' if receipt['delivered'] else 'accepted' if receipt['accepted'] else 'failed';receipt['association_manually_reviewed']=True
    else:state='manually_reconciled';receipt={'manual_review':True,'outcome':data.outcome,'provider_message_id':data.provider_message_id,'accepted':None,'delivered':False,'delivery_confirmation_source':'manual_evidence_only'}
    with engine.begin() as c:
        current=c.execute(text('SELECT state FROM outbound_messages WHERE id=:id FOR UPDATE'),{'id':str(ident)}).scalar()
        if current!='review_required':raise HTTPException(409,'نتیجه قبلاً تطبیق داده شده است.')
        c.execute(text('UPDATE outbound_messages SET state=:state,receipt=CAST(:receipt AS JSONB),error_code=NULL WHERE id=:id'),{'id':str(ident),'state':state,'receipt':encoded(receipt)});event(c,ident,user['id'],'outcome_reconciled',{'outcome':data.outcome,'evidence_note':data.evidence_note,'receipt':receipt})
    return {'state':state,'receipt':receipt,'message_resent':False}


def loop():
    while not _STOP.wait(10):
        try:dispatch_one()
        except Exception:pass  # No provider error or URL (which can contain a key) is logged.

@router.on_event('startup')
def startup():
    global _THREAD
    with engine.begin() as c:ensure(c)
    if enabled() and (_THREAD is None or not _THREAD.is_alive()):_STOP.clear();_THREAD=Thread(target=loop,daemon=True,name='kiarad-outbound');_THREAD.start()

@router.on_event('shutdown')
def shutdown():_STOP.set()
