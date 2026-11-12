"""Early real-gateway CI test, independent of slow mobile compilation."""
import json,os,subprocess,sys,tempfile,time
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if os.getenv('KIARAD_REVIEW_DISPOSABLE_DB')!='1':raise SystemExit('Explicit disposable CI PostgreSQL required')
from scripts.configure_traccar import configure,IMAGE
from dotenv import dotenv_values
import requests
runenv={**os.environ,'HOLO_AUTO_REFRESH_ENABLED':'0','HOLO_API_URL':'http://127.0.0.1:9','KIARAD_AUTOMATIONS_DISABLED':'1','KIARAD_AGENT_DISABLED':'1','KIARAD_OUTBOUND_ENABLED':'0','KIARAD_JWT_SECRET':'traccar-ci-synthetic-signing-secret-0123456789'}
subprocess.run([sys.executable,'init_db.py'],cwd=ROOT,env=runenv,check=True)
subprocess.run([sys.executable,'fix_missing_tables.py'],cwd=ROOT,env=runenv,check=True)
from sqlalchemy import text
from db import engine
with engine.begin() as c:
    c.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS password_version INTEGER NOT NULL DEFAULT 0'))
    c.execute(text('ALTER TABLE products ADD COLUMN IF NOT EXISTS price2 DOUBLE PRECISION'))
    c.execute(text("INSERT INTO products(code,name,category,price,price2,stock,is_active) SELECT 'CI-A','Synthetic GPS fixture','Test',10000,10000,10,1 WHERE NOT EXISTS(SELECT 1 FROM products WHERE code='CI-A')"))
container='kiarad-traccar-ci-'+uuid4().hex;api=None;created=False
with tempfile.TemporaryDirectory(prefix='kiarad-traccar-') as directory:
    root=Path(directory);(root/'.env').write_text('KIARAD_AUTOMATIONS_DISABLED=1\n');configure(root,'https://gps.ci.invalid');config=root/'secrets/traccar-forward.xml';config.write_text(config.read_text().replace('http://backend:8000/','http://127.0.0.1:8800/'))
    runenv.update({k:v for k,v in dotenv_values(root/'.env').items() if v is not None})
    try:
        with (root/'api.log').open('w') as logs:
            api=subprocess.Popen([sys.executable,'-m','uvicorn','api:app','--host','127.0.0.1','--port','8800'],cwd=ROOT,env=runenv,stdout=logs,stderr=subprocess.STDOUT)
            for attempt in range(60):
                try:
                    if requests.get('http://127.0.0.1:8800/health',timeout=2).ok:break
                except requests.RequestException:pass
                if api.poll() is not None:raise RuntimeError('CI backend exited: '+(root/'api.log').read_text()[-4000:])
                time.sleep(1)
            else:raise RuntimeError('CI backend did not become ready')
            subprocess.run([sys.executable,'scripts/ci_traccar_smoke.py','--seed'],cwd=ROOT,env=runenv,check=True)
            subprocess.run(['docker','pull','--platform','linux/amd64',IMAGE],check=True)
            subprocess.run(['docker','run','-d','--name',container,'--network','host','--security-opt','no-new-privileges:true','-e','JAVA_TOOL_OPTIONS=-Xmx512m','--mount','type=bind,source='+str(config)+',target=/opt/traccar/conf/traccar.xml,readonly',IMAGE],check=True);created=True
            output=Path(os.environ.get('RUNNER_TEMP',directory))/'traccar-early-smoke.json'
            subprocess.run([sys.executable,'scripts/ci_traccar_smoke.py','--output',str(output)],cwd=ROOT,env=runenv,check=True)
    finally:
        if created:subprocess.run(['docker','rm','-f',container],check=False,stdout=subprocess.DEVNULL)
        if api:
            api.terminate()
            try:api.wait(timeout=10)
            except subprocess.TimeoutExpired:api.kill();api.wait()
