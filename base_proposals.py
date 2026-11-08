"""Field-submitted base proposals; manager approval creates a local base only."""
import hashlib
import json
import re
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import text
from db import engine
from operations import current_user,require_manager,MANAGER_ROLES

router=APIRouter(prefix='/api/compensation/base-proposals',tags=['base_proposals'])
BASE_TABLES=('pharmacies','cosmetics_shops','kerman_bases_manual')


def normalize(value):
    return re.sub(r'\s+','',value.translate(str.maketrans('يكآ','یکا')).replace('\u200c','')).casefold()


def ensure_proposals(conn,*,temporary=False):
    conn.execute(text(f'''CREATE {'TEMP ' if temporary else ''}TABLE IF NOT EXISTS base_proposals (
        id SERIAL PRIMARY KEY,created_by INTEGER NOT NULL REFERENCES users(id),
        salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),submission_key UUID NOT NULL,payload_hash TEXT NOT NULL,
        name VARCHAR(160) NOT NULL,city VARCHAR(100) NOT NULL,address TEXT NOT NULL,phone VARCHAR(30),
        category VARCHAR(24) NOT NULL,latitude DOUBLE PRECISION NOT NULL,longitude DOUBLE PRECISION NOT NULL,
        accuracy_m DOUBLE PRECISION,note TEXT NOT NULL,status VARCHAR(24) NOT NULL DEFAULT 'pending',
        created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
        reviewed_by INTEGER REFERENCES users(id),reviewed_at TIMESTAMP,review_note TEXT,
        approved_base_id INTEGER REFERENCES kerman_bases_manual(id),
        holoo_status VARCHAR(40) NOT NULL DEFAULT 'not_requested',UNIQUE(created_by,submission_key))'''))


@router.on_event('startup')
def startup():
    with engine.begin() as conn:ensure_proposals(conn)


class ProposalInput(BaseModel):
    submission_key:UUID
    name:str=Field(min_length=2,max_length=160)
    city:str=Field(min_length=2,max_length=100)
    address:str=Field(min_length=5,max_length=2000)
    phone:str=Field(default='',max_length=30)
    category:Literal['pharmacy','cosmetics','clinic','other']
    latitude:float=Field(ge=-90,le=90,allow_inf_nan=False)
    longitude:float=Field(ge=-180,le=180,allow_inf_nan=False)
    accuracy_m:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    note:str=Field(min_length=3,max_length=2000)

    @field_validator('name','city','address','note',mode='before')
    @classmethod
    def strip_text(cls,value):return value.strip() if isinstance(value,str) else value


class ReviewInput(BaseModel):
    decision:Literal['approved','rejected']
    note:str=Field(min_length=3,max_length=2000)

    @field_validator('note',mode='before')
    @classmethod
    def strip_note(cls,value):return value.strip() if isinstance(value,str) else value


def existing_bases(conn):
    return [dict(row,source=table) for table in BASE_TABLES for row in conn.execute(text(f'SELECT id,name,city FROM {table}')).mappings()]


def duplicates(name,city,bases):
    return [row for row in bases if normalize(row.get('name') or '')==normalize(name) and normalize(row.get('city') or '')==normalize(city)]


@router.post('',status_code=201)
def submit(data:ProposalInput,user:dict=Depends(current_user)):
    if user.get('role') not in {'visitor','salesperson'} or not user.get('salesperson_id'):
        raise HTTPException(403,'پیشنهاد میدانی باید از حساب پرسنلِ متصل به پروفایل ثبت شود')
    payload=data.model_dump(exclude={'submission_key'})
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    values={**payload,'actor':user['id'],'sp':user['salesperson_id'],'key':str(data.submission_key),'digest':digest}
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f"proposal:{user['id']}:{data.submission_key}"})
        old=conn.execute(text('SELECT id,payload_hash FROM base_proposals WHERE created_by=:actor AND submission_key=CAST(:key AS uuid)'),values).mappings().first()
        if old:
            if old['payload_hash']!=digest:raise HTTPException(409,'شناسهٔ ارسال قبلاً برای محتوای متفاوت استفاده شده؛ پیشنهاد تازه‌ای شروع کنید')
            return {'id':old['id'],'replayed':True,'holoo_sent':False}
        identity=conn.execute(text('''INSERT INTO base_proposals
            (created_by,salesperson_id,submission_key,payload_hash,name,city,address,phone,category,latitude,longitude,accuracy_m,note)
            VALUES (:actor,:sp,CAST(:key AS uuid),:digest,:name,:city,:address,:phone,:category,:latitude,:longitude,:accuracy_m,:note) RETURNING id'''),values).scalar()
    return {'id':identity,'replayed':False,'holoo_sent':False}


@router.get('')
def history(user:dict=Depends(current_user)):
    manager=user.get('role') in MANAGER_ROLES
    with engine.connect() as conn:
        rows=conn.execute(text('''SELECT p.*,u.full_name AS author_name FROM base_proposals p JOIN users u ON u.id=p.created_by'''+
            ('' if manager else ' WHERE p.created_by=:actor')+' ORDER BY p.created_at DESC,p.id DESC LIMIT 100'),{'actor':user['id']}).mappings().all()
        bases=existing_bases(conn) if manager else []
    result=[]
    for row in rows:
        item=dict(row);item.pop('payload_hash');item.pop('submission_key')
        item['duplicate_candidates']=duplicates(item['name'],item['city'],bases) if item['status']=='pending' else []
        result.append(item)
    return {'items':result,'can_review':manager}


@router.post('/{proposal_id}/review')
def review(proposal_id:int,data:ReviewInput,manager:dict=Depends(require_manager)):
    with engine.begin() as conn:
        row=conn.execute(text('SELECT * FROM base_proposals WHERE id=:id FOR UPDATE'),{'id':proposal_id}).mappings().first()
        if not row:raise HTTPException(404,'پیشنهاد پیدا نشد')
        if row['status']!='pending':raise HTTPException(409,'این پیشنهاد قبلاً بررسی شده است')
        if row['created_by']==manager['id']:raise HTTPException(403,'بررسی پیشنهاد خودتان مجاز نیست')
        base_id=None
        if data.decision=='approved':
            # Serialize proposal approvals; exact-name/city duplicates must be resolved, not silently merged.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('base-proposal-approval',0))"))
            if duplicates(row['name'],row['city'],existing_bases(conn)):
                raise HTTPException(409,'پایگاه هم‌نام در همان شهر موجود است؛ ابتدا تکراری‌بودن را بررسی و پیشنهاد را با علت رد کنید')
            if row['accuracy_m'] is not None and row['accuracy_m']>100:
                raise HTTPException(422,'دقت نقطه بیش از ۱۰۰ متر است؛ پیشنهاد با نقطهٔ دقیق‌تر دوباره ثبت شود')
            base_id=conn.execute(text('''INSERT INTO kerman_bases_manual
                (name,city,address,phone,type,latitude,longitude,visit_radius_m)
                VALUES (:name,:city,:address,:phone,:category,:latitude,:longitude,150) RETURNING id'''),dict(row)).scalar()
        conn.execute(text('''UPDATE base_proposals SET status=:decision,reviewed_by=:actor,
            reviewed_at=NOW() AT TIME ZONE 'Asia/Tehran',review_note=:note,approved_base_id=:base,
            holoo_status=:holoo WHERE id=:id'''),{'id':proposal_id,'decision':data.decision,'actor':manager['id'],
                'note':data.note,'base':base_id,'holoo':'awaiting_connector' if base_id else 'not_requested'})
    return {'id':proposal_id,'status':data.decision,'base_id':base_id,'holoo_sent':False}
