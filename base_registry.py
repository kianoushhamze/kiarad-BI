"""Explicit local Holoo-counterparty import; no ERP calls and no name matching."""
from collections import Counter
import json
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import text

BASES = ('pharmacies', 'cosmetics_shops', 'kerman_bases_manual')


def normalize_search(value):
    text = unicodedata.normalize('NFKC', str(value or '')).translate(str.maketrans(
        {'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'آ': 'ا', 'أ': 'ا', 'إ': 'ا',
         **{digit: str(index % 10) for index, digit in enumerate('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩')}}))
    text = re.sub('[ـ\u064b-\u065f\u0670]', '', text)
    return ' '.join(''.join(character if character.isalnum() else ' ' for character in text.casefold()).split())


def matches_search(query, *values):
    haystack = normalize_search(' '.join(str(value or '') for value in values))
    compact = haystack.replace(' ', '')
    return all(word in haystack or word in compact for word in normalize_search(query).split())


def ensure_registry(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS holoo_customer_bases(
        customer_id INTEGER PRIMARY KEY, holoo_erp_code TEXT NOT NULL UNIQUE,
        base_source TEXT NOT NULL CHECK(base_source IN ('pharmacies','cosmetics_shops','kerman_bases_manual')),
        base_id INTEGER NOT NULL, snapshot_id BIGINT NOT NULL, imported_by INTEGER NOT NULL,
        imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(base_source,base_id))'''))


def _source(conn):
    row = conn.execute(text('''SELECT s.id,s.payload,s.captured_at FROM holoo_operational_runs r
        JOIN holoo_financial_snapshots s ON s.id=r.snapshot_id
        WHERE r.receipt->>'status'='completed' ORDER BY r.snapshot_id DESC LIMIT 1''')).mappings().first()
    if not row:
        raise HTTPException(409, 'نسخهٔ محلیِ کامل و همگام‌شدهٔ هلو موجود نیست؛ دریافت اطلاعات را بررسی کنید.')
    feed = row['payload'].get('sources', {}).get('customers', {})
    if not feed.get('ok') or not feed.get('complete') or not isinstance(feed.get('rows'), list):
        raise HTTPException(409, 'فهرست طرف حساب‌های نسخهٔ محلی کامل نیست؛ واردسازی انجام نشد.')
    codes = []
    for item in feed['rows']:
        value = item.get('ErpCode')
        if value is None or isinstance(value, bool) or not str(value).strip():
            raise HTTPException(409, 'شناسهٔ طرف حساب در نسخهٔ محلی معتبر نیست.')
        codes.append(str(value).strip())
    if len(codes) != len(set(codes)):
        raise HTTPException(409, 'شناسهٔ تکراری در منبع طرف حساب‌ها وجود دارد؛ واردسازی متوقف شد.')
    local = {r['id']: dict(r) for r in conn.execute(text('SELECT id,name,code,to_jsonb(c) AS fields FROM customers c')).mappings()}
    mappings = [dict(r) for r in conn.execute(text("SELECT local_id,holoo_erp_code FROM holoo_entity_mappings WHERE entity_type='customer'")).mappings()]
    counts = Counter(str(r['holoo_erp_code']) for r in mappings)
    by_code = {str(r['holoo_erp_code']): r['local_id'] for r in mappings}
    candidates = []
    for code in codes:
        customer = local.get(by_code.get(code))
        if counts[code] != 1 or not customer:
            raise HTTPException(409, 'نگاشت یکتای تمام طرف حساب‌های هلو به مشتری محلی کامل نیست؛ هیچ رکوردی ساخته نشد.')
        if not str(customer['name'] or '').strip() or len(customer['name']) > 200:
            raise HTTPException(409, 'نام یکی از طرف حساب‌ها خالی یا بیش از ظرفیت دفتر پایگاه است؛ ابتدا نام را اصلاح کنید.')
        fields = customer['fields']
        if len(str(fields.get('city') or '')) > 100 or len(str(fields.get('phone') or '')) > 40:
            raise HTTPException(409, 'شهر یا تلفن یکی از مشتری‌ها نیازمند اصلاح است؛ واردسازی انجام نشد.')
        candidates.append({**customer, 'holoo_erp_code': code})
    return row, candidates


def _existing_link(conn, customer_id):
    links = [dict(r) for r in conn.execute(text('''SELECT base_source,base_id FROM (
        SELECT DISTINCT ON(base_source,base_id) base_source,base_id,payload
        FROM base_coach_profiles ORDER BY base_source,base_id,revision DESC) p
        WHERE payload->>'customer_id'=:c'''), {'c': str(customer_id)}).mappings()]
    if len(links) > 1:
        raise HTTPException(409, 'یک مشتری به چند پایگاه پیوند دارد؛ ابتدا پیوندهای صریح را اصلاح کنید.')
    if not links:
        return None
    link = links[0]
    if link['base_source'] not in BASES or not conn.execute(text(f"SELECT 1 FROM {link['base_source']} WHERE id=:id"), {'id': link['base_id']}).first():
        raise HTTPException(409, 'پایگاهِ پیوند موجود حذف یا نامعتبر شده است؛ بازبینی مدیر لازم است.')
    return link


def preview_import(conn, *, source=None):
    snapshot, candidates = source if source is not None else _source(conn)
    registered = {r['customer_id']: dict(r) for r in conn.execute(text('SELECT * FROM holoo_customer_bases')).mappings()}
    existing = new = reuse = 0
    for customer in candidates:
        entry = registered.get(customer['id'])
        if entry:
            if entry['holoo_erp_code'] != customer['holoo_erp_code']:
                raise HTTPException(409, 'شناسهٔ هلو برای پایگاه قبلی تغییر کرده؛ واردسازی خودکار مجاز نیست.')
            if not conn.execute(text(f"SELECT 1 FROM {entry['base_source']} WHERE id=:id"), {'id': entry['base_id']}).first():
                raise HTTPException(409, 'پایگاه ثبت‌شدهٔ قبلی حذف شده؛ بازبینی مدیر لازم است.')
            existing += 1
        elif _existing_link(conn, customer['id']):
            reuse += 1
        else:
            new += 1
    return {'snapshot_id': snapshot['id'], 'captured_at': snapshot['captured_at'], 'source_customers': len(candidates),
            'already_registered': existing, 'reuse_explicit_links': reuse, 'new_bases': new,
            'skipped': 0, 'skipped_reasons': [], 'local_only': True, 'holoo_writes': False,
            'classification': 'unknown', 'portfolio_assigned': False}


def import_customers(conn, snapshot_id, actor_id):
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('base-registry:holoo-customers',0))"))
    source = _source(conn)
    receipt = preview_import(conn, source=source)
    if receipt['snapshot_id'] != snapshot_id:
        raise HTTPException(409, 'نسخهٔ محلی تغییر کرده؛ پیش‌نمایش را دوباره دریافت و تأیید کنید.')
    _, candidates = source
    for customer in candidates:
        ident = customer['id']
        conn.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key': f'coach-customer:{ident}'})
        old = conn.execute(text('SELECT 1 FROM holoo_customer_bases WHERE customer_id=:id'), {'id': ident}).first()
        if old:
            continue
        link = _existing_link(conn, ident)
        if not link:
            fields = customer['fields']
            base_id = conn.execute(text('''INSERT INTO kerman_bases_manual(name,city,address,phone,type)
                VALUES(:name,:city,:address,:phone,'holoo_counterparty') RETURNING id'''),
                {'name': customer['name'], 'city': fields.get('city') or None,
                 'address': fields.get('address') or None, 'phone': fields.get('phone') or None}).scalar_one()
            link = {'base_source': 'kerman_bases_manual', 'base_id': base_id}
            payload = {'customer_id': ident, 'grade': 'unknown', 'monthly_capacity': None,
                       'source_note': f"واردسازی صریح مدیر از مشتری محلی و نگاشت یکتای هلو؛ نسخهٔ {snapshot_id}. نوع، موقعیت، استان و مسئول تأیید نشده‌اند."}
            conn.execute(text('''INSERT INTO base_coach_profiles(base_source,base_id,revision,payload,created_by)
                VALUES(:s,:b,1,CAST(:p AS JSONB),:u)'''),
                {'s': link['base_source'], 'b': link['base_id'], 'p': json.dumps(payload, ensure_ascii=False), 'u': actor_id})
        conn.execute(text('''INSERT INTO holoo_customer_bases(customer_id,holoo_erp_code,base_source,base_id,snapshot_id,imported_by)
            VALUES(:c,:e,:s,:b,:snap,:u)'''), {'c': ident, 'e': customer['holoo_erp_code'],
                's': link['base_source'], 'b': link['base_id'], 'snap': snapshot_id, 'u': actor_id})
    return {**receipt, 'created_bases': receipt['new_bases'], 'registered_links': receipt['new_bases'] + receipt['reuse_explicit_links']}
