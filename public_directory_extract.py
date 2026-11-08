"""Turn the observed two-column university PDF table into review-only leads."""
import re
import unicodedata

CITIES=('کرمان','زرند','ماهان','بم','بروات','رستم آباد','ریگان','فهرج','ارزوئیه','فاریاب','عنبرآباد',
        'سیرجان','بردسیر','رفسنجان','شهربابک','انار','کهنوج','جیرفت','قلعه گنج','منوجان','رودبار','بافت','رابر')


def visual_text(value):
    lines=[]
    for line in str(value or '').splitlines():
        logical=line[::-1].translate(str.maketrans({'(':')',')':'(','[':']',']':'['}))
        logical=re.sub(r'[A-Za-z0-9۰-۹٠-٩]+(?:[-./][A-Za-z0-9۰-۹٠-٩]+)*',lambda match:match[0][::-1],logical)
        lines.append(logical.strip())
    return ' '.join(lines).strip()


def compact(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value or '')).translate(str.maketrans('يىكآ','ییکا')))


def parse_university_tables(tables,source_url):
    records=[]
    for page_index,table in enumerate(tables,1):
        if not table or any(len(row)!=8 for row in table):raise ValueError('unexpected_table_layout')
        for offset in (4,0):
            current=None
            for row_index,row in enumerate(table,1):
                raw_address,raw_phone,raw_name,raw_city=row[offset:offset+4]
                name,city=visual_text(raw_name),visual_text(raw_city)
                if city in ('شهر','ر هش') or name.replace(' ','')=='داروخانه':continue
                if city and city!='-' and name and name!='-':
                    canonical=next((known for known in CITIES if compact(known)==compact(city)),None)
                    current={'source_id':f'kmu:page-{page_index}:half-{offset}:row-{row_index}',
                             'source_url':source_url,'source_page':page_index,'name':name,'city':canonical or city,
                             'category':'pharmacy','province':'کرمان','address':visual_text(raw_address),
                             'phone':str(raw_phone or '').strip(),'latitude':None,'longitude':None,
                             'review_status':'unverified','customer_id':None,
                             'issues':['source_date_unknown','pdf_text_requires_review']+([] if canonical else ['city_requires_review'])}
                    records.append(current)
                elif current and not city:
                    if name:current['name']+=' '+name
                    if raw_address:current['address']+=' '+visual_text(raw_address)
                    if raw_phone:current['phone']+=' / '+str(raw_phone).strip()
    return records
