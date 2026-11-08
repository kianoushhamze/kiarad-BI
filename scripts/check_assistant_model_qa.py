"""Real provider acceptance with synthetic data and proposals only, no confirmations."""
from pathlib import Path
import sys,json
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from config import DB_CONFIG
from db import engine
from assistant_engine import call_gpt
import assistant_reports

assert DB_CONFIG['database']=='kiarad_assistant_qa_20261103'
with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
cases=[
 ('target_without_internal_id','برای پرسنل آزمون دستیار یک تارگت به نام «هدف تست ایجنت» با مبلغ ۲۰ میلیون تومان و پاداش صفر از ۱۴۰۵/۰۹/۰۱ تا ۱۴۰۵/۰۹/۳۰ ثبت کن. پیش‌نمایش بده تا تأیید کنم.'),
 ('treasury_operation','یک حساب نقدی به نام «صندوق پیشنهاد ایجنت» با موجودی ۱۲۳۰۰۰ ریال و حداقل ذخیره ۱۰۰۰ ریال ایجاد کن. پیش‌نمایش بده تا تأیید کنم.'),
 ('financial_analysis','وضعیت خزانه و چک‌های ثبت‌شده را از پنل بخوان، تحلیل کن و سه اقدام پیشنهادی بده. کامل‌بودن منابع را فرض نکن؛ چیزی ثبت نکن.'),
]
results=[]
real=assistant_reports.execute_report_tool
for name,question in cases:
    calls=[]
    def trace(tool,args,actor):
        value=real(tool,args,actor)
        calls.append({'tool':tool,'resource':args.get('resource'),'operation':args.get('operation'),'status':value.get('status') if isinstance(value,dict) else None,'arguments':args,'response':value})
        return value
    with patch.object(assistant_reports,'execute_report_tool',side_effect=trace):
        answer=call_gpt(question,{'_actor':user},[],user['role'],user['full_name'])
    preview=isinstance(answer,dict) and answer.get('mode')=='operation_preview'
    if preview and name=='target_without_internal_id':
        ident=answer['action']['href'].split('id=')[-1]
        with engine.connect() as conn:
            stored=conn.execute(text('SELECT payload FROM assistant_operation_proposals WHERE id=:id'),{'id':ident}).scalar_one()
        preview=stored['body']['unit']=='TOMAN' and __import__('decimal').Decimal(str(stored['body']['rows'][0]['target_amount']))==20000000
    passed=preview if name!='financial_analysis' else isinstance(answer,str) and any(c['tool']=='read_panel_module' and c['resource']!='capabilities' for c in calls) and not any(c['status'] in {'source_unavailable','access_denied','tool_error'} for c in calls)
    results.append({'case':name,'passed':passed,'tools':calls,'answer':answer})
    (Path(__file__).resolve().parents[1]/'audit-2026-11-03/assistant-model-qa-progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'case':name,'passed':passed,'tools':len(calls)},ensure_ascii=False),flush=True)
path=Path(__file__).resolve().parents[1]/'audit-2026-11-03/assistant-model-qa.json'
path.write_text(json.dumps({'synthetic_data_only':True,'confirmed_operations':0,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(not all(x['passed'] for x in results))
