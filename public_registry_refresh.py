"""Refresh an allowlisted public directory without changing customer records."""
from datetime import datetime, timezone
import hashlib
import json
import threading
import requests
from html.parser import HTMLParser
from base_registry import normalize_search
from public_registry_review import DATA_FILE, load_registry

LOCK = threading.Lock()
MY_URL = 'https://my.co.ir/my-store-point/'


def parse_my(content):
    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.active = False; self.row = []; self.cell = None; self.rows = []

        def handle_starttag(self, tag, attrs):
            if tag == 'table' and dict(attrs).get('id') == 'tablepress-1':
                self.active = True
            if self.active and tag == 'tr':
                self.row = []
            if self.active and tag == 'td':
                self.cell = []
            if self.cell is not None and tag == 'br':
                self.cell.append(' ')

        def handle_data(self, data):
            if self.active and self.cell is not None:
                self.cell.append(data)

        def handle_endtag(self, tag):
            if self.active and tag == 'td' and self.cell is not None:
                self.row.append(' '.join(''.join(self.cell).split())); self.cell = None
            if self.active and tag == 'tr':
                self.rows.append(self.row)
            if tag == 'table':
                self.active = False

    parser = TableParser()
    parser.feed(content.decode('utf-8-sig'))
    rows = parser.rows
    starts = [i for i, r in enumerate(rows) if len(r) == 3 and normalize_search(r[0]).replace(' ', '') == normalize_search('اختیارآباد').replace(' ', '') and r[1] == 'آرامیس']
    ends = [i for i, r in enumerate(rows) if len(r) == 3 and r[0] == 'نگار' and r[1] == 'داروخانه عقیلی']
    if len(starts) != 1 or len(ends) != 1 or not 0 < ends[0] - starts[0] < 300:
        raise ValueError('ambiguous_province_boundary')
    result = []
    seen = set()
    for index, row in enumerate(rows[starts[0]:ends[0]+1], starts[0]+1):
        city, name, address = row
        key = tuple(normalize_search(v) for v in row)
        if not name or key in seen:
            continue
        seen.add(key)
        ident = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:24]
        result.append({'source_id': 'my-network-kerman:' + ident, 'batch_id': 'my-network-kerman',
                       'source_row': index, 'name': name, 'city': city, 'address': address, 'phone': '',
                       'category': 'pharmacy' if 'داروخانه' in name else 'sales_point',
                       'review_status': 'unverified', 'latitude': None, 'longitude': None})
    return result


def refresh_registry():
    if not LOCK.acquire(blocking=False):
        return {'status': 'busy', 'message': 'به‌روزرسانی دیگری در حال اجرا است.'}
    try:
        dataset = load_registry()
        if dataset is None:
            raise ValueError('missing_registry')
        with requests.get(MY_URL, timeout=(8, 30), stream=True) as response:
            response.raise_for_status()
            parts = []; size = 0
            for part in response.iter_content(65536):
                size += len(part)
                if size > 8 * 1024 * 1024:
                    raise ValueError('source_too_large')
                parts.append(part)
        items = parse_my(b''.join(parts))
        if not items:
            raise ValueError('empty_source')
        stamp = datetime.now(timezone.utc).isoformat()
        old = [r for r in dataset['items'] if r['batch_id'] == 'my-network-kerman']
        # Only replace this source. Manual customers and other publishers are untouched.
        dataset['items'] = [r for r in dataset['items'] if r['batch_id'] != 'my-network-kerman'] + items
        for batch in dataset['batches']:
            if batch['id'] == 'my-network-kerman':
                batch.update(records=len(items), retrieved_at=stamp, current_activity_verified=False)
        dataset['last_refresh'] = {'checked_at': stamp, 'source_url': MY_URL, 'status': 'updated',
                                   'previous_rows': len(old), 'rows': len(items)}
        temporary = DATA_FILE.with_suffix('.refresh.tmp')
        temporary.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(DATA_FILE)
        return {'status': 'updated', 'rows': len(items), 'checked_at': stamp,
                'message': 'شبکهٔ فروش مای تازه شد؛ سایر منابع تاریخ دریافت مستقل دارند. مشتری اصلی تغییر نکرد.'}
    finally:
        LOCK.release()
