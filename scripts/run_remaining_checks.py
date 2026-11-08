"""Coverage gaps: isolated schema upgrades and previously ungrouped unit checks."""
import os
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
os.environ['KIARAD_TEST_TARGET_SCHEMA_DB'] = '1'
os.environ['KIARAD_TEST_INTEGRATION_DB'] = '1'
from sqlalchemy import create_engine
import db
db.engine = create_engine(db.engine.url, connect_args={
    'options': '-c search_path=pg_temp -c statement_timeout=15000 -c lock_timeout=3000'})
modules = ['test_notifications', 'test_target_schema', 'test_integration_schema_upgrade',
           'test_personal_campaigns', 'test_public_prospects', 'test_operational_readiness']
suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
with patch('requests.sessions.Session.request', side_effect=AssertionError('External HTTP blocked')):
    result = unittest.TextTestRunner(verbosity=2).run(suite)
report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'modules': modules,
          'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'passed': result.wasSuccessful() and not result.skipped,
          'temporary_schema_only': True, 'external_http': False}
folder = ROOT / 'audit-2026-10-24'
folder.mkdir(exist_ok=True)
(folder / 'remaining-checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
raise SystemExit(not report['passed'])
