"""Bounded public-source refresh; failures preserve the previous source rows."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import json
import threading
import requests
import openpyxl
from public_registry_refresh import LOCK, MY_URL, parse_my
from public_registry_review import DATA_FILE, load_registry

STATUS_FILE=DATA_FILE.with_name('refresh-status.json')
JOB_LOCK=threading.Lock()
VIRALIAN='https://viralian.com/fa/کرمان/'


def download(url):
    with requests.get(url,timeout=(8,25),stream=True) as response:
        response.raise_for_status()
        chunks=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>8*1024*1024:raise ValueError('source_too_large')
            chunks.append(chunk)
        return b''.join(chunks)


def viralian_rows(content):
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__();self.row=[];self.cell=None;self.rows=[]
        def handle_starttag(self,tag,attrs):
            if tag=='tr':self.row=[]
            if tag=='td':self.cell=[]
        def handle_data(self,data):
            if self.cell is not None:self.cell.append(data)
        def handle_endtag(self,tag):
            if tag=='td' and self.cell is not None:
                self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
            if tag=='tr' and self.row:self.rows.append(self.row)
    parser=Parser();parser.feed(content.decode('utf-8-sig'))
    records=[];seen=set()
    for index,row in enumerate(parser.rows,1):
        if len(row)<4 or row[0].strip().lower()!='kerman':continue
        _,name,address,phone,*_=row
        identity=hashlib.sha256(json.dumps(row[:4],ensure_ascii=False).encode()).hexdigest()[:24]
        if not name or identity in seen:continue
        seen.add(identity)
        records.append({'source_id':'viralian-kerman:'+identity,'batch_id':'viralian-kerman',
            'source_row':index,'name':name,'city':'کرمان','address':address,'phone':phone,
            'category':'pharmacy','review_status':'unverified','latitude':None,'longitude':None})
    if not records:raise ValueError('no_kerman_rows')
    return records


def workbook_rows(content,batch):
    if not content.startswith(b'PK'):raise ValueError('not_workbook')
    workbook=openpyxl.load_workbook(BytesIO(content),read_only=True,data_only=True,keep_links=False)
    try:
        sheet=workbook[batch['sheet']]
        rows=list(sheet.iter_rows(values_only=True))
        if not rows or len(rows)>20000:raise ValueError('invalid_workbook_size')
        clean=lambda value:' '.join(str(value or '').split())
        header=[clean(value) for value in rows[0]]
        if 'نام  داروخانه' in [str(v or '') for v in rows[0]]:
            fields={'name':1,'phone':5,'city':7,'address':9,'hours_label':2,'institution_type':3};start=1
        elif 'نام داروخانه' in header:
            fields={'name':0,'gln':1,'address':2,'city':3,'county':4,'institution_type':5};start=1
        elif len(rows)>1 and clean(rows[1][0])=='نام' and batch['kind']=='distributor':
            fields={'name':0,'phone':1,'address':8};start=2
        else:raise ValueError('changed_workbook_header')
        records=[]
        for index,row in enumerate(rows[start:],start+1):
            if len(row)<=max(fields.values()):continue
            values={key:clean(row[column]) for key,column in fields.items()}
            if not values['name']:continue
            identity=hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]
            records.append({'source_id':batch['id']+':'+identity,'batch_id':batch['id'],'source_row':index,
                'category':batch['kind'],**values,'review_status':'unverified','latitude':None,'longitude':None})
        if not records:raise ValueError('empty_workbook')
        return records
    finally:workbook.close()


def status():
    if STATUS_FILE.is_file():
        value=json.loads(STATUS_FILE.read_text(encoding='utf-8'))
        if value.get('status')=='running' and not JOB_LOCK.locked():
            return {**value,'status':'interrupted','message':'اجرای قبلی متوقف شده؛ می‌توانید دوباره به‌روزرسانی کنید.'}
        return value
    return {'status':'idle','sources':[]}


def write_status(value):
    temporary=STATUS_FILE.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(STATUS_FILE)


def run():
    try:
        with LOCK:
            dataset=load_registry()
            if dataset is None:raise ValueError('missing_registry')
            batches=[b for b in dataset['batches'] if b['kind'] in {'pharmacy','distributor'} and b['source_url'].startswith('https://vfd.kmu.ac.ir/Images/')]
            batches += [next(b for b in dataset['batches'] if b['id']=='my-network-kerman'),
                        {'id':'viralian-kerman','title':'داروخانه‌های معرفی‌شدهٔ کرمان در ویرالیان','kind':'pharmacy',
                         'source_url':VIRALIAN,'records':0,'source_file_modified':None,'current_activity_verified':False}]
            def fetch(batch):
                try:
                    content=download(batch['source_url'])
                    records=parse_my(content) if batch['id']=='my-network-kerman' else viralian_rows(content) if batch['id']=='viralian-kerman' else workbook_rows(content,batch)
                    return batch,records,None
                except Exception as error:return batch,None,type(error).__name__
            sources=[];updated=0
            with ThreadPoolExecutor(max_workers=3) as pool:
                for batch,records,error in pool.map(fetch,batches):
                    stamp=datetime.now(timezone.utc).isoformat()
                    sources.append({'id':batch['id'],'title':batch['title'],'source_url':batch['source_url'],
                        'checked_at':stamp,'status':'updated' if records else 'failed_preserved','error_type':error,
                        'records':len(records) if records else batch['records']})
                    if records:
                        updated+=1
                        dataset['items']=[r for r in dataset['items'] if r['batch_id']!=batch['id']]+records
                        updated_batch={**batch,'records':len(records),'retrieved_at':stamp,'current_activity_verified':False}
                        dataset['batches']=[b for b in dataset['batches'] if b['id']!=batch['id']]+[updated_batch]
            stamp=datetime.now(timezone.utc).isoformat()
            dataset['source_refresh_status']=sources
            temporary=DATA_FILE.with_suffix('.sources.tmp')
            temporary.write_text(json.dumps(dataset,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(DATA_FILE)
            write_status({'status':'completed' if updated==len(sources) else 'partial' if updated else 'failed',
                'finished_at':stamp,'sources':sources,'updated_sources':updated,'business_writes':False})
    except Exception as error:
        write_status({'status':'failed','error_type':type(error).__name__,'sources':[],'business_writes':False})
    finally:JOB_LOCK.release()


def start():
    if not JOB_LOCK.acquire(blocking=False):return status()
    try:
        write_status({'status':'running','sources':[],'started_at':datetime.now(timezone.utc).isoformat()})
        threading.Thread(target=run,daemon=True,name='public-registry-refresh').start()
    except Exception:
        JOB_LOCK.release()
        raise
    return status()
