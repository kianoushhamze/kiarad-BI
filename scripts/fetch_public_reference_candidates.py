"""One normal TLS request per public PDF candidate; never imports business data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data'/'public-prospects'/'reference-candidates'
SOURCES=[('kmu-night-pharmacies','https://pr.kmu.ac.ir/Images/Download/31467/1_1.pdf'),
         ('manufacturer-kerman','https://arm-strong.co/wp-content/uploads/2026/06/Kerman.pdf')]


def fetch(item):
    name,url=item;result={'source_url':url,'source_name':name,'imported_customers':0,'official_complete_register':False}
    try:
        response=requests.get(url,timeout=(8,25),stream=True)
        result['status']=response.status_code
        response.raise_for_status()
        chunks=[];length=0
        for chunk in response.iter_content(65536):
            chunks.append(chunk);length+=len(chunk)
            if length>20*1024*1024:raise ValueError('too_large')
        content=b''.join(chunks)
        if not content.startswith(b'%PDF-'):raise ValueError('not_pdf')
        path=FOLDER/(name+'.pdf');path.write_bytes(content)
        result.update(downloaded=True,bytes=length,path=str(path.relative_to(ROOT)))
    except Exception as error:result.update(downloaded=False,error_type=type(error).__name__)
    return result


if __name__=='__main__':
    FOLDER.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(fetch,SOURCES))
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'sources':results,'scope':'Public candidates only, not a verified province directory'}
    (ROOT/'audit-2026-10-27'/'public-reference-candidates.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
