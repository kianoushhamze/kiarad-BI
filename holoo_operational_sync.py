"""Transactional local mirror of verified Holoo feeds; never an ERP write.

Sales are signed merchandise amounts in IRR after discounts, excluding tax.
Returns are separate documents with negative amounts and negative quantities.
ERP identity, not the non-unique document number, is the idempotency key.
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from sqlalchemy import text
from db import engine
from holoo_finance import numeric
from holoo_mappings import ensure_holoo_entity_mappings, save_holoo_entity_mapping
from purchase_profit import _day, _normalize_invoice

SEMANTICS={'header_sum_price':'gross_before_discount_tax','header_discount_scope':'includes_line_discounts'}


class ProjectionError(ValueError):
    pass


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,allow_nan=False)


def identity(value):
    if value is None or isinstance(value,bool) or not str(value).strip():
        raise ProjectionError('missing_identity')
    return str(value).strip()


def active(value):
    if value in (True,1,'1','True','true'):return 1
    if value in (False,0,'0','False','false'):return 0
    raise ProjectionError('invalid_product_activity')


def ensure_schema(conn):
    ensure_holoo_entity_mappings(conn)
    for column in ('holoo_kind SMALLINT','holoo_erp_code TEXT','holoo_snapshot_id BIGINT','holoo_payload_hash TEXT'):
        exists=conn.execute(text("SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass('sales') AND attname=:name AND NOT attisdropped"),{'name':column.split()[0]}).first()
        if not exists:conn.execute(text('ALTER TABLE sales ADD COLUMN '+column))
    conn.execute(text('DROP INDEX IF EXISTS uq_sales_holoo_sanad'))
    conn.execute(text('''CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_holoo_identity
        ON sales(holoo_kind,holoo_erp_code) WHERE holoo_erp_code IS NOT NULL'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS holoo_operational_audit(
        id BIGSERIAL PRIMARY KEY,snapshot_id BIGINT NOT NULL,sale_id INT NOT NULL,operation TEXT NOT NULL,
        old_row JSONB,old_items JSONB,new_row JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS holoo_operational_runs(
        snapshot_id BIGINT PRIMARY KEY,receipt JSONB NOT NULL,finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'''))
    human_required=conn.execute(text("SELECT attnotnull FROM pg_attribute WHERE attrelid=to_regclass('receivable_snapshots') AND attname='imported_by' AND NOT attisdropped")).scalar()
    if human_required:
        # NULL explicitly identifies a system import, not a fabricated human approval.
        conn.execute(text('ALTER TABLE receivable_snapshots ALTER COLUMN imported_by DROP NOT NULL'))


def audit(conn,snapshot_id,row,operation,new_row=None):
    items=[dict(r) for r in conn.execute(text('SELECT * FROM sale_items WHERE sale_id=:s ORDER BY id'),{'s':row['id']}).mappings()]
    conn.execute(text('''INSERT INTO holoo_operational_audit(snapshot_id,sale_id,operation,old_row,old_items,new_row)
        VALUES(:snap,:sale,:op,CAST(:old AS JSONB),CAST(:items AS JSONB),CAST(:new AS JSONB))'''),
        {'snap':snapshot_id,'sale':row['id'],'op':operation,'old':encode(dict(row)),'items':encode(items),'new':encode(new_row)})


def feed(payload,kind):
    value=payload.get('sources',{}).get(kind,{})
    if not value.get('ok') or not value.get('complete') or not isinstance(value.get('rows'),list):
        raise ProjectionError('incomplete_'+kind)
    return value['rows']


def entities(conn,payload,factor):
    from product_pricing import ensure_product_prices
    from data_sources import ensure_source_storage, apply_manual_fields
    ensure_product_prices(conn)
    ensure_source_storage(conn)
    result={}
    for kind,table,entity in (('customers','customers','customer'),('products','products','product')):
        rows=feed(payload,kind)
        keys=[identity(r.get('ErpCode')) for r in rows]
        codes=[identity(r.get('Code') or r.get('ErpCode')) for r in rows]
        if len(set(keys))!=len(keys) or len(set(codes))!=len(codes):raise ProjectionError('duplicate_'+kind+'_identity')
        local={str(r['code']):dict(r) for r in conn.execute(text(f'SELECT * FROM {table}')).mappings()}
        mappings=[dict(r) for r in conn.execute(text('SELECT local_id,holoo_erp_code FROM holoo_entity_mappings WHERE entity_type=:e'),{'e':entity}).mappings()]
        counts=Counter(r['holoo_erp_code'] for r in mappings)
        if any(v>1 for v in counts.values()):raise ProjectionError('ambiguous_'+kind+'_mapping')
        by_erp={r['holoo_erp_code']:r['local_id'] for r in mappings};by_local={r['local_id']:r['holoo_erp_code'] for r in mappings}
        result[kind]={}
        for row,key,code in zip(rows,keys,codes):
            candidates={r['id'] for k in (code,key) if (r:=local.get(k)) is not None}
            if key in by_erp:candidates.add(by_erp[key])
            if len(candidates)>1:raise ProjectionError('conflicting_'+kind+'_mapping')
            local_id=next(iter(candidates),None)
            if local_id and local_id in by_local and by_local[local_id]!=key:raise ProjectionError('changed_'+kind+'_identity')
            params={'code':code,'name':str(row.get('Name') or '').strip() or 'نام در هلو ثبت نشده'}
            if kind=='products':
                price=numeric(row.get('SellPrice'))*factor
                if price<0:raise ProjectionError('negative_product_price')
                params.update(price=price,stock=numeric(row.get('Few')),active=active(row.get('IsActive')))
                second=row.get('SellPrice2')
                params['price2']=numeric(second)*factor if second is not None else None
                if params['price2'] is not None and params['price2']<0:raise ProjectionError('negative_product_price2')
            if local_id is None:
                sql='INSERT INTO customers(code,name,created_at) VALUES(:code,:name,NOW()) RETURNING id' if kind=='customers' else '''INSERT INTO products(code,name,price,price2,stock,is_active,min_stock,updated_at)
                    VALUES(:code,:name,:price,:price2,:stock,:active,0,NOW()) RETURNING id'''
                local_id=conn.execute(text(sql),params).scalar_one()
            else:
                conn.execute(text(f'SELECT id FROM {table} WHERE id=:id FOR UPDATE'),{'id':local_id})
                params=apply_manual_fields(conn,kind,local_id,params)
                params['id']=local_id
                sql='UPDATE customers SET code=:code,name=:name WHERE id=:id' if kind=='customers' else 'UPDATE products SET code=:code,name=:name,price=:price,price2=:price2,stock=:stock,is_active=:active,updated_at=NOW() WHERE id=:id'
                conn.execute(text(sql),params)
            save_holoo_entity_mapping(conn,entity,local_id,key)
            result[kind][key]=local_id
    return result


def documents(payload,maps,factor):
    start,end=_day(payload['from_date']),_day(payload['to_date']);result=[]
    for kind,number,sign in (('sales',2,1),('sales_returns',4,-1)):
        seen=set()
        for row in feed(payload,kind):
            key=identity(row.get('ErpCode'))
            if key in seen:raise ProjectionError('duplicate_invoice_erp')
            seen.add(key)
            day=_day(row.get('Date'))
            if not start<=day<=end:raise ProjectionError('invoice_outside_source_window')
            customer=maps['customers'].get(identity(row.get('CustomerErpCode')))
            if customer is None:raise ProjectionError('unmapped_invoice_customer')
            items,net,amounts=_normalize_invoice(row,factor,SEMANTICS)
            lines=[]
            for item in items:
                product=maps['products'].get(item['product'])
                if product is None:raise ProjectionError('unmapped_invoice_product')
                lines.append({'product_id':product,'quantity':str(item['quantity']*sign),'price':str(item['net']/item['quantity'])})
            raw_sanad=row.get('SanadCode');sanad=None
            if raw_sanad is not None:
                try:sanad=int(raw_sanad)
                except (ValueError,TypeError):raise ProjectionError('invalid_document_number')
            content={'kind':number,'erp':key,'customer_id':customer,'date':day.isoformat(),'total_amount':str(net*sign),'sanad':sanad,'items':lines,
                     'amount_basis':'net_merchandise_irr_excluding_tax','gross_irr':str(amounts['gross']),'discount_irr':str(amounts['discount']),'tax_irr':str(amounts['tax'])}
            content['hash']=hashlib.sha256(encode(content).encode()).hexdigest()
            result.append(content)
    return result


def receivables(conn,snapshot,payload,maps,factor):
    rows=[]
    for r in feed(payload,'customers'):
        value=numeric(r.get('Mandeh'))*factor
        if value>0:rows.append((maps['customers'][identity(r['ErpCode'])],str(r.get('Name') or 'نام در هلو ثبت نشده'),value))
    total=sum((r[2] for r in rows),Decimal(0))
    digest=hashlib.sha256(('holoo:'+str(snapshot)+':receivables').encode()).hexdigest()
    ident=conn.execute(text('''INSERT INTO receivable_snapshots(source_file,import_hash,report_from_text,report_to_text,snapshot_date,total_amount,row_count,created_at)
        VALUES(:source,:hash,:start,:end,:date,:total,:count,NOW()) RETURNING id'''),{'source':'holoo:customers:'+str(snapshot),'hash':digest,'start':payload['from_date'],'end':payload['to_date'],'date':_day(payload['to_date']),'total':total,'count':len(rows)}).scalar_one()
    for customer,name,value in rows:
        conn.execute(text('''INSERT INTO receivable_balances(snapshot_id,counterparty,normalized_counterparty,balance,share_percent,customer_id,created_at)
            VALUES(:snap,:name,:norm,:balance,:share,:customer,NOW())'''),{'snap':ident,'name':name,'norm':name.strip().replace('ي','ی').replace('ك','ک'),'balance':value,'share':value/total*100 if total else 0,'customer':customer})
    return ident,len(rows)


def apply_snapshot(conn,snapshot):
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('kiarad:operational-sync',0))"))
    ensure_schema(conn)
    newest=conn.execute(text('SELECT MAX(snapshot_id) FROM holoo_operational_runs')).scalar()
    if newest is not None and newest>snapshot['id']:raise ProjectionError('out_of_order_snapshot')
    age=(datetime.now(timezone.utc)-snapshot['captured_at']).total_seconds()
    if age>600 or age < -60:raise ProjectionError('stale_source')
    previous=conn.execute(text('SELECT receipt FROM holoo_operational_runs WHERE snapshot_id=:s'),{'s':snapshot['id']}).scalar()
    if previous:return {**previous,'already_applied':True}
    payload=snapshot['payload'];factor=numeric(payload.get('currency_factor'))
    if factor not in (1,10):raise ProjectionError('currency_unverified')
    maps=entities(conn,payload,factor)
    docs=documents(payload,maps,factor)
    start,end=_day(payload['from_date']),_day(payload['to_date'])
    receipt={'status':'completed','snapshot_id':snapshot['id'],'customers':len(maps['customers']),'products':len(maps['products']),'sales':sum(d['kind']==2 for d in docs),'returns':sum(d['kind']==4 for d in docs),'inserted':0,'updated':0,'unchanged':0,'archived_legacy':0,'removed_from_mirror':0,'amount_basis':'net_merchandise_irr_excluding_tax','salesperson_attribution':'preserved_only_never_guessed','erp_writes':False}
    # Legacy source rows have no stable ERP identity. Archive unattributed rows,
    # then reconstruct the mirror rather than guessing which repeated number is which.
    legacy=conn.execute(text('''SELECT * FROM sales WHERE holoo_sanad IS NOT NULL AND holoo_erp_code IS NULL
        AND date::date BETWEEN :start AND :end FOR UPDATE'''),{'start':start,'end':end}).mappings().all()
    if newest is not None and legacy:raise ProjectionError('legacy_writer_still_active')
    assigned=[r for r in legacy if r['salesperson_id'] is not None]
    for old in assigned:
        matches=[d for d in docs if d['kind']==2 and d['sanad']==old['holoo_sanad'] and d['customer_id']==old['customer_id'] and d['date']==old['date'].date().isoformat()]
        if len(matches)!=1:raise ProjectionError('ambiguous_attributed_legacy_identity')
        match=matches[0]
        audit(conn,snapshot['id'],old,'adopt_explicit_legacy_identity',match)
        conn.execute(text('UPDATE sales SET holoo_kind=2,holoo_erp_code=:e WHERE id=:id'),{'e':match['erp'],'id':old['id']})
    for old in legacy:
        if old['salesperson_id'] is not None:continue
        audit(conn,snapshot['id'],old,'replace_legacy_without_erp_identity')
        conn.execute(text('DELETE FROM sale_items WHERE sale_id=:id'),{'id':old['id']})
        conn.execute(text('DELETE FROM sales WHERE id=:id'),{'id':old['id']});receipt['archived_legacy']+=1
    for d in docs:
        old=conn.execute(text('SELECT * FROM sales WHERE holoo_kind=:k AND holoo_erp_code=:e FOR UPDATE'),{'k':d['kind'],'e':d['erp']}).mappings().first()
        params={'k':d['kind'],'e':d['erp'],'snap':snapshot['id'],'hash':d['hash'],'customer':d['customer_id'],'date':_day(d['date']),'amount':Decimal(d['total_amount']),'sanad':d['sanad']}
        if old and old['holoo_payload_hash']==d['hash']:
            conn.execute(text('UPDATE sales SET holoo_snapshot_id=:snap WHERE id=:id'),{'snap':snapshot['id'],'id':old['id']});receipt['unchanged']+=1;continue
        if old:
            if old['customer_id']!=d['customer_id'] and old['salesperson_id'] is not None:raise ProjectionError('attributed_invoice_customer_changed')
            audit(conn,snapshot['id'],old,'update_mirror',d);params['id']=old['id']
            conn.execute(text('''UPDATE sales SET customer_id=:customer,date=:date,total_amount=:amount,holoo_sanad=:sanad,
                holoo_snapshot_id=:snap,holoo_payload_hash=:hash WHERE id=:id'''),params)
            ident=old['id'];conn.execute(text('DELETE FROM sale_items WHERE sale_id=:id'),{'id':ident});receipt['updated']+=1
        else:
            archived=conn.execute(text('''SELECT old_row FROM holoo_operational_audit WHERE operation='absent_from_complete_source'
                AND old_row->>'holoo_erp_code'=:e AND (old_row->>'holoo_kind')::int=:k ORDER BY id DESC LIMIT 1'''),{'e':d['erp'],'k':d['kind']}).scalar()
            params['owner']=archived.get('salesperson_id') if archived else None
            if params['owner'] is not None and archived['customer_id']!=d['customer_id']:raise ProjectionError('restored_attributed_customer_changed')
            ident=conn.execute(text('''INSERT INTO sales(customer_id,salesperson_id,date,total_amount,holoo_sanad,holoo_kind,holoo_erp_code,holoo_snapshot_id,holoo_payload_hash)
                VALUES(:customer,:owner,:date,:amount,:sanad,:k,:e,:snap,:hash) RETURNING id'''),params).scalar_one();receipt['inserted']+=1
        for line in d['items']:
            conn.execute(text('INSERT INTO sale_items(sale_id,product_id,quantity,price) VALUES(:sale,:product,:qty,:price)'),{'sale':ident,'product':line['product_id'],'qty':Decimal(line['quantity']),'price':Decimal(line['price'])})
    missing=conn.execute(text('''SELECT * FROM sales WHERE holoo_kind IN (2,4) AND holoo_erp_code IS NOT NULL AND holoo_snapshot_id<>:snap
        AND date::date BETWEEN :start AND :end FOR UPDATE'''),{'snap':snapshot['id'],'start':start,'end':end}).mappings().all()
    for old in missing:
        audit(conn,snapshot['id'],old,'absent_from_complete_source')
        conn.execute(text('DELETE FROM sale_items WHERE sale_id=:id'),{'id':old['id']})
        conn.execute(text('DELETE FROM sales WHERE id=:id'),{'id':old['id']});receipt['removed_from_mirror']+=1
    ar_id,ar_count=receivables(conn,snapshot['id'],payload,maps,factor)
    receipt.update(receivable_snapshot_id=ar_id,receivable_customers=ar_count)
    conn.execute(text('INSERT INTO holoo_operational_runs(snapshot_id,receipt) VALUES(:snap,CAST(:receipt AS JSONB))'),{'snap':snapshot['id'],'receipt':encode(receipt)})
    return receipt


def operational_status(conn,manager=False):
    if not conn.execute(text("SELECT to_regclass('holoo_operational_runs') IS NOT NULL")).scalar():
        return {'status':'not_synced','amount_basis':'net_merchandise_irr_excluding_tax'}
    row=conn.execute(text('SELECT snapshot_id,finished_at,receipt FROM holoo_operational_runs ORDER BY snapshot_id DESC LIMIT 1')).mappings().first()
    if not row:return {'status':'not_synced','amount_basis':'net_merchandise_irr_excluding_tax'}
    age=(datetime.now(timezone.utc)-row['finished_at']).total_seconds()
    latest=conn.execute(text('SELECT MAX(id) FROM holoo_financial_snapshots')).scalar()
    state='behind_source' if latest!=row['snapshot_id'] else 'fresh' if 0<=age<=600 else 'stale'
    result={'status':state,'snapshot_id':row['snapshot_id'],'finished_at':row['finished_at'],
            'amount_basis':'net_merchandise_irr_excluding_tax','document_count_includes_returns':True,'scope':'company' if manager else 'only_explicitly_attributed_to_you'}
    if manager:
        result['unattributed_documents']=conn.execute(text('SELECT count(*) FROM sales WHERE holoo_erp_code IS NOT NULL AND salesperson_id IS NULL')).scalar()
    return result


def sync_operational_snapshot(snapshot_id=None,dry_run=False):
    with engine.connect() as conn:
        tx=conn.begin()
        try:
            snapshot=conn.execute(text('SELECT id,captured_at,payload FROM holoo_financial_snapshots '+('WHERE id=:id' if snapshot_id is not None else 'ORDER BY id DESC LIMIT 1')),{'id':snapshot_id}).mappings().first()
            if not snapshot:raise ProjectionError('source_missing')
            result=apply_snapshot(conn,snapshot)
            if dry_run:tx.rollback()
            else:tx.commit()
            return {**result,'dry_run':dry_run}
        except Exception:
            tx.rollback();raise
