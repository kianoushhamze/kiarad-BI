"""Download workbook links actually published on the saved university pages."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import html,json,re
from urllib.parse import urljoin
import requests
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'data/public-prospects/reference-candidates'


def collect_links():
    links={}
    for source in ('kmu-supervised-pharmacies','kmu-distributors'):
        content=(FOLDER/(source+'.html')).read_text(encoding='utf-8-sig')
        for url,title in re.findall(r'<a[^>]+href=["\x27]([^"\x27]+)["\x27][^>]*>(.*?)</a>',content,re.S):
            if not re.search(r'\.xlsx?$',url,re.I):continue
            url=urljoin('https://vfd.kmu.ac.ir/',html.unescape(url))
            if not url.startswith('https://vfd.kmu.ac.ir/Images/UserFiles/'):raise ValueError('unexpected_download_origin')
            title=html.unescape(re.sub('<[^>]+>','',title)).strip()
            if url not in links:links[url]={'source_page':source,'source_url':url,'title':title}
    return list(links.values())


def fetch(item):
    result=dict(item)
    try:
        with requests.get(item['source_url'],timeout=(8,30),stream=True) as response:
            result['http_status']=response.status_code;response.raise_for_status()
            chunks=[];length=0
            for chunk in response.iter_content(65536):
                length+=len(chunk)
                if length>20*1024*1024:raise ValueError('workbook_too_large')
                chunks.append(chunk)
            content=b''.join(chunks)
            if not content.startswith(b'PK'):raise ValueError('not_xlsx')
            import hashlib
            path=FOLDER/('official-'+hashlib.sha256(item['source_url'].encode()).hexdigest()[:12]+'.xlsx')
            path.write_bytes(content);result.update(downloaded=True,bytes=length,file=str(path.relative_to(ROOT)))
    except Exception as error:result.update(downloaded=False,error_type=type(error).__name__)
    return result


if __name__=='__main__':
    links=collect_links()
    with ThreadPoolExecutor(max_workers=2) as pool:items=list(pool.map(fetch,links))
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'sources':items,'business_writes':False}
    (ROOT/'audit-2026-10-27/official-workbooks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'files':len(items),'downloaded':sum(item['downloaded'] for item in items),'business_writes':False}))
