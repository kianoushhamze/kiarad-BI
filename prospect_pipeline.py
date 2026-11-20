"""Versioned public business leads: discover -> evidence -> review -> route base."""
from datetime import datetime,timezone
from uuid import UUID,uuid4
from typing import Literal
import hashlib,json,unicodedata
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import text
from db import engine
from operations import current_user
from public_prospect_discovery import discover
from agent_center import ceo,encode

router=APIRouter(prefix='/prospects',tags=['prospect_pipeline'])
SOURCES=('pharmacies','cosmetics_shops','kerman_bases_manual')

def normalized(v):return ' '.join(unicodedata.normalize('NFKC',str(v or '')).translate(str.maketrans({'ي':'ی','ك':'ک','\u200c':' '})).split()).casefold()

def ensure(c):
    for statement in (
        '''CREATE TABLE IF NOT EXISTS prospect_runs(id UUID PRIMARY KEY,created_by INTEGER NOT NULL REFERENCES users(id),
        submission_key UUID NOT NULL,state TEXT NOT NULL DEFAULT 'started',started_at TIMESTAMPTZ DEFAULT NOW(),finished_at TIMESTAMPTZ,
        summary JSONB,error_code TEXT,UNIQUE(created_by,submission_key))''',
        '''CREATE TABLE IF NOT EXISTS prospect_candidates(id UUID PRIMARY KEY,source TEXT NOT NULL,source_key TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1,payload JSONB NOT NULL,payload_hash TEXT NOT NULL,identity_hint TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'unverified',first_seen_at TIMESTAMPTZ DEFAULT NOW(),last_seen_at TIMESTAMPTZ DEFAULT NOW(),
        reviewed_by INTEGER REFERENCES users(id),reviewed_at TIMESTAMPTZ,review_note TEXT,base_source TEXT,base_id INTEGER,
        UNIQUE(source,source_key))''',
        '''CREATE TABLE IF NOT EXISTS prospect_observations(id BIGSERIAL PRIMARY KEY,candidate_id UUID NOT NULL REFERENCES prospect_candidates(id),
        run_id UUID NOT NULL REFERENCES prospect_runs(id),revision INTEGER NOT NULL,payload JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW(),UNIQUE(candidate_id,run_id))''',
        '''CREATE TABLE IF NOT EXISTS prospect_reviews(id BIGSERIAL PRIMARY KEY,candidate_id UUID NOT NULL REFERENCES prospect_candidates(id),
        revision INTEGER NOT NULL,actor_id INTEGER NOT NULL REFERENCES users(id),decision TEXT NOT NULL,note TEXT NOT NULL,
        payload JSONB NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW())''',
        'CREATE INDEX IF NOT EXISTS prospect_review_queue ON prospect_candidates(review_status,last_seen_at DESC)',
        'CREATE INDEX IF NOT EXISTS prospect_identity_hint ON prospect_candidates(identity_hint)',
    ):c.execute(text(statement))

