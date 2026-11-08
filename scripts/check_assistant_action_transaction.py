"""Real task confirmation and replay protection, with all writes rolled back."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from db import engine
import operations
import assistant_operations as actions

with engine.connect() as conn:
    transaction=conn.begin()
    @contextmanager
    def scope():yield conn
    proxy=SimpleNamespace(begin=scope,connect=scope)
    try:
        actor=dict(conn.execute(text("SELECT id,role,salesperson_id FROM users WHERE role='ceo' AND is_active=1 ORDER BY id LIMIT 1")).mappings().one())
        before=conn.execute(text('SELECT COUNT(*) FROM tasks')).scalar()
        with patch.object(actions,'engine',proxy),patch.object(operations,'engine',proxy):
            request={'operation':'create_task','payload':{'title':'آزمون برگشت‌پذیر '+uuid4().hex,'assigned_to':actor['id']}}
            first=actions.prepare(request,actor)
            second=actions.prepare(request,actor)
            assert first['proposal_id']==second['proposal_id']
            assert conn.execute(text('SELECT COUNT(*) FROM tasks')).scalar()==before
            receipt=actions.confirm_proposal(first['proposal_id'],actions.Confirmation(confirm=True),actor)
            repeated=actions.confirm_proposal(first['proposal_id'],actions.Confirmation(confirm=True),actor)
            assert receipt['status']=='applied' and repeated['reused'] is True
            assert conn.execute(text('SELECT COUNT(*) FROM tasks')).scalar()==before+1
        print(json.dumps({'checks':4,'passed':True,'rolled_back':True}))
    finally:transaction.rollback()
