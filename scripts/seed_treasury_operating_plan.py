"""Save the manager's explicit budget instruction once, without financial entries."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from sqlalchemy import text
from db import engine
from iran_time import iran_today
from treasury_operating_plan import default_operating_plan
from treasury_strategy import ensure_schema,_latest,_save

with engine.begin() as conn:
    ensure_schema(conn)
    row = _latest(conn,'operating-plan')
    if row:
        result = {'saved':False,'revision':row['revision'],'reason':'existing_policy_preserved'}
    else:
        user = conn.execute(text("SELECT id,role FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().one()
        policy = {**default_operating_plan(),'balance_source':'holoo','attested_at':iran_today().isoformat()}
        saved = _save(conn,'operating-plan',0,policy,dict(user),True)
        result = {'saved':True,'revision':saved['revision'],'monthly_expense_irr':3000000000,'financial_entries_created':False,'holoo_writes':False}
print(json.dumps(result))
