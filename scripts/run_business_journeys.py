"""Own an isolated local stack for the real HTTP/browser acceptance journeys."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    if os.getenv('KIARAD_REVIEW_DISPOSABLE_DB') != '1' or not os.getenv('DB_NAME', '').startswith('kiarad_e2e'):
        raise SystemExit('Explicit disposable kiarad_e2e database required')
    if os.getenv('DB_HOST') not in {'127.0.0.1', 'localhost'}:
        raise SystemExit('Only local isolated PostgreSQL is supported')
    if (ROOT / 'secrets').exists() and any(p.is_file() for p in (ROOT / 'secrets').rglob('*')):
        raise SystemExit('Use a clean checkout without real service credentials')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for port in (58810, 53310, 58191):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit('Test port already owned by another process: ' + str(port))
    os.environ.update({
        'KIARAD_JWT_SECRET': 'synthetic-browser-journey-signing-secret-0123456789',
        'HOLO_API_URL': 'http://127.0.0.1:9', 'HOLO_AUTO_REFRESH_ENABLED': '0',
        'KIARAD_AUTOMATIONS_DISABLED': '1', 'KIARAD_AGENT_DISABLED': '1',
        'KIARAD_ROUTINES_DISABLED': '1', 'KIARAD_OUTBOUND_ENABLED': '0',
        'KIARAD_TRACCAR_ENABLED': '0', 'AVALAI_API_KEY': '', 'OPENAI_API_KEY': '',
        'KIARAD_API_URL': 'http://127.0.0.1:58810', 'NEXT_PUBLIC_API_URL': 'http://127.0.0.1:58810',
        'PORT': '53310', 'HOSTNAME': '127.0.0.1',
        'KIARAD_SITE_PORT': '58191', 'KIARAD_SITE_HOST': '127.0.0.1',
    })
    for script in ('init_db.py', 'fix_missing_tables.py', 'scripts/run_migrations.py'):
        subprocess.run([sys.executable, script], cwd=ROOT, check=True)
    from db import engine
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS password_version INTEGER NOT NULL DEFAULT 0'))
        conn.execute(text('ALTER TABLE products ADD COLUMN IF NOT EXISTS price2 DOUBLE PRECISION'))
    # Run the server directly so cleanup owns the actual process, not npm's
    # shell parent (which can leave an orphan listening after the suite exits).
    subprocess.run(['node', 'scripts/prepare-standalone.mjs'], cwd=ROOT / 'kiarad-dashboard', check=True)
    processes, logs = [], []
    try:
        for name, cmd, cwd in (
            ('api', [sys.executable, '-m', 'uvicorn', 'api:app', '--host', '127.0.0.1', '--port', '58810'], ROOT),
            ('panel', ['node', '.next/standalone/server.js'], ROOT / 'kiarad-dashboard'),
            ('storefront', ['node', 'scripts/serve_kiaradhealer.mjs'], ROOT),
        ):
            stream = (args.output / (name + '.log')).open('w')
            logs.append(stream)
            processes.append(subprocess.Popen(cmd, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT))
        import requests
        for url in ('http://127.0.0.1:58810/health', 'http://127.0.0.1:53310/login', 'http://127.0.0.1:58191/buy/'):
            for attempt in range(60):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('Test service exited; inspect owned service logs')
                try:
                    if requests.get(url, timeout=2).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError('Owned test service did not become ready')
        return subprocess.run([sys.executable, 'scripts/check_business_journeys.py', '--output', str(args.output)], cwd=ROOT).returncode
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in logs:
            stream.close()


if __name__ == '__main__':
    raise SystemExit(main())
