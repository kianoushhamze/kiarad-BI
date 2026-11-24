"""Preview/commit entry for operational records. Never writes to Holoo."""
from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import text
from db import engine
from operations import current_user
from data_sources import FIELDS,ensure_source_storage,save_manual_fields,encoded,restore_holoo_fields
from treasury_excel import table,number,day,norm,MAX_FILE
from target_schema import normalize_person_target

router=APIRouter(prefix='/data-entry',tags=['data-entry'])
# key, Persian label, type, required
SPECS={
 'products':{'label':'کالاها','module':'catalog','href':'/catalog','holoo':True,'fields':[
  ('code','کد کالا','text',True),('name','نام کالا','text',True),('price','قیمت ۱','money',True),
  ('price2','قیمت ۲','money',False),('stock','موجودی','number',True),('min_stock','حد سفارش','number',False),
  ('category','دسته','text',False),('is_active','فعال ـ صفر یا یک','flag',False)]},
 'customers':{'label':'مشتریان','module':'customers','href':'/customers','holoo':True,'fields':[
  ('code','کد مشتری','text',True),('name','نام مشتری','text',True),('phone','تلفن','text',False),
  ('city','شهر','text',False),('credit_limit','سقف اعتبار ـ صفر یعنی بدون سقف ثبت‌شده','money',True)]},
 'targets':{'label':'هدف‌های فروش','module':'personnel','href':'/person-targets','holoo':False,'fields':[
  ('title','عنوان','text',True),('salesperson_id','شناسه پرسنل ـ خالی برای شرکت','id',False),
  ('target_amount','مبلغ هدف','positive_money',True),('bonus_reward','پاداش','money',False),
  ('start_date','شروع','date',True),('end_date','پایان','date',True),('product_focus','تمرکز کالایی','text',False),
  ('target_type','نوع هدف ـ فروش یا تسویه','text',False)]},
 'batches':{'label':'بچ و انقضا','module':'catalog','href':'/catalog','holoo':False,'fields':[
  ('product_code','کد کالا','text',True),('batch_code','شماره بچ','text',True),
  ('expiry_date','تاریخ انقضا','date',True),('quantity','تعداد','positive_number',True),('note','توضیح','text',False)]},
 'sales-assignments':{'label':'انتساب فروشندهٔ فاکتور','module':'personnel','href':'/personnel','holoo':False,'fields':[
  ('holoo_kind','نوع سند ـ فروش ۲ یا برگشت ۴','id',True),
  ('holoo_erp_code','شناسهٔ یکتای سند هلو','text',True),
  ('salesperson_id','شناسهٔ پرسنل','id',True)]},
}


def allowed(entity,user):
    if entity not in SPECS:raise HTTPException(404,'نوع ورود پیدا نشد.')
    if user.get('role') not in {'ceo','sales_manager','finance'} or (entity=='targets' and user.get('role')=='finance'):
        raise HTTPException(403,'ورود این اطلاعات در دسترسی شما نیست.')


def ensure_entry_storage(conn):
    ensure_source_storage(conn)
    conn.execute(text('''CREATE TABLE IF NOT EXISTS data_entry_batches (
        id BIGSERIAL PRIMARY KEY,entity TEXT NOT NULL,created_by INT NOT NULL,
        input_mode TEXT NOT NULL,content_hash TEXT NOT NULL,payload JSONB NOT NULL,
        status TEXT NOT NULL DEFAULT 'preview',receipt JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),committed_at TIMESTAMPTZ,
        UNIQUE(entity,created_by,content_hash))'''))


@router.on_event('startup')
def initialize_entries():
    from catalog import ensure_inventory_batches
    ensure_inventory_batches()
    with engine.begin() as conn:ensure_entry_storage(conn)


@router.get('/schema')
def schema(user=Depends(current_user)):
    if user.get('role') not in {'ceo','sales_manager','finance'}:raise HTTPException(403,'دسترسی مدیریتی لازم است.')
    return {'entities':[{'id':key,**value,'fields':[{'key':k,'label':label,'type':kind,'required':required} for k,label,kind,required in value['fields']]}
        for key,value in SPECS.items() if key!='targets' or user['role']!='finance'],
        'money_units':['IRR','TOMAN'],'max_rows':500,'erp_writes':False}


