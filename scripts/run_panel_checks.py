"""Panel regressions with mocked writes and external HTTP disabled."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
load_dotenv(ROOT/'.env')
from scripts.run_compensation_checks import SafeResult

suite=unittest.defaultTestLoader.loadTestsFromNames(['test_panel_repairs','test_catalog_upload_validation','test_assistant_grounding'])
result=SafeResult()
with patch('requests.sessions.Session.request',side_effect=AssertionError('External traffic blocked')):
    suite.run(result)
report={'tests':result.testsRun,'passed':result.wasSuccessful() and not result.skipped,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'cases':result.cases,'financial_writes':False,'external_http':False}
(ROOT/'audit-2026-10-20/panel-repairs-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in report.items() if key!='cases'}))
for _,trace in result.errors+result.failures:print(trace)
raise SystemExit(not report['passed'])
