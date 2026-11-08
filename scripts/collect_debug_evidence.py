"""Preserve current local QA receipts without database or network access."""
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audit-2026-10-25' / 'comprehensive'
SOURCES = {
    'personnel': 'audit-2026-10-18/compensation-tests-final.json',
    'treasury': 'audit-2026-10-19/treasury-tests.json',
    'data-entry': 'audit-2026-10-20/data-entry-tests.json',
    'panel': 'audit-2026-10-20/panel-repairs-tests.json',
    'assistant': 'audit-2026-10-20/assistant-tests.json',
}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, relative in SOURCES.items():
        source = ROOT / relative
        report = json.loads(source.read_text(encoding='utf-8'))
        shutil.copy2(source, OUT / (name + '.json'))
        results[name] = {key: report.get(key) for key in ('tests', 'passed', 'failures', 'errors', 'skipped')}
    summary = {'collected_at': datetime.now(timezone.utc).isoformat(), 'suites': results,
               'overlapping_suites': True, 'all_suites_passed': all(item['passed'] for item in results.values()),
               'complete_product_acceptance': False, 'receipt_collection_only': True}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary))

if __name__ == '__main__':
    main()
