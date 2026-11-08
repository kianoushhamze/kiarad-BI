"""Route scheduling: timed stops, shared-visit exception and nearest ordering.

Synthetic QA database only; no production rows are touched.
"""
from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
import json, sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DB_CONFIG
from db import engine
from sqlalchemy import text
from fastapi import HTTPException
import jdatetime
import monthly_visit_plans as plans

assert DB_CONFIG['database'] == 'kiarad_assistant_qa_20261103'

tag = uuid4().hex[:8]
with engine.connect() as c:
    ceo = dict(c.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
    template = dict(c.execute(text("SELECT password_hash FROM users WHERE username='qa_visitor'")).mappings().one())

with engine.begin() as c:
    plans.ensure(c)
    people = []
    for index in (1, 2):
        salesperson = c.execute(text('INSERT INTO salespersons(name) VALUES(:name) RETURNING id'),
                                {'name': f'نیروی مسیر {tag}-{index}'}).scalar_one()
        user = dict(c.execute(text('''INSERT INTO users(username,full_name,password_hash,role,is_active,salesperson_id,password_version,created_at)
            VALUES(:login,:name,:hash,'visitor',1,:sp,0,NOW()) RETURNING *'''),
            {'login': f'qa_route_{index}_{tag}', 'name': f'نیروی مسیر {tag}-{index}', 'hash': template['password_hash'], 'sp': salesperson}).mappings().one())
        people.append(user)
    coords = [(30.2830, 57.0800), (30.2850, 57.0830), (30.2840, 57.0815)]
    bases = [c.execute(text('''INSERT INTO kerman_bases_manual(name,city,address,type,latitude,longitude,visit_radius_m)
        VALUES(:name,'کرمان','نشانی تستی مسیر','pharmacy',:lat,:lng,150) RETURNING id'''),
        {'name': f'پایگاه مسیر {tag}-{i}', 'lat': lat, 'lng': lng}).scalar_one() for i, (lat, lng) in enumerate(coords, start=1)]
    no_coord = c.execute(text('''INSERT INTO kerman_bases_manual(name,city,address,type)
        VALUES(:name,'کرمان','نشانی بدون مختصات','pharmacy') RETURNING id'''), {'name': f'پایگاه بیمختصات {tag}'}).scalar_one()

persian = jdatetime.date.fromgregorian(date=plans.iran_today() + timedelta(days=70))
month = f'{persian.year:04d}-{persian.month:02d}'
start, _ = plans.month_window(month)
day = start + timedelta(days=5)
checks = []


def route(day_value, base, order=1, start_time=None, end_time=None, objective='ویزیت تستی مسیر'):
    return {'visit_date': day_value, 'base_source': 'kerman_bases_manual', 'base_id': base,
            'stop_order': order, 'objective': objective, 'start_time': start_time, 'end_time': end_time}


def draft(owner, stops):
    return plans.create_draft(plans.Draft(user_id=owner['id'], month=month, stops=stops), owner)['id']


with patch.object(plans, 'iran_today', return_value=start):
    first = draft(people[0], [route(day, bases[0], 1), route(day, bases[1], 2)])
    plans.submit(first, people[0])
    plans.review(first, plans.Decision(decision='approved', note='تأیید برنامهٔ دارای ترتیب تستی'), ceo)

    for label, stops in (
        ('overlapping_windows_rejected', [route(day, bases[0], 1, time(9), time(11)), route(day, bases[1], 2, time(10), time(12))]),
        ('half_timed_day_rejected', [route(day, bases[0], 1, time(9), time(10)), route(day, bases[1], 2)]),
        ('backwards_window_rejected', [route(day, bases[0], 1, time(11), time(9))]),
    ):
        try:
            draft(people[0], stops)
        except HTTPException as error:
            assert error.status_code == 422, (label, error.status_code)
            checks.append(label)
        else:
            raise AssertionError('Invalid schedule was accepted: ' + label)

with patch.object(plans, 'iran_today', return_value=start):
    timed = draft(people[1], [route(day, bases[2], 1, time(14), time(15))])
    plans.submit(timed, people[1])
    plans.review(timed, plans.Decision(decision='approved', note='تأیید برنامهٔ زمان‌دار تستی'), ceo)

with engine.connect() as c:
    stored = c.execute(text('''SELECT start_time,end_time FROM visit_route_assignments
        WHERE user_id=:u AND base_source='kerman_bases_manual' AND base_id=:b AND visit_date=:d'''),
        {'u': people[1]['id'], 'b': bases[2], 'd': day}).one()
    assert stored[0] is not None and stored[0].strftime('%H:%M') == '14:00', stored
    assert stored[1].strftime('%H:%M') == '15:00', stored
    checks.append('schedule_time_published_on_route')

with patch.object(plans, 'iran_today', return_value=start):
    shared = draft(people[0], [route(day, bases[2], 3, time(16), time(17), 'ویزیت مشترک با نیروی دیگر')])
    plans.submit(shared, people[0])
    try:
        plans.review(shared, plans.Decision(decision='approved', note='تلاش تأیید بدون اجازهٔ ویزیت مشترک'), ceo)
    except HTTPException as error:
        assert error.status_code == 409 and 'مشترک' in error.detail, error.detail
        checks.append('shared_visit_blocked_without_explicit_choice')
    else:
        raise AssertionError('Shared visit published without approval')
    try:
        plans.review(shared, plans.Decision(decision='approved', note='کوتاه', allow_shared=True), ceo)
    except HTTPException as error:
        assert error.status_code == 422, error.status_code
        checks.append('shared_visit_requires_reason')
    else:
        raise AssertionError('Shared visit accepted with a short reason')
    plans.review(shared, plans.Decision(decision='approved', note='هماهنگی تلفنی با نیروی دیگر انجام و ویزیت مشترک تصویب شد', allow_shared=True), ceo)
    with engine.connect() as c:
        assert c.execute(text("SELECT 1 FROM monthly_visit_plan_events WHERE plan_id=:p AND event='shared_visit_approved'"), {'p': shared}).scalar()
        count = c.execute(text("""SELECT count(*) FROM visit_route_assignments WHERE base_source='kerman_bases_manual'
            AND base_id=:b AND visit_date=:d"""), {'b': bases[2], 'd': day}).scalar()
    assert count == 2, count
    checks.extend(['shared_visit_published_after_explicit_ceo_approval', 'shared_visit_recorded_in_history'])

suggestion = plans.order_suggestion(plans.OrderRequest(stops=[
    {'base_source': 'kerman_bases_manual', 'base_id': bases[0]},
    {'base_source': 'kerman_bases_manual', 'base_id': bases[1]},
    {'base_source': 'kerman_bases_manual', 'base_id': bases[2]},
]), ceo)
assert suggestion['order'][0] == 0, suggestion
assert suggestion['order'] == [0, 2, 1], suggestion
assert suggestion['distance_m'] > 0, suggestion
checks.append('nearest_neighbour_order_uses_coordinates')

missing = plans.order_suggestion(plans.OrderRequest(stops=[
    {'base_source': 'kerman_bases_manual', 'base_id': bases[0]},
    {'base_source': 'kerman_bases_manual', 'base_id': no_coord},
]), ceo)
assert missing['missing_coordinates'] == [{'base_source': 'kerman_bases_manual', 'base_id': no_coord}], missing
assert missing['order'][-1] == 1, missing
checks.append('stops_without_coordinates_are_reported_and_kept_last')

report = {'passed': True, 'checks': checks, 'month': month, 'production_data_changed': False}
root = Path(__file__).resolve().parents[1]
(root / 'audit-2026-11-03/route-scheduling-qa.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
