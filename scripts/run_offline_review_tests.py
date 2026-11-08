"""Offline subset only; exclusions are explicit, full release suite stays required."""
import json
import os
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('HOLO_API_URL', 'http://127.0.0.1:9')
# Never inherit opt-in DB write suites into the offline runner.
for name in list(os.environ):
 if name.startswith('KIARAD_TEST_') and name.endswith('_DB'): os.environ.pop(name)
EXCLUDED_MODULES = {'test_assistant_verified', 'test_dashboard_read_smoke', 'test_new_workflows_read_smoke', 'test_role_access_smoke'}
EXCLUDED_TESTS = {
 'test_treasury_excel.ExcelRoleTests.test_personnel_cannot_read_preview_or_commit_finance': 'Needs PostgreSQL role-permission lookup',
}
if not (ROOT / 'migrations/0001_baseline.sql').is_file():
 EXCLUDED_TESTS['test_migration_files.MigrationFilesTests.test_release_contains_ordered_migration_payload'] = 'Missing SQL payload in uploaded archive'
def flatten(suite):
 for item in suite:
  if isinstance(item, unittest.TestSuite): yield from flatten(item)
  else: yield item

def main():
 selected, excluded = [], []
 for test in flatten(unittest.defaultTestLoader.discover(str(ROOT / 'tests'))):
  name = test.id()
  reason = EXCLUDED_TESTS.get(name) or ('Needs live API/PostgreSQL' if name.split('.')[0] in EXCLUDED_MODULES else None)
  if reason: excluded.append({'test': name, 'reason': reason})
  else: selected.append(test)
 result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
 print(json.dumps({'scope': 'offline subset only', 'run': result.testsRun, 'skipped': len(result.skipped),
  'failures': len(result.failures), 'errors': len(result.errors), 'excluded_live_tests': excluded}, ensure_ascii=False))
 return 0 if result.wasSuccessful() else 1
if __name__ == '__main__': raise SystemExit(main())