class Strict(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Discovery(Strict):
    submission_key:UUID
    city:str|None=Field(default=None,max_length=100)
    max_items:int=Field(default=2000,ge=1,le=5000)
class BaseFields(Strict):
    name:str=Field(min_length=2,max_length=160)
    city:str=Field(min_length=2,max_length=100)
    address:str=Field(min_length=5,max_length=2000)
    phone:str=Field(default='',max_length=40)
    category:Literal['pharmacy','cosmetics','clinic','other']
    latitude:float=Field(ge=-90,le=90)
    longitude:float=Field(ge=-180,le=180)
class Review(Strict):
    expected_revision:int=Field(ge=1)
    decision:Literal['approve','reject']
    note:str=Field(min_length=8,max_length=2000)
    verified_fields:BaseFields|None=None
    coordinates_confirmed:bool=False
    existing_base_source:Literal['pharmacies','cosmetics_shops','kerman_bases_manual']|None=None
    existing_base_id:int|None=Field(default=None,gt=0)
    apply_base_update:bool=False
    @model_validator(mode='after')
    def coherent(self):
        if bool(self.existing_base_source)!=bool(self.existing_base_id):raise ValueError('Existing base source and ID must be provided together')
        if self.decision=='approve' and (not self.verified_fields or not self.coordinates_confirmed):raise ValueError('Reviewed fields and explicit coordinate confirmation are required')
        return self


def ingest(c,run_id,items,city,max_items):
    added=changed=seen=0;limited=False;identities=set()
    for item in items:
        if city and normalized(item.get('city'))!=normalized(city):continue
        source_key=str(item.get('source_id',''))
        if source_key in identities:continue
        identities.add(source_key)
        if seen>=max_items:limited=True;break
        if not source_key or not source_key.split('/')[0] in {'node','way','relation'}:continue
        payload={k:item.get(k) for k in ('source_id','source_url','name','category','city','street','address','phone','latitude','longitude')}
        for key in ['name','city','street','address','phone']:
            if payload[key] is not None:payload[key]=str(payload[key])[:2000]
        sha=hashlib.sha256(encode(payload).encode()).hexdigest();hint=normalized(payload['name'])+'|'+normalized(payload['city'])
        c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'prospect:osm:'+source_key})
        row=c.execute(text("SELECT * FROM prospect_candidates WHERE source='osm' AND source_key=:key FOR UPDATE"),{'key':source_key}).mappings().first()
        if not row:
            ident=uuid4();revision=1;added+=1;c.execute(text("INSERT INTO prospect_candidates(id,source,source_key,payload,payload_hash,identity_hint) VALUES(:id,'osm',:key,CAST(:payload AS JSONB),:hash,:hint)"),{'id':str(ident),'key':source_key,'payload':encode(payload),'hash':sha,'hint':hint})
        else:
            ident=row['id'];revision=row['revision']+(row['payload_hash']!=sha)
            if row['payload_hash']!=sha:
                changed+=1;c.execute(text("UPDATE prospect_candidates SET revision=:revision,payload=CAST(:payload AS JSONB),payload_hash=:hash,identity_hint=:hint,review_status=CASE WHEN review_status='approved' THEN 'changed_after_review' ELSE review_status END,last_seen_at=NOW() WHERE id=:id"),{'id':str(ident),'revision':revision,'payload':encode(payload),'hash':sha,'hint':hint})
            else:c.execute(text('UPDATE prospect_candidates SET last_seen_at=NOW() WHERE id=:id'),{'id':str(ident)})
        c.execute(text('INSERT INTO prospect_observations(candidate_id,run_id,revision,payload) VALUES(:id,:run,:revision,CAST(:payload AS JSONB)) ON CONFLICT DO NOTHING'),{'id':str(ident),'run':str(run_id),'revision':revision,'payload':encode(payload)});seen+=1
    return {'observed':seen,'new_candidates':added,'changed_candidates':changed,'limited':limited,'customers_created':0,'existing_bases_changed':0,'coverage':'mapped public pharmacies/cosmetics in Kerman province; not a complete official registry'}


@router.post('/discover')
def run_discovery(data:Discovery,user=Depends(current_user)):
    ceo(user)
    with engine.begin() as c:
        ensure(c);c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'discovery:{user["id"]}:{data.submission_key}'})
        old=c.execute(text('SELECT id,state,summary FROM prospect_runs WHERE created_by=:uid AND submission_key=:key'),{'uid':user['id'],'key':str(data.submission_key)}).mappings().first()
        if old:
            if old['state']=='completed':return {'run_id':str(old['id']),'state':'completed','summary':old['summary'],'replayed':True}
            raise HTTPException(409,'اجرای قبلی هنوز کامل نشده؛ برای جلوگیری از هم‌پوشانی وضعیت آن را بررسی کنید.')
        c.execute(text('SELECT pg_advisory_xact_lock(819734,1)'))
        daily=c.execute(text("SELECT COUNT(*) FROM prospect_runs WHERE started_at>NOW()-INTERVAL '24 hours'")).scalar()
        if daily>=4:raise HTTPException(429,'سقف چهار دریافت روزانه از منبع عمومی تکمیل شده است.')
        ident=uuid4();c.execute(text('INSERT INTO prospect_runs(id,created_by,submission_key) VALUES(:id,:uid,:key)'),{'id':str(ident),'uid':user['id'],'key':str(data.submission_key)})
    try:
        report=discover()
        with engine.begin() as c:
            summary=ingest(c,ident,report['items'],data.city,data.max_items)
            summary.update(source=report['source'],source_url=report['source_url'],license_url=report['license_url'],observed_at=report['observed_at'])
            c.execute(text("UPDATE prospect_runs SET state='completed',summary=CAST(:summary AS JSONB),finished_at=NOW() WHERE id=:id"),{'id':str(ident),'summary':encode(summary)})
        return {'run_id':str(ident),'state':'completed','summary':summary,'replayed':False}
    except Exception:
        with engine.begin() as c:c.execute(text("UPDATE prospect_runs SET state='failed',error_code='source_unavailable_or_invalid',finished_at=NOW() WHERE id=:id"),{'id':str(ident)})
        raise HTTPException(503,'منبع عمومی قابل دریافت یا معتبر نبود؛ نتیجهٔ خالی به‌عنوان لیدیابی موفق ثبت نشد.') from None


