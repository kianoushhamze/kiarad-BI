"""Assistant regressions: no external HTTP, no financial or target writes."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from scripts.run_compensation_checks import SafeResult

suite=unittest.defaultTestLoader.loadTestsFromNames(['test_assistant_grounding','test_assistant_scope','test_assistant_verified'])
result=SafeResult()
with patch('requests.sessions.Session.request',side_effect=AssertionError('External traffic blocked')):
    suite.run(result)
report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'passed':result.wasSuccessful() and not result.skipped,'external_http':False,'financial_writes':False,'cases':result.cases}
path=ROOT/'audit-2026-10-20/assistant-tests.json'
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
for _,trace in result.failures+result.errors:
    print(trace)
raise SystemExit(not report['passed'])
