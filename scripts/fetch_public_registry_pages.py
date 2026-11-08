"""One bounded public read per verified source. No login or business writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/public-prospects/reference-candidates'
SOURCES=[('kmu-supervised-pharmacies','https://vfd.kmu.ac.ir/fa/page/59329/لیست-داروخانه-های-تحت-نظارت'),
         ('kmu-distributors','https://vfd.kmu.ac.ir/fa/page/53915/شرکت-های-پخش-سراسری-دارو'),
         ('my-sales-points','https://my.co.ir/my-store-point/')]


def fetch(item):
    name,url=item;result={'source_name':name,'source_url':url,'business_writes':False}
    try:
        with requests.get(url,timeout=(8,30),stream=True) as response:
            result['http_status']=response.status_code;response.raise_for_status()
            chunks=[];length=0
            for chunk in response.iter_content(65536):
                length+=len(chunk)
                if length>8*1024*1024:raise ValueError('source_too_large')
                chunks.append(chunk)
            content=b''.join(chunks)
            if b'<html' not in content.lower() and b'<!doctype html' not in content.lower():raise ValueError('not_html')
            path=FOLDER/(name+'.html');path.write_bytes(content)
            result.update(downloaded=True,bytes=length,file=str(path.relative_to(ROOT)))
    except Exception as error:result.update(downloaded=False,error_type=type(error).__name__)
    return result


if __name__=='__main__':
    FOLDER.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:items=list(pool.map(fetch,SOURCES))
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'sources':items}
    (ROOT/'audit-2026-10-27/public-registry-pages.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report))