@router.get('')
def candidates(state:str|None=None,user=Depends(current_user)):
    ceo(user)
    with engine.begin() as c:
        ensure(c);rows=c.execute(text('''SELECT p.*,(SELECT COUNT(*) FROM prospect_candidates d WHERE d.identity_hint=p.identity_hint AND d.id<>p.id) AS possible_duplicate_count
        FROM prospect_candidates p WHERE (:state IS NULL OR review_status=:state) ORDER BY last_seen_at DESC LIMIT 500'''),{'state':state}).mappings().all()
    return {'items':[dict(r) for r in rows],'limited_to':500}


@router.get('/runs')
def runs(user=Depends(current_user)):
    ceo(user)
    with engine.begin() as c:ensure(c);rows=c.execute(text('SELECT * FROM prospect_runs WHERE created_by=:uid ORDER BY started_at DESC LIMIT 100'),{'uid':user['id']}).mappings().all()
    return {'items':[dict(r) for r in rows]}


@router.post('/{ident}/review')
def review(ident:UUID,data:Review,user=Depends(current_user)):
    ceo(user)
    with engine.begin() as c:
        row=c.execute(text('SELECT * FROM prospect_candidates WHERE id=:id FOR UPDATE'),{'id':str(ident)}).mappings().first()
        if not row:raise HTTPException(404,'لید پیدا نشد.')
        if row['revision']!=data.expected_revision:raise HTTPException(409,'منبع پس از بازبینی تغییر کرده است؛ نسخهٔ جدید را بخوانید.')
        if data.decision=='reject':
            c.execute(text("UPDATE prospect_candidates SET review_status='rejected',reviewed_by=:uid,reviewed_at=NOW(),review_note=:note WHERE id=:id"),{'id':str(ident),'uid':user['id'],'note':data.note});result={'state':'rejected'}
        else:
            fields=data.verified_fields.model_dump();target_source=row['base_source'];target_id=row['base_id']
            if row['review_status']=='approved':return {'state':'approved','base_source':target_source,'base_id':target_id,'replayed':True}
            if data.existing_base_source:
                found=c.execute(text('SELECT id FROM '+data.existing_base_source+' WHERE id=:id'),{'id':data.existing_base_id}).scalar()
                if not found:raise HTTPException(404,'پایگاه انتخابی پیدا نشد.')
                target_source=data.existing_base_source;target_id=data.existing_base_id
            elif not target_id:
                from base_proposals import duplicates,existing_bases
                matches=duplicates(fields['name'],fields['city'],existing_bases(c))
                if matches:raise HTTPException(409,{'message':'پایگاه مشابه موجود است؛ شناسهٔ صحیح را برای پیوند انتخاب کنید.','matches':matches[:20]})
                target_source='kerman_bases_manual';target_id=c.execute(text('INSERT INTO kerman_bases_manual(name,city,address,phone,type,latitude,longitude,visit_radius_m) VALUES(:name,:city,:address,:phone,:category,:latitude,:longitude,150) RETURNING id'),fields).scalar()
            if row['base_id'] and row['review_status']=='changed_after_review' and not data.apply_base_update:raise HTTPException(409,'به‌روزرسانی پایگاه موجود نیازمند تأیید صریح اعمال تغییرات است.')
            if data.apply_base_update:
                c.execute(text('UPDATE '+target_source+' SET name=:name,city=:city,address=:address,phone=:phone,type=:category,latitude=:latitude,longitude=:longitude WHERE id=:id'),{**fields,'id':target_id})
            # Only explicitly reviewed fields may update a linked base.
            c.execute(text("UPDATE prospect_candidates SET review_status='approved',reviewed_by=:uid,reviewed_at=NOW(),review_note=:note,base_source=:source,base_id=:base WHERE id=:id"),{'id':str(ident),'uid':user['id'],'note':data.note,'source':target_source,'base':target_id});result={'state':'approved','base_source':target_source,'base_id':target_id,'existing_base_overwritten':bool(data.apply_base_update)}
        c.execute(text('INSERT INTO prospect_reviews(candidate_id,revision,actor_id,decision,note,payload) VALUES(:id,:revision,:uid,:decision,:note,CAST(:payload AS JSONB))'),{'id':str(ident),'revision':data.expected_revision,'uid':user['id'],'decision':data.decision,'note':data.note,'payload':encode(data.model_dump(mode='json'))})
    return result
