"""Run isolated SQL regressions on an explicitly disposable PostgreSQL database.

Never enables the live API suites. Each group runs in a fresh process so opt-in
flags and engine monkeypatches cannot leak between groups.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.getenv('KIARAD_REVIEW_DISPOSABLE_DB') != '1':
        print('Set KIARAD_REVIEW_DISPOSABLE_DB=1 only for a disposable test database.', file=sys.stderr)
        return 2
    source = (ROOT / 'scripts/run_full_test_suite.ps1').read_text(encoding='utf-8-sig')
    groups = re.findall(r'File = "([^"]+)"; Flag = "([^"]+)"', source)
    if not groups:
        raise RuntimeError('database_test_groups_missing')
    fallbacks = (
        ('test_site_cms_regressions.py', 'KIARAD_TEST_CMS_DB'),
        ('test_marketplace_feeds_db.py', 'KIARAD_TEST_MARKETPLACE_FEEDS_DB'),
        ('test_crm_schema.py', 'KIARAD_TEST_CRM_SCHEMA_DB'),
    )
    for filename, flag in fallbacks:
        if not any(name == filename for name, _ in groups):
            groups.append((filename, flag))
    results = []
    for filename, flag in groups:
        env = {k: v for k, v in os.environ.items() if not (k.startswith('KIARAD_TEST_') and k.endswith('_DB'))}
        env.update({flag: '1', 'PGOPTIONS': '-c search_path=pg_temp -c statement_timeout=30000 -c lock_timeout=5000',
                    'HOLO_API_URL': 'http://127.0.0.1:9', 'HOLO_AUTO_REFRESH_ENABLED': '0',
                    'KIARAD_AUTOMATIONS_DISABLED': '1'})
        result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', filename, '-v'],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        match = re.search(r'Ran (\d+) tests?', result.stderr)
        results.append({'file': filename, 'tests': int(match[1]) if match else None, 'exit_code': result.returncode})
    print(json.dumps({'scope': 'disposable PostgreSQL groups; not company acceptance', 'groups': results,
                      'passed': all(row['exit_code'] == 0 for row in results)}))
    return int(any(row['exit_code'] for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
