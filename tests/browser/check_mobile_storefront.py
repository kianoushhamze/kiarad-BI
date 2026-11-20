"""Real browser regression for responsive login and checkout; mock HTTP API only.

Install Playwright and Chromium. Set CHROMIUM_EXECUTABLE_PATH to use a system
Chromium. No company database, tokens, ERP, or external orders are used.
"""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ORDERS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, data, status=200):
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == '/api/public/catalog':
            return self.send_json({'products': [{'code': 'BROWSER-A', 'name': 'محصول آزمایشی',
                                                'category': 'Test', 'consumer_price_toman': 1150, 'in_stock': True}]})
        if self.path == '/api/site-banners':
            return self.send_json({'banners': []})
        if self.path == '/api/site-auth/me':
            return self.send_json({'name': 'Browser fixture'})
        files = {'/buy/': ROOT / 'site-healer/buy.html'}
        for font in ('Vazirmatn-Bold.ttf', 'Vazirmatn-Regular.ttf', 'lalezar.woff2'):
            files['/buy/fonts/' + font] = ROOT / 'site-healer/fonts' / font
        if self.path not in files:
            return self.send_json({}, 404)
        data = files[self.path].read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if self.path == '/buy/' else 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/site-auth/register':
            return self.send_json({'name': 'Browser fixture', 'token': 'test-only-token'})
        if self.path == '/api/site-orders':
            assert self.headers.get('Authorization') == 'Bearer test-only-token'
            assert body['items'] == [{'code': 'BROWSER-A', 'qty': 1}]
            ORDERS.append(body)
            return self.send_json({'ok': True, 'order_id': 42, 'total_irr': 10000})
        return self.send_json({}, 404)


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        with sync_playwright() as playwright:
            options = {'headless': True, 'args': ['--no-sandbox', '--disable-dev-shm-usage']}
            if os.getenv('CHROMIUM_EXECUTABLE_PATH'):
                options['executable_path'] = os.environ['CHROMIUM_EXECUTABLE_PATH']
            browser = playwright.chromium.launch(**options)
            try:
                for width in (360, 390, 640, 1280):
                    context = browser.new_context(viewport={'width': width, 'height': 900})
                    page = context.new_page()
                    crashes = []
                    page.on('pageerror', lambda error: crashes.append(str(error)))
                    page.goto(f'http://127.0.0.1:{server.server_port}/buy/', wait_until='networkidle')
                    page.get_by_text('محصول آزمایشی', exact=True).wait_for()
                    for selector in ('#loginMode', '#authContact', '#authPass', '#authSubmit', '#cartBtn'):
                        box = page.locator(selector).bounding_box()
                        assert box and box['x'] >= -1 and box['x'] + box['width'] <= width + 1, (width, selector, box)
                    page.locator('#loginMode').click()
                    for selector, value in (('#authName', 'Browser fixture'), ('#authContact', 'fixture@example.test'), ('#authPass', 'test-only-password')):
                        page.locator(selector).fill(value)
                    page.locator('#authSubmit').click()
                    page.locator('#whoName').wait_for(state='visible')
                    page.locator('[data-add="BROWSER-A"]').click()
                    page.locator('#cartBtn').click()
                    page.locator('#toInfo').click()
                    for selector, value in (('#fName', 'Browser fixture'), ('#fPhone', '09123456789'), ('#fCity', 'Test'), ('#fAddr', 'Synthetic address')):
                        page.locator(selector).fill(value)
                    page.locator('#toConfirm').click()
                    page.locator('#submitOrder').click()
                    page.locator('.oid').wait_for()
                    assert not crashes, crashes
                    results.append({'width': width, 'login_and_checkout': True, 'runtime_errors': 0})
                    context.close()
            finally:
                browser.close()
        assert len(ORDERS) == 4
        print(json.dumps({'passed': True, 'cases': results, 'mock_orders': len(ORDERS), 'company_data_used': False}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
