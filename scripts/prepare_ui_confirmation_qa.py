from pathlib import Path
import sys,json
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import DB_CONFIG
from db import engine
from sqlalchemy import text
from assistant_operations import prepare
assert DB_CONFIG['database']=='kiarad_assistant_qa_20261103'
with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
title='وظیفه تأیید مرورگر '+uuid4().hex[:8]
result=prepare({'operation':'create_task','payload':{'title':title,'assigned_to':user['id']}},user)
(Path(__file__).resolve().parents[1]/'private_exports/assistant-ui-confirmation.json').write_text(json.dumps({'id':result['proposal_id'],'title':title},ensure_ascii=False),encoding='utf-8')
print('QA proposal prepared; business task not created')