def normalize_rows(entity,rows,unit):
    if entity not in SPECS or unit not in {'IRR','TOMAN'}:raise HTTPException(422,'نوع ورود و واحد مبلغ معتبر لازم است.')
    if not rows or len(rows)>500:raise HTTPException(422,'بین یک تا پانصد ردیف مجاز است.')
    normalized=[];seen=set();spec=SPECS[entity]
    for index,row in enumerate(rows,1):
        if not isinstance(row,dict) or not set(row)<={f[0] for f in spec['fields']}:raise HTTPException(422,f'ردیف {index}: فیلد ناشناخته.')
        output={}
        for key,label,kind,required in spec['fields']:
            raw=row.get(key)
            if raw is None or raw=='':
                if required:raise HTTPException(422,f'ردیف {index}: {label} لازم است.')
                continue
            if kind in {'money','positive_money','number','positive_number','id','flag'}:
                value=number(raw,factor=10 if 'money' in kind and unit=='TOMAN' else 1)
                limit=Decimal('1e15') if 'money' in kind else Decimal('1e9')
                if value>limit or (kind.startswith('positive') and value<=0) or (kind=='id' and (value!=int(value) or value<=0)) or (kind=='flag' and value not in (0,1)):
                    raise HTTPException(422,f'ردیف {index}: {label} خارج از محدوده است.')
                output[key]=int(value) if kind in {'id','flag'} else str(value)
            elif kind=='date':output[key]=day(str(raw))
            else:
                if not isinstance(raw,str):raise HTTPException(422,f'ردیف {index}: {label} را متن وارد کنید؛ کدها باید متن باشند تا صفر اول حذف نشود.')
                value=norm(raw)
                limit=64 if 'code' in key else 30 if key=='phone' else 1000 if key=='note' else 150
                if not value or len(value)>limit or value[0] in '=+@' or '\x00' in value:raise HTTPException(422,f'ردیف {index}: {label} معتبر نیست.')
                output[key]=value
        if entity=='sales-assignments':
            if output['holoo_kind'] not in (2,4):raise HTTPException(422,'نوع سند باید فروش ۲ یا برگشت فروش ۴ باشد.')
            key=(output['holoo_kind'],output['holoo_erp_code'])
        elif entity=='targets':
            if output.get('target_type') not in (None, 'فروش', 'تسویه'):
                raise HTTPException(422, f'ردیف {index}: نوع هدف باید فروش یا تسویه باشد.')
            normalize_person_target(output)
            key=(output['title'],output.get('salesperson_id'),output['start_date'],output['end_date'],output.get('target_type') == 'تسویه')
        else:key=(output.get('product_code'),output['batch_code']) if entity=='batches' else output['code']
        if key in seen:raise HTTPException(422,f'ردیف {index}: کلید تکراری در همین ورودی.')
        seen.add(key);normalized.append(output)
    return normalized


