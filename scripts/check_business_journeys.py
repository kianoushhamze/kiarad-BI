"""Opt-in real HTTP/browser journeys against an explicitly disposable database.

Start an isolated backend, production panel and storefront first. This runner
does not connect to ERP or send messages. Browser sessions and tokens stay in
memory; the JSON report contains only synthetic record IDs and check results.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import shutil
import sys
from threading import Barrier
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    if os.getenv('KIARAD_REVIEW_DISPOSABLE_DB') != '1' or not os.getenv('DB_NAME', '').startswith('kiarad_e2e'):
        raise SystemExit('Explicit kiarad_e2e disposable database and opt-in are required')
    if os.getenv('DB_HOST') not in {'127.0.0.1', 'localhost'}:
        raise SystemExit('Only a local disposable PostgreSQL instance is supported')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:58810')
    parser.add_argument('--web', default='http://127.0.0.1:53310')
    parser.add_argument('--storefront', default='http://127.0.0.1:58191')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for address in (args.api, args.web, args.storefront):
        if not address.startswith('http://127.0.0.1:'):
            raise SystemExit('Journeys may target only loopback test services')
    import requests
    from sqlalchemy import text
    from db import engine
    from operations import hash_password
    from iran_time import iran_today
    import jdatetime
    from playwright.sync_api import sync_playwright

    suffix = uuid4().hex[:8]
    password = 'Synthetic-Journey-' + suffix
    names = {r: 'journey_' + r + '_' + suffix for r in ('ceo', 'alice', 'bob', 'finance')}
    sessions, users, results = {}, {}, []
    args.output.mkdir(parents=True, exist_ok=True)

    def check(name, fn):
        try:
            fn()
            results.append({'name': name, 'passed': True})
        except Exception as exc:
            results.append({'name': name, 'passed': False, 'error': type(exc).__name__ + ': ' + str(exc)[:700]})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)

    def call(method, path, role='ceo', expected=200, **kwargs):
        r = requests.request(method, args.api + path, headers=sessions.get(role, {}), timeout=25, **kwargs)
        assert r.status_code == expected, (method, path, r.status_code, r.text[:350])
        return r.json()

    with engine.begin() as c:
        for role in names:
            sp = None
            if role in {'alice', 'bob'}:
                sp = c.execute(text('INSERT INTO salespersons(name) VALUES(:name) RETURNING id'), {'name': names[role]}).scalar_one()
            row = c.execute(text('''INSERT INTO users(username,full_name,role,salesperson_id,password_hash,is_active,password_version,created_at)
                VALUES(:name,:name,:role,:sp,:password,1,0,NOW()) RETURNING id,salesperson_id'''),
                {'name': names[role], 'role': 'salesperson' if role in {'alice', 'bob'} else role,
                 'sp': sp, 'password': hash_password(password)}).mappings().one()
            users[role] = dict(row)
        customer = c.execute(text('''INSERT INTO customers(code,name,city,credit_limit)
            VALUES(:code,:name,'Test city',10000) RETURNING id'''), {'code': 'J-C-' + suffix, 'name': 'مشتری ساختگی ' + suffix}).scalar_one()
    for role in names:
        r = requests.post(args.api + '/auth/login', json={'username': names[role], 'password': password}, timeout=15)
        r.raise_for_status()
        sessions[role] = {'Authorization': 'Bearer ' + r.json()['access_token']}

    def product(label, stock=5):
        code = 'J-' + suffix + '-' + label
        with engine.begin() as c:
            ident = c.execute(text('''INSERT INTO products(code,name,category,price,price2,stock,is_active,updated_at)
                VALUES(:code,:name,'Journey',100000,100000,:stock,1,NOW()) RETURNING id'''),
                {'code': code, 'name': 'محصول آزمایشی ' + label + ' ' + suffix, 'stock': stock}).scalar_one()
        return ident, code

    # Confirm both frontends point to this fixture database before any browser
    # registration/order writes. A wrong proxy target must fail closed.
    proxy_user = requests.get(args.web + '/api/auth/me', headers=sessions['ceo'], timeout=15)
    assert proxy_user.status_code == 200 and proxy_user.json()['username'] == names['ceo']
    _, probe_code = product('connectivity-probe', 1)
    proxy_catalog = requests.get(args.storefront + '/api/public/catalog', timeout=15)
    assert proxy_catalog.status_code == 200 and any(p['code'] == probe_code for p in proxy_catalog.json()['products'])

    def parallel_registration():
        def register(n):
            return requests.post(args.api + '/site-auth/register', timeout=25, json={
                'name': 'ثبت‌نام هم‌زمان ساختگی', 'password': password,
                'contact': f'parallel-{n}-{suffix}@example.test'}).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(register, (0, 0, 1, 2)))
        assert sorted(statuses) == [200, 200, 200, 409], statuses
    check('concurrent_cold_registration_and_duplicate_conflict', parallel_registration)

    buyer_contact = 'journey-' + suffix + '@example.test'
    buyer = call('POST', '/site-auth/register', role=None, json={'name': 'خریدار ساختگی ' + suffix, 'contact': buyer_contact, 'password': password})
    sessions['buyer'] = {'Authorization': 'Bearer ' + buyer['token']}

    def proforma(pid, qty, expected=200):
        return call('POST', '/operations/proformas', 'alice', expected, json={
            'customer_id': customer, 'items': [{'product_id': pid, 'quantity': qty, 'unit_price': 1}]})

    def order(code, qty, key=None, expected=200):
        return call('POST', '/site-orders', 'buyer', expected, json={
            'customer_name': 'خریدار ساختگی ' + suffix, 'phone': '09000000000', 'city': 'Test',
            'address': 'Synthetic test address only', 'items': [{'code': code, 'qty': qty}],
            'request_id': key or uuid4().hex})

    def stock(code):
        return next(p['stock'] for p in call('GET', '/public/catalog', None)['products'] if p['code'] == code)

    def cold_financial_requests():
        barrier = Barrier(4)
        def read(role):
            barrier.wait(timeout=10)
            return call('GET', '/treasury/strategy/overview', role)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(read, role) for role in ('ceo', 'finance', 'ceo', 'finance')]
            for future in futures:
                future.result()
    check('concurrent_first_financial_snapshot_requests', cold_financial_requests)

    def role_boundaries():
        for role in ('alice', 'bob', 'finance'):
            call('GET', '/site-cms/products', role, 403)
            call('GET', '/users', role, 403)
        call('GET', '/treasury/overview', 'finance')
        call('GET', '/treasury/overview', 'alice', 403)
        for path in ('/users', '/site-orders/all'):
            r = requests.get(args.api + path, headers=sessions['buyer'], timeout=10)
            assert r.status_code in {401, 403}, (path, r.status_code)
    check('real_login_and_role_boundaries', role_boundaries)

    def cross_channel():
        pid, code = product('cross')
        pf = proforma(pid, 4)
        assert pf['status'] == 'pending' and pf['total_amount'] == 400000
        call('POST', f"/operations/proformas/{pf['proforma_id']}/approve", 'bob', 403)
        call('POST', f"/operations/proformas/{pf['proforma_id']}/approve")
        order(code, 2, expected=400)
        assert stock(code) == 1
        call('POST', f"/operations/proformas/{pf['proforma_id']}/cancel", 'bob', 403)
        call('POST', f"/operations/proformas/{pf['proforma_id']}/cancel", 'alice')
        assert stock(code) == 5
        key = uuid4().hex
        web_order = order(code, 4, key)
        replay = order(code, 4, key)
        assert web_order['order_id'] == replay['order_id'] and replay['replayed']
        order(code, 3, key, expected=409)
        proforma(pid, 2, expected=409)
        assert stock(code) == 1
        for path, field in [('/operations/products-list', None), ('/catalog/products', 'items')]:
            rows = call('GET', path)
            if field:
                rows = rows[field]
            assert next(p['available_stock'] for p in rows if p['id'] == pid) == 1
        call('PATCH', f"/site-orders/{web_order['order_id']}/status", json={'status': 'لغو شد'})
        assert stock(code) == 5
        call('PATCH', f"/site-orders/{web_order['order_id']}/status", expected=409, json={'status': 'جدید'})
    check('proforma_storefront_stock_approval_cancel_and_retry', cross_channel)

    def concurrent_orders():
        pid, code = product('race')
        def pf():
            return requests.post(args.api + '/operations/proformas', headers=sessions['alice'], json={
                'customer_id': customer, 'items': [{'product_id': pid, 'quantity': 4}]}, timeout=25).status_code
        def website():
            return requests.post(args.api + '/site-orders', headers=sessions['buyer'], json={
                'customer_name': 'Race fixture', 'phone': '09000000000', 'city': 'Test', 'address': 'Synthetic address',
                'items': [{'code': code, 'qty': 4}], 'request_id': uuid4().hex}, timeout=25).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(pf), pool.submit(website)]
            statuses = [f.result() for f in futures]
        assert statuses.count(200) == 1 and all(s in {200, 400, 409} for s in statuses), statuses
        assert stock(code) == 1
    check('concurrent_cross_channel_last_units', concurrent_orders)

    def multi_item_stress():
        a, code_a = product('stress-B')
        b, code_b = product('stress-A')
        def buy(n):
            if n % 2:
                path, role = '/operations/proformas', 'alice'
                ids = (a, b) if n % 4 == 1 else (b, a)
                data = {'customer_id': customer, 'items': [{'product_id': pid, 'quantity': 1} for pid in ids]}
            else:
                path, role = '/site-orders', 'buyer'
                data = {'customer_name': 'Synthetic stress', 'phone': '09000000000', 'city': 'Test',
                        'address': 'Synthetic stress address', 'request_id': uuid4().hex,
                        'items': [{'code': code_b, 'qty': 1}, {'code': code_a, 'qty': 1}]}
            return requests.post(args.api + path, headers=sessions[role], json=data, timeout=30).status_code
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(buy, range(16)))
        assert statuses.count(200) == 5 and all(s in {200, 400, 409} for s in statuses), statuses
        assert stock(code_a) == stock(code_b) == 0
        raw = json.dumps({'customer_id': customer, 'total_amount': 'replace-with-exponent'}).replace('"replace-with-exponent"', '1e309')
        response = requests.post(args.api + '/operations/proformas', headers={**sessions['alice'], 'Content-Type': 'application/json'}, data=raw, timeout=15)
        assert response.status_code == 422, (response.status_code, response.text[:200])
    check('sixteen_parallel_two_sku_checkouts_and_invalid_numeric_input', multi_item_stress)

    def visits():
        today = iran_today()
        with engine.begin() as c:
            base = c.execute(text('''INSERT INTO pharmacies(name,city,address,latitude,longitude,visit_radius_m)
                VALUES(:name,'Test','Synthetic address',30,57,150) RETURNING id'''), {'name': 'پایگاه آزمایشی ' + suffix}).scalar_one()
        month = jdatetime.date.fromgregorian(date=today).strftime('%Y-%m')
        plan = call('POST', '/monthly-visit-plans', 'alice', 201, json={'user_id': users['alice']['id'], 'month': month,
            'stops': [{'visit_date': today.isoformat(), 'base_source': 'pharmacies', 'base_id': base, 'stop_order': 1,
                       'objective': 'ویزیت آزمایشی', 'start_time': '09:00', 'end_time': '10:00'}]})
        call('GET', f"/monthly-visit-plans/{plan['id']}", 'bob', 403)
        call('POST', f"/monthly-visit-plans/{plan['id']}/submit", 'alice')
        call('POST', f"/monthly-visit-plans/{plan['id']}/review", json={'decision': 'approved', 'note': 'تأیید برنامهٔ آزمایشی'})
        data = {'source': 'pharmacies', 'base_id': base, 'lat': 30, 'lng': 57, 'accuracy_m': .7,
                'note': 'نتیجهٔ ویزیت ساختگی ثبت شد', 'submission_key': uuid4().hex}
        first = call('POST', '/api/compensation/base-checkins', 'alice', json=data)
        assert first['status'] == 'verified'
        repeated = call('POST', '/api/compensation/base-checkins', 'alice', json=data)
        assert first['checkin_id'] == repeated['checkin_id'] and repeated['already_saved']
        call('POST', '/daily-reports', 'alice', 201, json={'report_date': today.isoformat(), 'visits_count': 1, 'notes': 'گزارش ساختگی'})
        summary = call('GET', f"/monthly-visit-plans/{plan['id']}")['summary']
        assert summary['verified_stops'] == 1 and summary['fully_completed_days'] == 1, summary
    check('visit_plan_checkin_evidence_and_manager_visibility', visits)

    def assistant():
        result = call('POST', '/assistant/chat', json={'message': 'ارزش انبار چقدره؟'})
        assert result.get('answer') and result.get('mode') == 'verified_inventory_value', result
        # Cross-company finance must stay unavailable to staff.
        staff = call('POST', '/assistant/chat', 'alice', json={'message': 'صورتحساب بدهکاران چنده؟'})
        assert staff.get('answer') and staff.get('mode') == 'access_limited', staff
    check('source_backed_assistant_financial_questions', assistant)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE_PATH') or shutil.which('chromium'),
                                     args=['--no-sandbox', '--disable-dev-shm-usage'])
        contexts = {}
        pages = {}
        crashes = []
        failed_api_reads = []

        def response_check(response):
            if response.status >= 500 and '/api/' in response.url:
                # A configured-off ERP is expected to report unavailable.
                if '/holoo/' not in response.url or response.status not in {502, 503}:
                    failed_api_reads.append({'path': response.url.split('/api/', 1)[-1], 'status': response.status})
        for role in ('ceo', 'alice', 'bob', 'finance'):
            ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = ctx.new_page()
            page.on('pageerror', lambda error: crashes.append(str(error)))
            page.on('response', response_check)
            page.goto(args.web + '/login')
            page.locator('input[type=text]').fill(names[role])
            if role == 'ceo':
                page.locator('input[type=password]').fill('intentionally-wrong-password')
                page.get_by_role('button', name='ورود به سامانه').click()
                page.get_by_text('نام کاربری یا کلمه عبور اشتباه است.', exact=True).wait_for()
                assert page.url.endswith('/login')
            page.locator('input[type=password]').fill(password)
            page.get_by_role('button', name='ورود به سامانه').click()
            home = {'alice': 'my-plan', 'bob': 'my-plan', 'finance': 'treasury'}.get(role, 'management')
            page.wait_for_url('**/' + home)
            page.locator('main').wait_for()
            contexts[role], pages[role] = ctx, page

        def task_browser():
            chief, worker = pages['ceo'], pages['alice']
            title = 'کار آزمایشی سرتاسری ' + suffix
            chief.goto(args.web + '/tasks')
            chief.get_by_role('button', name='ایجاد کار', exact=True).click()
            chief.get_by_label('عنوان کار', exact=True).fill(title)
            chief.get_by_label('شرح کار', exact=True).fill('خروجی آزمایشی قابل بررسی مدیر')
            chief.get_by_label('پرسنل مسئول', exact=True).select_option(str(users['alice']['id']))
            chief.get_by_role('button', name='ثبت و تخصیص', exact=True).click()
            chief.get_by_role('heading', name=title, exact=True).wait_for()
            assert not any(t['title'] == title for t in call('GET', '/tasks', 'bob')['tasks'])
            worker.goto(args.web + '/tasks')
            card = worker.get_by_role('heading', name=title, exact=True).locator('..').locator('..')
            card.get_by_role('textbox').fill('خروجی ساختگی برای تأیید مدیر آماده شد')
            with worker.expect_response(lambda r: r.url.endswith('/progress') and r.request.method == 'PATCH') as finished:
                card.get_by_role('button', name='ارسال گزارش پایان کار', exact=True).click()
            assert finished.value.status == 200
            chief.reload()
            card = chief.get_by_role('heading', name=title, exact=True).locator('..').locator('..')
            card.get_by_role('textbox').fill('نتیجه در آزمون مرورگر تأیید شد')
            with chief.expect_response(lambda r: r.url.endswith('/review') and r.request.method == 'POST') as approved:
                card.get_by_role('button', name='تأیید نتیجهٔ کار', exact=True).click()
            assert approved.value.status == 200
            item = next(t for t in call('GET', '/tasks')['tasks'] if t['title'] == title)
            assert item['review_status'] == 'approved' and item['progress'] == 100
            chief.get_by_text('تأییدشده', exact=True).first.wait_for()
            chief.screenshot(path=str(args.output / 'task-manager-approved.png'), full_page=True)
        check('browser_ceo_assign_worker_report_ceo_approve', task_browser)

        def proforma_browser():
            pid, code = product('proforma-ui')
            page = pages['alice']
            page.goto(args.web + '/proformas')
            page.get_by_label('مشتری پیش‌فاکتور', exact=True).select_option(str(customer))
            page.get_by_label('کالای ردیف 1', exact=True).select_option(str(pid))
            page.get_by_label('تعداد ردیف 1', exact=True).fill('2')
            with page.expect_response(lambda r: r.url.endswith('/operations/proformas') and r.request.method == 'POST') as created:
                page.get_by_role('button', name='ثبت و صدور پیش‌فاکتور', exact=True).click()
            assert created.value.status == 200
            data = created.value.json()
            assert data['total_amount'] == 200000 and stock(code) == 3
            page.reload()
            page.get_by_role('button', name='لغو و آزادسازی کالا', exact=True).first.wait_for()
            page.on('dialog', lambda dialog: dialog.accept())
            with page.expect_response(lambda r: r.url.endswith('/cancel') and r.request.method == 'POST') as cancelled:
                page.get_by_role('button', name='لغو و آزادسازی کالا', exact=True).first.click()
            assert cancelled.value.status == 200 and cancelled.value.json()['proforma_id'] == data['proforma_id']
            assert stock(code) == 5
        check('browser_proforma_create_reload_cancel_restores_stock', proforma_browser)

        def render_routes():
            for role, routes in [('ceo', ['/management','/catalog','/proformas','/tasks','/monthly-plans','/site-cms','/treasury','/assistant']),
                                 ('alice', ['/visitors','/my-plan','/tasks','/proformas']), ('finance', ['/treasury','/tasks'])]:
                page = pages[role]
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    for route in routes:
                        page.goto(args.web + route)
                        page.locator('main').wait_for()
                        page.wait_for_load_state('networkidle')
                        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 4'), (role, route, width)
                page.screenshot(path=str(args.output / (role + '-mobile.png')), full_page=True)
            assert not crashes, crashes
            assert not failed_api_reads, failed_api_reads
        check('browser_role_routes_desktop_mobile_no_runtime_crash', render_routes)

        def store_browser():
            _, code = product('browser')
            ctx = browser.new_context(viewport={'width': 390, 'height': 900})
            page = ctx.new_page()
            page.goto(args.storefront + '/buy/')
            page.locator('#loginMode').click()
            page.locator('#authName').fill('خریدار مرورگر ' + suffix)
            page.locator('#authContact').fill('browser-' + suffix + '@example.test')
            page.locator('#authPass').fill(password)
            page.locator('#authSubmit').click()
            page.locator('#whoName').wait_for(state='visible')
            page.locator('[data-add="' + code + '"]').click()
            page.locator('#cartBtn').click()
            page.locator('#toInfo').click()
            for selector, value in [('#fName','خریدار مرورگر '+suffix),('#fPhone','09000000000'),('#fCity','Test'),('#fAddr','Synthetic browser address')]:
                page.locator(selector).fill(value)
            page.locator('#toConfirm').click()
            # A failed network attempt must preserve the cart and allow a safe retry.
            page.route('**/api/site-orders', lambda route: route.abort())
            page.locator('#submitOrder').click()
            page.wait_for_function("() => {const b=document.getElementById('submitOrder');return b && !b.disabled;}")
            assert page.locator('.oid').count() == 0
            page.unroute('**/api/site-orders')
            with page.expect_response(lambda r: r.url.endswith('/api/site-orders') and r.request.method == 'POST') as response:
                page.locator('#submitOrder').click()
            receipt = response.value.json()
            page.locator('.oid').wait_for()
            digits = re.findall(r'\d+', page.locator('.oid').inner_text())
            assert digits and int(digits[-1]) == receipt['order_id'], (digits, receipt['order_id'])
            assert stock(code) == 4
            page.wait_for_function('''code => {const button=document.querySelector('[data-add="'+code+'"]');
                return button && button.closest('.card')?.querySelector('.stock')?.textContent.includes('۴');}''', arg=code, timeout=5000)
            page.screenshot(path=str(args.output / 'storefront-real-receipt.png'), full_page=True)
            ctx.close()
        check('browser_registration_checkout_and_same_database_receipt', store_browser)

        def session_lifecycle():
            old_headers = sessions['alice']
            new_password = password + '-changed'
            call('POST', '/auth/password', 'alice', json={'current_password': password, 'new_password': new_password})
            old = requests.get(args.api + '/auth/me', headers=old_headers, timeout=10)
            assert old.status_code == 401
            r = requests.post(args.api + '/auth/login', json={'username': names['alice'], 'password': new_password}, timeout=10)
            assert r.status_code == 200 and r.json()['user']['role'] == 'salesperson'
            pages['alice'].goto(args.web + '/tasks')
            pages['alice'].wait_for_url('**/login')
            assert call('GET', '/auth/me', 'bob')['id'] == users['bob']['id']
        check('password_change_revokes_own_browser_session_preserves_other_user', session_lifecycle)
        for ctx in contexts.values():
            ctx.close()
        browser.close()

    report = {'scope': 'real HTTP and production-browser journeys on synthetic local data',
              'company_data_used': False, 'checks': results, 'passed': all(r['passed'] for r in results),
              'limits': ['No real ERP/model/channel requests', 'No physical GPS or company-server acceptance']}
    (args.output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
