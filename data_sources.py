"""Explicit per-field manual authority for operational product/customer records."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from fastapi import HTTPException
from sqlalchemy import text

FIELDS={'products':{'name','category','price','price2','stock','min_stock','is_active'},
        'customers':{'name','phone','city','credit_limit'}}


def ensure_source_storage(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS data_field_overrides (
        entity TEXT NOT NULL,local_id INT NOT NULL,field TEXT NOT NULL,value JSONB NOT NULL,
        updated_by INT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(entity,local_id,field))'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS data_change_audit (
        id BIGSERIAL PRIMARY KEY,entity TEXT NOT NULL,local_id INT NOT NULL,
        source TEXT NOT NULL,old_values JSONB,new_values JSONB,changed_by INT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))


def encoded(value):
    return json.dumps(value,ensure_ascii=False,default=str,allow_nan=False,sort_keys=True)


def save_manual_fields(conn,entity,ident,values,user_id,source='manual'):
    if entity not in FIELDS or not values or not set(values)<=FIELDS[entity]:
        raise HTTPException(422,'فیلدهای ویرایش مجاز نیستند.')
    for field,value in values.items():
        if field in {'price','price2','stock','min_stock','credit_limit'}:
            try:
                parsed=Decimal(str(value))
                if isinstance(value,bool) or not parsed.is_finite() or not 0<=parsed<=Decimal('1e15'):raise ValueError()
            except (ValueError,TypeError,ArithmeticError):raise HTTPException(422,'قیمت، اعتبار و موجودی باید عدد معتبر و نامنفی باشند.')
        elif field=='is_active':
            if value not in (0,1):raise HTTPException(422,'وضعیت کالا باید صفر یا یک باشد.')
        elif not isinstance(value,str) or len(value)>(30 if field=='phone' else 150) or (field=='name' and not value.strip()):
            raise HTTPException(422,'متن ویرایش معتبر نیست.')
    old=conn.execute(text(f'SELECT * FROM {entity} WHERE id=:id FOR UPDATE'),{'id':ident}).mappings().first()
    if not old:raise HTTPException(404,'رکورد پیدا نشد.')
    conn.execute(text(f"UPDATE {entity} SET "+', '.join(f'{field}=:{field}' for field in values)+' WHERE id=:id'),{**values,'id':ident})
    for field,value in values.items():
        conn.execute(text('''INSERT INTO data_field_overrides(entity,local_id,field,value,updated_by)
            VALUES(:e,:id,:f,CAST(:v AS JSONB),:u) ON CONFLICT(entity,local_id,field)
            DO UPDATE SET value=EXCLUDED.value,updated_by=EXCLUDED.updated_by,updated_at=NOW()'''),
            {'e':entity,'id':ident,'f':field,'v':encoded(value),'u':user_id})
    conn.execute(text('''INSERT INTO data_change_audit(entity,local_id,source,old_values,new_values,changed_by)
        VALUES(:e,:id,:s,CAST(:old AS JSONB),CAST(:new AS JSONB),:u)'''),
        {'e':entity,'id':ident,'s':source,'old':encoded({key:old[key] for key in values}), 'new':encoded(values),'u':user_id})


def apply_manual_fields(conn,entity,ident,values):
    """Called under the synchronization transaction; never changes source snapshots."""
    rows=conn.execute(text('SELECT field,value FROM data_field_overrides WHERE entity=:e AND local_id=:id'),{'e':entity,'id':ident}).mappings()
    result=dict(values)
    for row in rows:
        if row['field'] in result and row['field'] in FIELDS[entity]:result[row['field']]=row['value']
    return result


def restore_holoo_fields(conn,entity,ident,user_id):
    if entity not in FIELDS:raise HTTPException(422,'نوع رکورد معتبر نیست.')
    # Same lock order as operational synchronization, then the individual row.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('kiarad:operational-sync',0))"))
    row=conn.execute(text(f'SELECT * FROM {entity} WHERE id=:id FOR UPDATE'),{'id':ident}).mappings().first()
    if not row:raise HTTPException(404,'رکورد پیدا نشد.')
    kind='product' if entity=='products' else 'customer'
    if not conn.execute(text("SELECT to_regclass('holoo_entity_mappings') IS NOT NULL AND to_regclass('holoo_financial_snapshots') IS NOT NULL")).scalar():
        raise HTTPException(409,'نسخهٔ هلو و نگاشت هنوز آماده نیست؛ ویرایش دستی حفظ شد.')
    codes=conn.execute(text('SELECT holoo_erp_code FROM holoo_entity_mappings WHERE entity_type=:e AND local_id=:id'),{'e':kind,'id':ident}).scalars().all()
    snapshot=conn.execute(text('SELECT captured_at,payload FROM holoo_financial_snapshots ORDER BY id DESC LIMIT 1')).mappings().first()
    if len(codes)!=1 or not snapshot:raise HTTPException(409,'این رکورد منبع هلو با شناسهٔ یکتا ندارد.')
    if conn.execute(text('SELECT COUNT(*) FROM holoo_entity_mappings WHERE entity_type=:e AND holoo_erp_code=:code'),{'e':kind,'code':codes[0]}).scalar()!=1:
        raise HTTPException(409,'نگاشت هلو یکتا نیست؛ ویرایش دستی حفظ شد.')
    age=(datetime.now(timezone.utc)-snapshot['captured_at']).total_seconds()
    source=snapshot['payload'].get('sources',{}).get(entity,{})
    matches=[item for item in source.get('rows',[]) if str(item.get('ErpCode'))==str(codes[0])]
    if not -60<=age<=600 or not source.get('ok') or not source.get('complete') or len(matches)!=1:
        raise HTTPException(409,'نسخهٔ تازه و کامل هلو لازم است؛ ویرایش دستی حفظ شد.')
    item=matches[0];values={'name':str(item.get('Name') or row['name'])}
    if entity=='products':
        from holoo_operational_sync import active
        from holoo_finance import numeric
        try:
            factor=Decimal(str(snapshot['payload'].get('currency_factor')))
            if factor not in (1,10):raise ValueError()
            values.update(price=numeric(item.get('SellPrice'))*factor,
                price2=numeric(item['SellPrice2'])*factor if item.get('SellPrice2') is not None else None,
                stock=numeric(item.get('Few')),is_active=active(item.get('IsActive')))
        except (ValueError,TypeError,ArithmeticError):raise HTTPException(409,'مقادیر یا واحد مبلغ منبع معتبر نیست؛ ویرایش دستی حفظ شد.')
    # Only fields actually supplied by Holoo are reset. Local metadata stays manual.
    conn.execute(text(f'UPDATE {entity} SET '+', '.join(f'{k}=:{k}' for k in values)+' WHERE id=:id'),{**values,'id':ident})
    for field in values:
        conn.execute(text('DELETE FROM data_field_overrides WHERE entity=:e AND local_id=:id AND field=:f'),{'e':entity,'id':ident,'f':field})
    conn.execute(text('''INSERT INTO data_change_audit(entity,local_id,source,old_values,new_values,changed_by)
        VALUES(:e,:id,'holoo_restore',CAST(:old AS JSONB),CAST(:new AS JSONB),:u)'''),
        {'e':entity,'id':ident,'old':encoded({key:row[key] for key in values}),'new':encoded(values),'u':user_id})
    return {'status':'restored','fields':list(values),'erp_writes':False}