def plan_rows(conn,entity,rows,lock=False):
    plan=[]
    for values in rows:
        if entity=='sales-assignments':
            if not conn.execute(text('SELECT id FROM salespersons WHERE id=:id'),{'id':values['salesperson_id']}).first():raise HTTPException(422,'شناسهٔ پرسنل پیدا نشد.')
            found=conn.execute(text('SELECT id,holoo_kind,holoo_erp_code,salesperson_id FROM sales WHERE holoo_kind=:kind AND holoo_erp_code=:code'+(' FOR UPDATE' if lock else '')),
                {'kind':values['holoo_kind'],'code':values['holoo_erp_code']}).mappings().all()
            if len(found)!=1:raise HTTPException(409,'شناسهٔ سند هلو باید موجود و یکتا باشد.')
            if found[0]['salesperson_id'] not in (None,values['salesperson_id']):raise HTTPException(409,'این سند قبلاً به فرد دیگری منتسب شده؛ تغییر آن از ورود گروهی مجاز نیست.')
        elif entity in {'products','customers'}:
            found=conn.execute(text(f"SELECT * FROM {entity} WHERE code=:code"+(' FOR UPDATE' if lock else '')),{'code':values['code']}).mappings().all()
        elif entity=='targets':
            sid=values.get('salesperson_id')
            if sid and not conn.execute(text('SELECT id FROM salespersons WHERE id=:id'),{'id':sid}).first():raise HTTPException(422,'شناسهٔ پرسنل هدف پیدا نشد؛ نام شخص حدس زده نمی‌شود.')
            found=conn.execute(text('''SELECT * FROM targets WHERE title=:title
                AND salesperson_id IS NOT DISTINCT FROM :sid AND start_date=:start AND end_date=:end
                AND (:kind IS NULL OR (COALESCE(target_type,'')='تسویه')=(:kind='تسویه'))'''+(' FOR UPDATE' if lock else '')),
                {'title':values['title'],'sid':sid,'start':values['start_date'],'end':values['end_date'],
                 'kind':values.get('target_type')}).mappings().all()
        else:
            product=conn.execute(text('SELECT id FROM products WHERE code=:code'),{'code':values['product_code']}).scalars().all()
            if len(product)!=1:raise HTTPException(422,'کد کالا در ردیف بچ باید دقیق و یکتا باشد.')
            values={**values,'product_id':product[0]}
            found=conn.execute(text('SELECT * FROM inventory_batches WHERE product_id=:id AND batch_code=:batch'+(' FOR UPDATE' if lock else '')),{'id':product[0],'batch':values['batch_code']}).mappings().all()
        if len(found)>1:raise HTTPException(409,'کلید چند رکورد را مشخص می‌کند؛ ابتدا رکوردهای تکراری را تطبیق دهید.')
        old=dict(found[0]) if found else None
        expected=sha256(encoded(old).encode()).hexdigest() if old else None
        plan.append({'values':values,'id':old['id'] if old else None,'expected':expected,'action':'update' if old else 'create'})
    return plan


class ManualInput(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    unit:str
    rows:list[dict]=Field(min_length=1,max_length=500)


def store_preview(conn,entity,rows,user,mode):
    ensure_entry_storage(conn)
    if entity=='batches':
        # Storage exists at normal application startup; tests create isolated equivalents.
        if not conn.execute(text("SELECT to_regclass('inventory_batches') IS NOT NULL")).scalar():
            raise HTTPException(409,'جدول بچ آماده نیست؛ سرویس را راه‌اندازی کنید.')
    digest=sha256(encoded(rows).encode()).hexdigest()
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'entry:{entity}:{user["id"]}:{digest}'})
    old=conn.execute(text('SELECT id,status,payload,receipt FROM data_entry_batches WHERE entity=:e AND created_by=:u AND content_hash=:h'),{'e':entity,'u':user['id'],'h':digest}).mappings().first()
    if old and old['status']=='committed':return {'id':old['id'],'status':'committed','entity':entity,'rows':old['payload']['plan'],'row_count':len(rows),'reused':True,'receipt':old['receipt']}
    plan=plan_rows(conn,entity,rows)
    if old:
        if old['status']=='preview':
            conn.execute(text('UPDATE data_entry_batches SET payload=CAST(:p AS JSONB),created_at=NOW(),input_mode=:mode WHERE id=:id'),{'p':encoded({'rows':rows,'plan':plan}),'id':old['id'],'mode':mode})
        return {'id':old['id'],'status':old['status'],'entity':entity,'rows':plan if old['status']=='preview' else old['payload']['plan'],'row_count':len(rows),'reused':True,'receipt':old['receipt']}
    ident=conn.execute(text('''INSERT INTO data_entry_batches(entity,created_by,input_mode,content_hash,payload)
        VALUES(:e,:u,:m,:h,CAST(:p AS JSONB)) RETURNING id'''),{'e':entity,'u':user['id'],'m':mode,'h':digest,'p':encoded({'rows':rows,'plan':plan})}).scalar_one()
    return {'id':ident,'status':'preview','entity':entity,'rows':plan,'row_count':len(rows),'erp_writes':False}


@router.post('/{entity}/manual/preview')
def manual_preview(entity:str,data:ManualInput,user=Depends(current_user)):
    allowed(entity,user)
    rows=normalize_rows(entity,data.rows,data.unit)
    with engine.begin() as conn:return store_preview(conn,entity,rows,user,'manual')


