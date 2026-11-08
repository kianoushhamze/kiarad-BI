"""Read-only source rows and possible matches; never imports customers."""
from collections import defaultdict
from pathlib import Path
import json
from base_registry import normalize_search,matches_search

DATA_FILE=Path(__file__).resolve().parent/'data/public-prospects/registry-review.json'


def identity_name(value):
    return normalize_search(value).replace('داروخانه','').replace(' ','')


def telephone(value):
    digits=''.join(c for c in normalize_search(value) if c.isascii() and c.isdigit())
    if digits.startswith('0098') and len(digits)==14:
        digits=digits[4:]
    elif digits.startswith('98') and len(digits)==12:
        digits=digits[2:]
    elif digits.startswith('0') and len(digits)==11:
        digits=digits[1:]
    return digits if len(digits)==10 else ''


def review_registry(dataset,customers,base_links,q='',batch='',offset=0,limit=20):
    by_name=defaultdict(list);by_phone=defaultdict(list)
    for customer in customers:
        name=identity_name(customer.get('name'));city=normalize_search(customer.get('city')).replace(' ','')
        if name and city:by_name[(name,city)].append(customer)
        phone=telephone(customer.get('phone'))
        if phone:by_phone[phone].append(customer)
    results=[];with_candidates=0
    for record in dataset['items']:
        candidates={};name=identity_name(record.get('name'));city=normalize_search(record.get('city')).replace(' ','')
        for customer in by_name.get((name,city),[]):
            candidates[customer['id']]={'customer_id':customer['id'],'customer_name':customer['name'],'basis':'same_name_and_city'}
        phone=telephone(record.get('phone'))
        if phone:
            for customer in by_phone.get(phone,[]):
                candidates[customer['id']]={'customer_id':customer['id'],'customer_name':customer['name'],'basis':'same_full_phone'}
        for ident,candidate in candidates.items():candidate['base']=base_links.get(ident)
        if candidates:with_candidates+=1
        if (batch and record['batch_id']!=batch) or not matches_search(q,record.get('name'),record.get('city'),record.get('address'),record.get('gln'),record.get('phone')):continue
        results.append({**record,'possible_matches':list(candidates.values())[:5],'possible_matches_count':len(candidates),'identity_confirmed':False})
    return {'observed_at':dataset['observed_at'],'notice':dataset['notice'],'batches':dataset['batches'],
            'total_source_rows':len(dataset['items']),'rows_with_possible_matches':with_candidates,
            'total_matches':len(results),'offset':offset,'limit':limit,'items':results[offset:offset+limit],
            'automatic_customer_import':False,'province_coverage_percent':None}


def load_registry():
    if not DATA_FILE.is_file():return None
    if DATA_FILE.stat().st_size>8*1024*1024:raise ValueError('registry_file_too_large')
    value=json.loads(DATA_FILE.read_text(encoding='utf-8'))
    if not isinstance(value.get('items'),list) or not isinstance(value.get('batches'),list):raise ValueError('invalid_registry')
    return value
