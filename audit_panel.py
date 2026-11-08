"""Current-run evidence: safe HTTP reads and isolated regression tests."""
import io
import json
import os
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import requests
from sqlalchemy import text

ROOT = Path(__file__).parent
OUT = ROOT / 'audit-2026-10-17' / 'base-proposals'


def main():
    load_dotenv(ROOT / '.env')
    from db import engine
    from operations import create_token
    OUT.mkdir(parents=True,exist_ok=True)
    for flag in ('TASK_WORKFLOW','VISIT_WORKFLOW','VOICE_WORKFLOW','PERSONNEL','VISIT_COVERAGE','INTEGRATION','BASE_PROPOSALS'):
        os.environ[f'KIARAD_TEST_{flag}_DB']='1'
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    (OUT/'regression-tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    with engine.connect() as conn:
        user = conn.execute(text("SELECT id,role,password_version FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().first()
        counts = {table:conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar() for table in
                  ('users','salespersons','customers','products','sales','tasks','daily_reports','voice_report_entries','base_checkins')}
    headers = {'Authorization':'Bearer '+create_token(dict(user))}
    from tests.test_dashboard_read_smoke import READ_PATHS
    extra = ['/integrations','/catalog/sync-runs','/operations/locations/latest','/operations/proformas/exports',
             '/operations/proformas/holoo-queue','/api/compensation/bases','/api/compensation/base-checkins',
             '/api/compensation/visit-routes','/api/compensation/payroll-people','/operations/voice-reports',
             '/operations/speech-readiness','/tasks/assignees','/notifications','/catalog-files',
             '/api/compensation/visit-coverage','/api/compensation/base-proposals']
    def probe(item):
        kind,path=item
        origin='http://127.0.0.1:3000' if kind=='page' else 'http://127.0.0.1:8000'
        try:
            response=requests.get(origin+path,headers=headers if kind=='api' else {},timeout=15)
            return {'kind':kind,'path':path,'status':response.status_code,'milliseconds':round(response.elapsed.total_seconds()*1000)}
        except requests.RequestException:
            return {'kind':kind,'path':path,'status':None}
    pages=['/'+str(path.parent.relative_to(ROOT/'kiarad-dashboard'/'app')).replace('\\','/').replace('.','')
           for path in (ROOT/'kiarad-dashboard'/'app').rglob('page.tsx')]
    jobs=[('page',path) for path in sorted(set(pages+['/newdash_online.html']))]
    jobs += [('api',path) for path in dict.fromkeys([*READ_PATHS,*extra])]
    with ThreadPoolExecutor(max_workers=5) as pool:
        checks=list(pool.map(probe,jobs))
    anonymous=[]
    for path in ['/auth/me','/users','/tasks','/operations/voice-reports','/api/compensation/base-checkins']:
        anonymous.append({'path':path,'status':requests.get('http://127.0.0.1:8000'+path,timeout=10).status_code})
    evidence={'tests':{'run':result.testsRun,'successful_log_entries':sum(line.endswith(' ... ok') for line in stream.getvalue().splitlines()),
                      'failures':len(result.failures),'errors':len(result.errors),'skipped_events':len(result.skipped)},
              'checks':checks,'anonymous':anonymous,'counts':counts,
              'limitations':['No actual staff login exists','No microphone or GPS permission granted','No external financial writes','Read responses do not prove successful form submissions']}
    (OUT/'technical-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=True))


if __name__=='__main__':
    main()