@router.post('/{entity}/excel/preview')
async def excel_preview(entity:str,file:UploadFile=File(...),unit:str=Form(...),sheet_name:str=Form(''),user=Depends(current_user)):
    allowed(entity,user)
    content=await file.read(MAX_FILE+1)
    headers,values,_=table(content,sheet_name)
    names={norm(label):key for key,label,_,_ in SPECS[entity]['fields']}
    if not set(headers)<=set(names):raise HTTPException(422,'قالب همین بخش را دانلود کنید؛ ستون ناشناخته مجاز نیست.')
    rows=normalize_rows(entity,[{names[h]:value for h,value in zip(headers,row)} for row in values],unit)
    with engine.begin() as conn:return store_preview(conn,entity,rows,user,'excel')


@router.get('/{entity}/template')
def template(entity:str,user=Depends(current_user)):
    allowed(entity,user)
    import openpyxl
    workbook=openpyxl.Workbook();sheet=workbook.active;sheet.title=SPECS[entity]['label'][:31]
    if entity=='sales-assignments':
        with engine.connect() as conn:
            pending=conn.execute(text('SELECT holoo_kind,holoo_erp_code FROM sales WHERE holoo_erp_code IS NOT NULL AND salesperson_id IS NULL ORDER BY date,id')).mappings().all()
            people=conn.execute(text('SELECT id,name FROM salespersons ORDER BY id')).all()
        for start in range(0,max(1,len(pending)),500):
            page=sheet if start==0 else workbook.create_sheet()
            page.title=f'اسناد {start//500+1}'
            page.append([field[1] for field in SPECS[entity]['fields']])
            for row in pending[start:start+500]:
                code=str(row['holoo_erp_code'])
                if code.startswith(('=','+','-','@','\t','\r')):raise HTTPException(422,'شناسهٔ سند برای خروجی اکسل معتبر نیست.')
                page.append([str(row['holoo_kind']),code,''])
            for column in range(1,4):
                page.column_dimensions[page.cell(1,column).column_letter].width=32
                for index in range(2,502):page.cell(index,column).number_format='@'
        reference=workbook.create_sheet('راهنمای پرسنل');reference.append(['شناسهٔ پرسنل','نام پرسنل'])
        for ident,name in people:
            name=str(name or '')
            reference.append([ident,"'"+name if name.startswith(('=','+','-','@')) else name])
        reference.column_dimensions['B'].width=35
        stream=BytesIO();workbook.save(stream)
        return Response(stream.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="sales-assignments-entry.xlsx"'})
    sheet.append([field[1] for field in SPECS[entity]['fields']])
    for column,field in enumerate(SPECS[entity]['fields'],1):
        sheet.column_dimensions[sheet.cell(1,column).column_letter].width=28
        for index in range(2,502):sheet.cell(index,column).number_format='@'
    stream=BytesIO();workbook.save(stream)
    return Response(stream.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{entity}-entry.xlsx"'})


def refresh_view(status,entity):
    return {'status':status.get('status'),'finished_at':status.get('finished_at'),
        'sources':[{'kind':row.get('kind'),'count':row.get('count'),'ok':row.get('ok'),'complete':row.get('complete')} for row in status.get('sources',[]) if row.get('kind')==entity],
        'erp_writes':False,'manual_fields_preserved':True}


@router.get('/{entity}/holoo-refresh')
def holoo_refresh_status(entity:str,user=Depends(current_user)):
    allowed(entity,user)
    if not SPECS[entity]['holoo']:raise HTTPException(422,'این بخش منبع مستقیم هلو ندارد.')
    from holoo_finance_jobs import financial_refresh_status
    return refresh_view(financial_refresh_status(),entity)


@router.post('/{entity}/holoo-refresh',status_code=202)
def request_holoo_refresh(entity:str,user=Depends(current_user)):
    allowed(entity,user)
    if not SPECS[entity]['holoo']:raise HTTPException(422,'این بخش منبع مستقیم هلو ندارد.')
    from holoo_finance_jobs import start_financial_refresh
    return refresh_view(start_financial_refresh(),entity)


class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    confirm:bool


@router.post('/{entity}/{batch_id}/commit')
def commit(entity:str,batch_id:int,data:Confirm,user=Depends(current_user)):
    allowed(entity,user)
    if not data.confirm:raise HTTPException(422,'تأیید صریح لازم است.')
    with engine.begin() as conn:
        ensure_entry_storage(conn)
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'data-entry:'+entity})
        batch=conn.execute(text('SELECT * FROM data_entry_batches WHERE id=:id FOR UPDATE'),{'id':batch_id}).mappings().first()
        if not batch or batch['entity']!=entity or batch['created_by']!=user['id']:raise HTTPException(404,'پیش‌نمایش متعلق به این حساب پیدا نشد.')
        if batch['status']=='committed':return {**batch['receipt'],'already_committed':True}
        if (datetime.now(timezone.utc)-batch['created_at']).total_seconds()>86400:raise HTTPException(409,'پیش‌نمایش قدیمی است؛ آن را تازه کنید.')
        plan=plan_rows(conn,entity,batch['payload']['rows'],lock=True)
        if encoded(plan)!=encoded(batch['payload']['plan']):raise HTTPException(409,'دیتا پس از پیش‌نمایش تغییر کرده؛ هیچ ردیفی ثبت نشد. پیش‌نمایش را تازه کنید.')
        created=updated=0;ids=[]
        for entry in plan:
            values=dict(entry['values']);ident=entry['id']
            if entity=='sales-assignments':
                conn.execute(text('UPDATE sales SET salesperson_id=:person WHERE id=:id'),{'person':values['salesperson_id'],'id':ident})
                updated+=1
            elif entity in FIELDS:
                if ident is None:
                    defaults={'min_stock':0,'is_active':1} if entity=='products' else {}
                    values={**defaults,**values}
                    timestamp='updated_at' if entity=='products' else 'created_at'
                    ident=conn.execute(text(f'INSERT INTO {entity} ('+', '.join(values)+f',{timestamp}) VALUES ('+', '.join(':'+key for key in values)+',NOW()) RETURNING id'),values).scalar_one()
                    created+=1
                else:updated+=1
                save_manual_fields(conn,entity,ident,{key:value for key,value in values.items() if key!='code'},int(user['id']),batch['input_mode'])
            elif entity=='targets':
                values={**values,'salesperson_id':values.get('salesperson_id')}
                if ident is None:
                    values=normalize_person_target({'period_type':'بازهٔ مشخص','target_type':'فروش',**values})
                    ident=conn.execute(text('INSERT INTO targets ('+', '.join(values)+',created_at) VALUES ('+', '.join(':'+key for key in values)+',NOW()) RETURNING id'),values).scalar_one();created+=1
                else:
                    values=normalize_person_target(values, existing=values)
                    conn.execute(text('UPDATE targets SET '+', '.join(f'{key}=:{key}' for key in values)+' WHERE id=:id'),{**values,'id':ident});updated+=1
            else:
                values.pop('product_code')
                if ident is None:
                    values.setdefault('note','')
                    ident=conn.execute(text('INSERT INTO inventory_batches ('+', '.join(values)+',created_by) VALUES ('+', '.join(':'+key for key in values)+',:actor) RETURNING id'),{**values,'actor':user['id']}).scalar_one();created+=1
                else:
                    conn.execute(text('UPDATE inventory_batches SET '+', '.join(f'{key}=:{key}' for key in values)+' WHERE id=:id'),{**values,'id':ident});updated+=1
            ids.append(ident)
        receipt={'status':'committed','created':created,'updated':updated,'ids':ids,'erp_writes':False}
        conn.execute(text("UPDATE data_entry_batches SET status='committed',receipt=CAST(:r AS JSONB),committed_at=NOW() WHERE id=:id"),{'r':encoded(receipt),'id':batch_id})
        return receipt


@router.post('/{entity}/{local_id}/restore-holoo')
def restore(entity:str,local_id:int,user=Depends(current_user)):
    allowed(entity,user)
    if entity not in FIELDS:raise HTTPException(422,'این بخش منبع مستقیم هلو ندارد.')
    with engine.begin() as conn:return restore_holoo_fields(conn,entity,local_id,int(user['id']))
