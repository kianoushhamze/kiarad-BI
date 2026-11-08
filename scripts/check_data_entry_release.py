"""Read-only release checks, plus one explicitly authorized vendor profile probe.

No valid intake/commit requests or financial/marketplace mutations are made.
Tokens stay in memory; reports contain no user names or business amounts.
"""
from pathlib import Path
import json
import sys
from io import BytesIO

import openpyxl
import requests
from dotenv import load_dotenv
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')
from db import engine
from operations import create_token


def main():
    session = requests.Session()
    session.trust_env = False
    cases = []
    def check(name, value):
        cases.append({'name': name, 'passed': bool(value)})
    with engine.connect() as conn:
        users = [dict(row) for row in conn.execute(text(
            'SELECT id,role,salesperson_id,password_version FROM users WHERE is_active=1 ORDER BY id'
        )).mappings()]
        before = conn.execute(text('SELECT COUNT(*) FROM data_entry_batches')).scalar()
    manager = next(user for user in users if user['role'] == 'ceo')
    headers = {'Authorization': 'Bearer ' + create_token(manager)}
    for origin, prefix in [('http://127.0.0.1:8000', ''), ('http://127.0.0.1:3000', '/api'),
                           ('https://kiarad.taile287ae.ts.net', '/api')]:
        base = origin + prefix
        response = session.get(base + '/data-entry/schema', headers=headers, timeout=30)
        check(origin + '-schema', response.status_code == 200 and
              {row['id'] for row in response.json().get('entities', [])} == {'products', 'customers', 'targets', 'batches'})
        for entity in ['products', 'customers', 'targets', 'batches']:
            response = session.get(base + f'/data-entry/{entity}/template', headers=headers, timeout=30)
            valid = False
            if response.status_code == 200:
                book = openpyxl.load_workbook(BytesIO(response.content), read_only=True)
                valid = bool(next(book.active.values))
                book.close()
            check(origin + '-' + entity + '-template', valid)
            response = session.post(base + f'/data-entry/{entity}/manual/preview', headers=headers,
                                    json={'unit': 'TOMAN', 'rows': []}, timeout=30)
            check(origin + '-' + entity + '-empty-input-rejected', response.status_code == 422)
        for kind in ['balances', 'checks', 'purchases', 'sales', 'purchase_returns', 'sales_returns', 'monthly', 'inventory', 'general']:
            response = session.get(base + '/treasury/excel/manual-schema', params={'kind': kind}, headers=headers, timeout=30)
            check(origin + '-' + kind + '-manual-finance-schema', response.status_code == 200 and bool(response.json().get('headers')))
        for entity in ['products', 'customers']:
            response = session.get(base + f'/data-entry/{entity}/holoo-refresh', headers=headers, timeout=30)
            check(origin + '-' + entity + '-read-source-status', response.status_code == 200 and
                  set(response.json()) <= {'status', 'finished_at', 'sources', 'erp_writes', 'manual_fields_preserved'})
        check(origin + '-anonymous-denied', session.get(base + '/data-entry/schema', timeout=20).status_code == 401)
        for user in users:
            if user['role'] not in {'visitor', 'salesperson'}:
                continue
            staff_headers = {'Authorization': 'Bearer ' + create_token(user)}
            for path in ['/data-entry/schema', '/data-entry/products/template', '/treasury/excel/manual-schema?kind=checks']:
                check(origin + f'-staff-{user["id"]}-denied-' + path,
                      session.get(base + path, headers=staff_headers, timeout=20).status_code == 403)
        response = session.get(base + '/catalog/products', headers=headers, timeout=30)
        data = response.json().get('items') if response.status_code == 200 else None
        check(origin + '-manual-authority-visible', isinstance(data, list) and bool(data) and all('manual_fields' in row for row in data))
    for origin in ['http://127.0.0.1:3000', 'https://kiarad.taile287ae.ts.net']:
        response = session.get(origin + '/data-entry', timeout=30)
        check(origin + '-entry-page', response.status_code == 200 and '<iframe' not in response.text.lower())
    # A browser login does not refresh the separate API credential. Only read profile.
    response = session.post('http://127.0.0.1:8000/integrations/digikala/check', headers=headers, timeout=90)
    check('vendor-probe-receipt', response.status_code == 200)
    vendor = response.json() if response.status_code == 200 else {'status': 'probe_failed', 'http_status': response.status_code}
    safe_vendor = {key: vendor.get(key) for key in ['status', 'http_status', 'checked_at', 'read_only']}
    with engine.connect() as conn:
        check('no-intake-records-created', conn.execute(text('SELECT COUNT(*) FROM data_entry_batches')).scalar() == before)
    report = {'checks': len(cases), 'failures': sum(not row['passed'] for row in cases), 'cases': cases,
              'digikala': safe_vendor, 'financial_writes': False, 'holoo_writes': False,
              'marketplace_mutations': False, 'browser_visual_review': 'not_verified_browser_disabled'}
    (ROOT / 'audit-2026-10-21/data-entry-live.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'cases'}))
    for row in cases:
        if not row['passed']:
            print(json.dumps(row))
    return int(report['failures'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
