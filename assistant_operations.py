"""Actor-bound, expiring proposals. Business writes require a separate confirmation."""
from datetime import datetime, timezone
import json
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from sqlalchemy import text
from operations import current_user, MANAGER_ROLES, TaskCreate, DailyReportCreate, role_has_module_permission
from db import engine

router=APIRouter(prefix='/actions',tags=['assistant_actions'])


class OperationArgs(BaseModel):
    model_config=ConfigDict(extra='forbid')
    operation: str = Field(max_length=80)
    payload: dict

    @field_validator('operation')
    @classmethod
    def known_operation(cls,value):
        from assistant_commands import COMMANDS
        if value not in COMMANDS and value not in {'create_task','create_daily_report','save_contract','create_content_draft'}:
            raise ValueError('عملیات ناشناخته است.')
        return value


def ensure(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS assistant_operation_proposals(
        id UUID PRIMARY KEY,actor_id INT NOT NULL,operation TEXT NOT NULL,payload JSONB NOT NULL,
        baseline JSONB,status TEXT NOT NULL DEFAULT 'preview',receipt JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '20 minutes')'''))


@router.on_event('startup')
def startup():
    with engine.begin() as conn:
        ensure(conn)


def authorize(operation,user):
    from assistant_commands import COMMANDS,authorize as command_authorize
    if operation in COMMANDS:
        command_authorize(operation,user)
        return
    module={'create_task':'tasks','create_daily_report':'daily-reports','save_contract':'compensation','create_content_draft':'social'}[operation]
    if user.get('role')!='ceo' and not (role_has_module_permission(user.get('role',''),module,'can_write') or
            (operation=='save_contract' and role_has_module_permission(user.get('role',''),'payroll','can_write'))):
        raise HTTPException(403,'مجوز نوشتن در بخش مربوط فعال نیست.')
    if operation=='create_task' and user.get('role') not in MANAGER_ROLES:
        raise HTTPException(403,'تخصیص کار فقط برای مدیر است.')
    if operation=='save_contract':
        from compensation import COMPENSATION_ADMIN_ROLES
        if user.get('role') not in COMPENSATION_ADMIN_ROLES:
            raise HTTPException(403,'تغییر قرارداد در دسترسی شما نیست.')
    if not user.get('id'):raise HTTPException(401,'ورود لازم است.')


def prepare(args,user):
    a=OperationArgs.model_validate(args);authorize(a.operation,user)
    if len(json.dumps(a.payload,ensure_ascii=False,allow_nan=False))>30000:
        raise HTTPException(422,'شرح عملیات بیش از حد طولانی است.')
    baseline={}
    from assistant_commands import COMMANDS
    if a.operation in COMMANDS:
        from assistant_commands import prepare as prepare_command
        payload,baseline=prepare_command(a.operation,a.payload,user)
    elif a.operation=='create_task':
        if set(a.payload)-set(TaskCreate.model_fields):raise HTTPException(422,'فیلد ناشناختهٔ وظیفه.')
        payload=TaskCreate.model_validate(a.payload).model_dump(mode='json')
        if len(payload.get('description') or '')>10000:raise HTTPException(422,'شرح کار طولانی است.')
        with engine.connect() as conn:
            name=conn.execute(text("SELECT COALESCE(full_name,username) FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),{'id':payload['assigned_to']}).scalar()
        if not name:raise HTTPException(422,'مسئول فعال پیدا نشد.')
        baseline['display']={'assigned_to':name}
    elif a.operation=='create_daily_report':
        if set(a.payload)-set(DailyReportCreate.model_fields):raise HTTPException(422,'فیلد ناشناختهٔ گزارش.')
        payload=DailyReportCreate.model_validate(a.payload).model_dump(mode='json')
        from iran_time import iran_today
        if not user.get('salesperson_id'):raise HTTPException(403,'گزارش کار به پروفایل پرسنلی نیاز دارد.')
        if DailyReportCreate.model_validate(a.payload).report_date>iran_today():raise HTTPException(422,'گزارش آینده مجاز نیست.')
    elif a.operation=='create_content_draft':
        from integrations import ContentDraftInput, CONTENT_CHANNELS
        if set(a.payload)-set(ContentDraftInput.model_fields):raise HTTPException(422,'فیلد ناشناختهٔ محتوا.')
        content=ContentDraftInput.model_validate(a.payload)
        if content.channel not in CONTENT_CHANNELS or not content.title.strip() or not content.body.strip():
            raise HTTPException(422,'کانال، عنوان و متن معتبر لازم است.')
        if content.scheduled_at.tzinfo is None or content.scheduled_at.utcoffset() is None:
            raise HTTPException(422,'زمان محتوا باید منطقهٔ زمانی مشخص داشته باشد.')
        payload=content.model_dump(mode='json')
    else:
        if set(a.payload)-{'salesperson_id','month','description'}:raise HTTPException(422,'فیلد ناشناختهٔ قرارداد.')
        from compensation import get_contract
        from payroll_assistant import draft_rules
        from payroll_service import period
        sid=a.payload.get('salesperson_id')
        if type(sid) is not int or sid<=0:raise HTTPException(422,'پرسنل مشخص لازم است.')
        month=period(a.payload.get('month'))[0]
        current=get_contract(sid,month,user)
        with engine.connect() as conn:
            name=conn.execute(text('SELECT name FROM salespersons WHERE id=:id'),{'id':sid}).scalar()
        if not name:raise HTTPException(422,'پرسنل پیدا نشد.')
        draft=draft_rules({'description':a.payload.get('description'),'current_rules':current})
        if draft.get('questions'):
            return {'status':'needs_information','questions':draft['questions'],'saved':False}
        payload={'salesperson_id':sid,'effective_month':month,**draft['rules'],'rules_approved':True,
                 'expected_rule_version':current.get('rule_version'),
                 'unresolved_questions':[],'decision_note':a.payload['description'][:2000]}
        baseline={'rule_version':current.get('rule_version'),'display':{'salesperson_id':name}}
    ident=str(uuid4())
    with engine.begin() as conn:
        import hashlib
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False)
        digest=hashlib.sha256(encoded.encode()).hexdigest()
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'assistant-proposal:{user["id"]}:{digest}'})
        existing=conn.execute(text('''SELECT id FROM assistant_operation_proposals WHERE actor_id=:actor
            AND operation=:operation AND payload=CAST(:payload AS JSONB) AND expires_at>NOW()
            ORDER BY created_at DESC LIMIT 1'''),{'actor':user['id'],'operation':a.operation,'payload':encoded}).scalar()
        if existing:
            return {'status':'operation_preview','proposal_id':str(existing),'saved':False,
                    'review_href':'/assistant-actions?id='+str(existing),'message':'این پیشنهاد قبلاً آماده شده؛ وضعیت و جزئیات همان پیشنهاد را بررسی کنید.'}
        conn.execute(text('''INSERT INTO assistant_operation_proposals(id,actor_id,operation,payload,baseline)
            VALUES(:id,:actor,:operation,CAST(:payload AS JSONB),CAST(:baseline AS JSONB))'''),
            {'id':ident,'actor':user['id'],'operation':a.operation,'payload':json.dumps(payload,ensure_ascii=False),
             'baseline':json.dumps(baseline)})
    return {'status':'operation_preview','proposal_id':ident,'saved':False,
            'review_href':'/assistant-actions?id='+ident,'message':'پیشنهاد آماده است؛ فقط پس از بررسی جزئیات و تأیید جداگانه اعمال می‌شود.'}


def proposal(conn,ident,user,lock=False):
    row=conn.execute(text('SELECT * FROM assistant_operation_proposals WHERE id=:id AND actor_id=:actor'+(' FOR UPDATE' if lock else '')),
                     {'id':str(ident),'actor':user['id']}).mappings().first()
    if row is None:raise HTTPException(404,'پیشنهاد پیدا نشد یا متعلق به این حساب نیست.')
    authorize(row['operation'],user)
    return dict(row)


@router.get('')
def operation_catalog(user=Depends(current_user)):
    from assistant_commands import catalog
    return catalog(user)


@router.get('/{ident}')
def read_proposal(ident: str,user=Depends(current_user)):
    from uuid import UUID
    try:UUID(ident)
    except ValueError:raise HTTPException(422,'شناسهٔ پیشنهاد معتبر نیست.') from None
    with engine.begin() as conn:
        row=proposal(conn,ident,user)
    return {**{k:row[k] for k in ('id','operation','payload','status','receipt','expires_at')},
            'display':(row.get('baseline') or {}).get('display',{}),
            'before':(row.get('baseline') or {}).get('before'),
            'entry_preview':(row.get('baseline') or {}).get('entry_preview')}


class Confirmation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: Literal[True]


@router.post('/{ident}/confirm')
def confirm_proposal(ident:str,data:Confirmation,user=Depends(current_user)):
    # Reuse ID validation, and keep the actor/role check on both calls.
    read_proposal(ident,user)
    with engine.begin() as conn:
        row=proposal(conn,ident,user,True)
        if row['status']=='applied':return {'status':'applied','receipt':row['receipt'],'reused':True}
        if row['status']!='preview':raise HTTPException(409,'این پیشنهاد قبلاً بررسی شده؛ پیش از تلاش مجدد نتیجه را بررسی کنید.')
        if row['expires_at']<=datetime.now(timezone.utc):raise HTTPException(409,'مهلت پیشنهاد گذشته؛ پیشنهاد تازه بسازید.')
        conn.execute(text("UPDATE assistant_operation_proposals SET status='executing' WHERE id=:id"),{'id':ident})
    try:
        payload=dict(row['payload'])
        from assistant_commands import COMMANDS
        if row['operation'] in COMMANDS:
            from assistant_commands import execute as execute_command
            receipt=execute_command(row['operation'],payload,row.get('baseline') or {},user)
        elif row['operation']=='create_task':
            from operations import create_task
            receipt=create_task(TaskCreate.model_validate(payload),user)
        elif row['operation']=='create_daily_report':
            from operations import create_daily_report
            receipt=create_daily_report(DailyReportCreate.model_validate(payload),user)
        elif row['operation']=='create_content_draft':
            from integrations import create_content_draft, ContentDraftInput
            receipt=create_content_draft(ContentDraftInput.model_validate(payload),user)
        else:
            from compensation import get_contract,save_contract
            sid=payload.pop('salesperson_id')
            current=get_contract(sid,payload['effective_month'],user)
            if current.get('rule_version')!=(row.get('baseline') or {}).get('rule_version'):
                raise HTTPException(409,'قرارداد پس از پیش‌نمایش تغییر کرده؛ پیشنهاد تازه بسازید.')
            receipt=save_contract(sid,payload,user)
        serialized=json.dumps(receipt,ensure_ascii=False,default=str)
        with engine.begin() as conn:
            conn.execute(text("UPDATE assistant_operation_proposals SET status='applied',receipt=CAST(:receipt AS JSONB) WHERE id=:id"),{'id':ident,'receipt':serialized})
        return {'status':'applied','receipt':receipt}
    except Exception:
        with engine.begin() as conn:
            conn.execute(text("UPDATE assistant_operation_proposals SET status='review_required' WHERE id=:id"),{'id':ident})
        raise
