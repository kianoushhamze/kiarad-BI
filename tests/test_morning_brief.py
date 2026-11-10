"""Offline unit tests for morning_brief (no DB needed)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from morning_brief import parse_sync_line, sync_health, MAX_SYNC_LAG_HOURS


def test_completed_line():
    line = '2026-11-10T21:08:00+03:30 {"snapshot": 1024, "status": "completed", "sales": 780}'
    e = parse_sync_line(line)
    assert e is not None
    assert e['status'] == 'completed'
    assert e['snapshot'] == 1024
    assert e['at_dt'] is not None


def test_stale_line_without_json_status():
    line = '2026-11-09T22:24:00+03:30 {"snapshot": null, "error": "stale_source"}'
    e = parse_sync_line(line)
    assert e['status'] == 'stale_source'
    assert e['snapshot'] is None


def test_garbage_line_never_crashes():
    for line in ('', 'not json at all', '{"x": 1}', '[]', 'null'):
        e = parse_sync_line(line)
        assert e is None or isinstance(e, dict)


def test_sync_health_completed_recent():
    now = datetime.now().astimezone()
    recent = (now - timedelta(hours=2)).isoformat(timespec='seconds')
    log = Path(__file__).parent / '_tmp_sync_test.log'
    log.write_text(recent + ' {"status": "completed"}\n', encoding='utf-8')
    try:
        with patch('morning_brief.SYNC_LOG', log):
            h = sync_health()
        assert h['healthy'] is True
        assert h['status'] == 'completed'
        assert h['hours_ago'] is not None and h['hours_ago'] < 5
    finally:
        log.unlink(missing_ok=True)


def test_sync_health_old_becomes_unhealthy():
    old = (datetime.now().astimezone() - timedelta(hours=MAX_SYNC_LAG_HOURS + 5)).isoformat(timespec='seconds')
    log = Path(__file__).parent / '_tmp_sync_test2.log'
    log.write_text(old + ' {"status": "completed"}\n', encoding='utf-8')
    try:
        with patch('morning_brief.SYNC_LOG', log):
            h = sync_health()
        assert h['healthy'] is False
    finally:
        log.unlink(missing_ok=True)


def test_sync_health_missing_file():
    with patch('morning_brief.SYNC_LOG', Path('/nonexistent/nope.log')):
        h = sync_health()
    assert h['healthy'] is False
    assert h['status'] == 'missing'


if __name__ == '__main__':
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith('test_')}.items()):
        fn()
        print('OK', name)
    print('ALL PASS')
