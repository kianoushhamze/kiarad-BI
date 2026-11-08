from pathlib import Path
import sys,json
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from dotenv import load_dotenv
load_dotenv(root/'.env',override=False)
from db import engine
from sqlalchemy import text
names=['products','sales','sale_items','holoo_entity_mappings','base_checkins','customer_interactions','voice_reports','crm_followups','pharmacies','cosmetics_shops','kerman_bases_manual','base_portfolio_assignments','tasks','task_updates']
with engine.connect() as conn:
    conn.exec_driver_sql('SET TRANSACTION READ ONLY')
    rows=conn.execute(text("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(:names) ORDER BY table_name,ordinal_position"),{'names':names}).mappings().all()
print(json.dumps([dict(r) for r in rows]))
