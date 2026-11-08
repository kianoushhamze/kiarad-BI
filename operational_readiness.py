"""Read-only local deployment checks. Never creates accounts or business records."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def probe_url(url):
    try:
        with urlopen(url, timeout=8) as response:
            return {"ok": response.status == 200, "status": response.status}
    except HTTPError as error:
        return {"ok": False, "status": error.code}
    except (URLError, TimeoutError, OSError):
        return {"ok": False, "status": None}


def assess_blockers(database, speech, services):
    blockers = []
    if not all(item.get('ok') for item in services.values()):
        blockers.append('یک یا چند سرویس محلی پاسخ سالم نمی‌دهد')
    if database.get('error'):
        blockers.append('بررسی خواندنی دیتابیس موفق نبود')
    elif not database.get('linked_field_accounts', 0):
        blockers.append('حساب فعال پرسنلِ متصل به پروفایل فروشنده موجود نیست')
    if speech.get('state') != 'loaded':
        blockers.append('تبدیل واقعی صوت هنوز تأیید نشده؛ ورود متنی مستقل در دسترس است')
    blockers.append('آزمون واقعی گوشی، میکروفن و موقعیت مکانی باید جدا انجام شود')
    return blockers


def database_snapshot(engine):
    from sqlalchemy import text
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text("SET LOCAL statement_timeout = '5s'"))
            linked = conn.execute(text("""SELECT COUNT(*) FROM users u JOIN salespersons s ON s.id=u.salesperson_id
                WHERE u.role IN ('visitor','salesperson') AND u.is_active::text IN ('1','true','t')""")).scalar()
            pending = conn.execute(text("SELECT COUNT(*) FROM tasks WHERE review_status='pending'")).scalar()
            reports = conn.execute(text('SELECT COUNT(*) FROM voice_report_entries')).scalar()
    return {'linked_field_accounts': linked, 'tasks_pending_review': pending, 'voice_report_entries': reports}


def collect():
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).with_name('.env'))
    from db import engine
    from voice_reports import speech_readiness
    services = {
        'backend': probe_url('http://127.0.0.1:8000/health'),
        'dashboard': probe_url('http://127.0.0.1:3000/newdash_online.html'),
        'voice_page': probe_url('http://127.0.0.1:3000/voice-report'),
    }
    try:
        database = database_snapshot(engine)
    except Exception:
        database = {'error': True}  # Do not print credentials or connection strings.
    speech = speech_readiness()
    return {'services': services, 'database': database, 'speech': speech,
            'blockers': assess_blockers(database, speech, services),
            'scope': 'بررسی خواندنی؛ هلو و آزمون واقعی گوشی بررسی نشده‌اند'}


if __name__ == '__main__':
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
