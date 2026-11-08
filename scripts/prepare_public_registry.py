"""Read downloaded workbooks/HTML with bundled libraries; preserve provenance.

Creates a review dataset only. Never connects to the company database.
"""
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
import sys
import openpyxl
from lxml import html
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from public_directory_extract import compact


def clean(value):
    if value is None:return ''
    if isinstance(value,float) and value.is_integer():return str(int(value))
    return re.sub(r'\s+',' ',str(value)).strip()


def main():
    sources=json.loads((ROOT/'audit-2026-10-27/official-workbooks.json').read_text(encoding='utf-8'))['sources']
    records=[];batches=[];seen_content={};superseded=[]
    for source in sources:
        if not source['downloaded']:continue
        if source['source_page']=='kmu-distributors' and '1404' in source['title']:
            superseded.append({'title':source['title'],'file':source['file'],'reason':'نسخهٔ مرداد ۱۴۰۵ از همین ناشر دریافت شده است.'})
            continue
        workbook=openpyxl.load_workbook(ROOT/source['file'],read_only=True,data_only=True,keep_links=False)
        try:
            for sheet in workbook:
                rows=list(sheet.iter_rows(values_only=True))
                if 'نام  داروخانه' in rows[0]:
                    fields={'name':1,'phone':5,'city':7,'address':9,'hours_label':2,'institution_type':3};header=0;kind='pharmacy'
                elif 'نام داروخانه' in rows[0]:
                    fields={'name':0,'gln':1,'address':2,'city':3,'county':4,'institution_type':5};header=0;kind='pharmacy'
                elif sheet.title=='بیمارستان ها':
                    fields={'name':1,'gln':2,'address':3,'institution_type':4};header=0;kind='hospital_identity'
                elif len(rows)>1 and clean(rows[1][0])=='نام':
                    fields={'name':0,'phone':1,'address':8};header=1;kind='distributor'
                else:raise ValueError('unrecognized_workbook_header')
                prepared=[(index+1,{key:clean(row[column]) for key,column in fields.items()}) for index,row in enumerate(rows) if index>header and clean(row[fields['name']])]
                digest=hashlib.sha256(json.dumps([value for _,value in prepared],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
                if digest in seen_content:
                    seen_content[digest]['alternate_sources'].append({'url':source['source_url'],'title':source['title']})
                    continue
                batch_id=Path(source['file']).stem+':'+sheet.title
                batch={'id':batch_id,'title':source['title']+' · '+sheet.title,'kind':kind,'source_url':source['source_url'],
                       'file':source['file'],'sheet':sheet.title,'source_file_modified':str(workbook.properties.modified),
                       'records':len(prepared),'alternate_sources':[],'current_activity_verified':False}
                seen_content[digest]=batch;batches.append(batch)
                for row_number,value in prepared:
                    records.append({'source_id':batch_id+':'+str(row_number),'batch_id':batch_id,'source_row':row_number,
                                    'category':kind,**value,'review_status':'unverified','latitude':None,'longitude':None})
        finally:workbook.close()
    path=ROOT/'data/public-prospects/reference-candidates/my-sales-points.html'
    document=html.fromstring(path.read_bytes())
    rows=[[clean(cell.text_content()) for cell in row.xpath('./td')] for row in document.xpath('//table[@id="tablepress-1"]//tr')]
    starts=[i for i,row in enumerate(rows) if len(row)==3 and compact(row[0])==compact('اختیارآباد') and row[1]=='آرامیس']
    ends=[i for i,row in enumerate(rows) if len(row)==3 and row[0]=='نگار' and row[1]=='داروخانه عقیلی']
    if len(starts)!=1 or len(ends)!=1 or not 0<ends[0]-starts[0]<300:raise ValueError('ambiguous_kerman_block')
    selected=rows[starts[0]:ends[0]+1]
    batch_id='my-network-kerman'
    batches.append({'id':batch_id,'title':'شبکهٔ نقاط فروش مای؛ بخش شهرهای کرمان','kind':'sales_network',
                    'source_url':'https://my.co.ir/my-store-point/','file':str(path.relative_to(ROOT)),
                    'records':len(selected),'source_file_modified':None,'alternate_sources':[],'current_activity_verified':False})
    for index,row in enumerate(selected,starts[0]+1):
        city,name,address=row
        if not name:continue
        records.append({'source_id':batch_id+':'+str(index),'batch_id':batch_id,'source_row':index,'name':name,'city':city,
                        'address':address,'phone':'','category':'pharmacy' if 'داروخانه' in name else 'sales_point',
                        'review_status':'unverified','latitude':None,'longitude':None})
    report={'observed_at':datetime.now(timezone.utc).isoformat(),'complete_province_register':False,
            'business_writes':False,'automatic_identity_merge':False,'batches':batches,'items':records,'superseded_sources':superseded,
            'notice':'این فهرست منتشرشدهٔ منابع است؛ وجود در آن، فعالیت فعلی یا پوشش کل استان را ثابت نمی‌کند. فایل‌های داروخانه تاریخ ذخیرهٔ ۲۰۲۴ دارند؛ تطبیق مشتری فقط پیشنهادی است.'}
    target=ROOT/'data/public-prospects/registry-review.json'
    temporary=target.with_suffix('.json.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(target)
    print(json.dumps({'records':len(records),'batches':len(batches),'categories':dict(Counter(row['category'] for row in records)),
                      'duplicate_source_files_collapsed':sum(len(batch['alternate_sources']) for batch in batches),'business_writes':False}))


if __name__=='__main__':main()
