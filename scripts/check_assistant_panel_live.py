"""Read every fixed panel resource as CEO; save only statuses, never report contents."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from db import engine
from assistant_panel import RESOURCES,read_panel

with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT id,role,salesperson_id,password_version FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().one())
checks=[]
for resource in RESOURCES:
    try:
        result=read_panel({'resource':resource},user)
        checks.append({'resource':resource,'passed':'data' in result,'status':result.get('status','ok'),'http_status':result.get('http_status',200)})
    except Exception as error:
        checks.append({'resource':resource,'passed':False,'error_type':type(error).__name__})
report={'checks':checks,'passed':sum(r['passed'] for r in checks),'total':len(checks),'business_writes':False}
folder=Path(__file__).resolve().parents[1]/'audit-2026-11-03';folder.mkdir(exist_ok=True)
(folder/'assistant-panel-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report))
