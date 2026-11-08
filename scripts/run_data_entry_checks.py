"""Run new intake checks with pg_temp-only database access and HTTP blocked."""
import os,sys,json,unittest
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
os.environ['KIARAD_TEST_TREASURY_DB']='1'
import db
from sqlalchemy import create_engine
from scripts.run_compensation_checks import SafeResult
old=db.engine
isolated=create_engine(old.url,connect_args={'options':'-c search_path=pg_temp -c statement_timeout=15000 -c lock_timeout=3000','connect_timeout':5})
db.engine=isolated
try:
    with isolated.connect() as conn:assert conn.exec_driver_sql('SHOW search_path').scalar()=='pg_temp'
    suite=unittest.defaultTestLoader.loadTestsFromNames(['test_data_entry','test_holoo_operational_sync','test_treasury_excel'])
    result=SafeResult()
    with patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP blocked')):
        suite.run(result)
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful() and not result.skipped,
        'temporary_tables_only':True,'external_http':False,'erp_writes':False,'cases':result.cases}
    (ROOT/'audit-2026-10-20/data-entry-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='cases'}))
    for _,trace in result.failures+result.errors:print(trace)
finally:
    db.engine=old;isolated.dispose()
raise SystemExit(not report['passed'])
