"""Collect public business-map leads, never insert customers or submit to Holoo."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ENDPOINT='https://overpass-api.de/api/interpreter'
QUERY='''[out:json][timeout:45];
(area["boundary"="administrative"]["admin_level"="4"]["name:en"="Kerman"];
 area["boundary"="administrative"]["admin_level"="4"]["name:en"="Kerman Province"];)->.region;
(nwr["amenity"="pharmacy"](area.region);nwr["shop"="cosmetics"](area.region);nwr["shop"="perfumery"](area.region););
out center tags;'''


def normalize_elements(elements):
    records=[]
    seen=set()
    for entry in elements:
        tags=entry.get('tags',{})
        if tags.get('amenity')=='pharmacy':
            category='pharmacy'
        elif tags.get('shop') in {'cosmetics','perfumery'}:
            category='cosmetics'
        else:
            continue
        identity=(entry.get('type'),entry.get('id'))
        if identity in seen or identity[0] not in {'node','way','relation'} or not isinstance(identity[1],int):
            continue
        seen.add(identity)
        center=entry.get('center') or entry
        records.append({'source_id':f'{identity[0]}/{identity[1]}',
            'source_url':f'https://www.openstreetmap.org/{identity[0]}/{identity[1]}',
            'name':tags.get('name:fa') or tags.get('name') or tags.get('name:en') or None,
            'category':category,'city':tags.get('addr:city'),'street':tags.get('addr:street'),
            'latitude':center.get('lat'),'longitude':center.get('lon'),
            'address':tags.get('addr:full') or ' '.join(str(tags.get(k) or '') for k in ('addr:city','addr:street','addr:housenumber')).strip() or None,
            'phone':tags.get('contact:phone') or tags.get('phone'),
            'review_status':'unverified','customer_id':None})
    return records


def discover():
    response=requests.post(ENDPOINT,data={'data':QUERY},headers={'User-Agent':'KiaradBusinessDiscovery/1.0 (public business coverage review)'},timeout=(10,55))
    response.raise_for_status()
    body=response.json()
    if body.get('remark'):
        raise RuntimeError('Map provider reported an incomplete or failed query')
    if not isinstance(body.get('elements'),list):
        raise RuntimeError('Invalid map response')
    return {'source':'OpenStreetMap / Overpass','source_url':ENDPOINT,'query':QUERY,
            'license_url':'https://www.openstreetmap.org/copyright',
            'observed_at':datetime.now(timezone.utc).isoformat(),
            'coverage':'Mapped pharmacies, cosmetics and perfumery shops in the requested province boundary; not an official complete register',
            'items':normalize_elements(body['elements'])}


if __name__=='__main__':
    data=discover()
    folder=Path(__file__).parent/'data'/'public-prospects'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'path':str(path),'unverified_leads':len(data['items']),'inserted_customers':0}))
