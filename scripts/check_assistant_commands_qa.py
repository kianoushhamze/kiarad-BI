"""Exercise real command handlers in the dedicated synthetic database only."""
from pathlib import Path
import sys,json
from datetime import date,datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from fastapi import HTTPException
from db import engine
from config import DB_CONFIG
from operations import create_token
import assistant_operations as actions
from assistant_commands import dispatch,COMMANDS

assert DB_CONFIG['database']=='kiarad_assistant_qa_20261103','Refuse business database'
root=Path(__file__).resolve().parents[1]
with engine.connect() as conn:
    user=dict(conn.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
    pid=conn.execute(text("SELECT id FROM products WHERE code='QA-ONLY-P'")).scalar_one()
    cid=conn.execute(text("SELECT id FROM customers WHERE code='QA-ONLY-C'")).scalar_one()

results=[]; proposals=[]
run_key=__import__('uuid').uuid4().hex[:8]
def run(name,body=None,params=None,query=None):
    try:
        body=dict(body or {})
        for key in ('batch_code','external_id','external_order_id','event_key'):
            if body.get(key):body[key]=str(body[key])+'-'+run_key
        payload={'body':body or {},'path_params':params or {},'query_params':query or {}}
        proposed=actions.prepare({'operation':name,'payload':payload},user)
        ident=proposed['proposal_id'];proposals.append(ident)
        response=actions.confirm_proposal(ident,actions.Confirmation(confirm=True),user)
        replay=actions.confirm_proposal(ident,actions.Confirmation(confirm=True),user)
        assert replay.get('reused') is True
        results.append({'operation':name,'passed':True,'replay_protected':True})
        return response['receipt']
    except Exception as error:
        results.append({'operation':name,'passed':False,'error':str(getattr(error,'detail',error))[:500]})
        return {}

run('catalog_update_product',{'price':110000,'price2':130000},{'product_id':pid})
run('catalog_add_batch',{'batch_code':'QA-BATCH-1','expiry_date':'2027-12-31','quantity':10},{'product_id':pid})
run('catalog_link_channel',{'channel':'digikala','external_id':'QA-ONLY-EXTERNAL','is_active':False},{'product_id':pid})
run('catalog_reserve',{'channel':'qa','external_order_id':'QA-ORDER-2','quantity':1},{'product_id':pid})
account=run('treasury_create_account',{'name':'حساب تست مستقل','account_type':'cash','current_balance':1000000,'minimum_reserve':1000})
if account.get('id'):
    run('treasury_update_account',{'current_balance':1200000},{'account_id':account['id']})
expense=run('treasury_create_expense',{'title':'هزینه تست مستقل','amount':10000,'due_day':5})
if expense.get('id'):
    run('treasury_update_expense',{'amount':11000},{'expense_id':expense['id']})
document=run('treasury_create_document',{'document_type':'payable','counterparty':'طرف حساب تست','amount':20000,'due_date':'2026-11-10'})
if document.get('id'):run('treasury_document_status',{'status':'settled'},{'document_id':document['id']})
check=run('treasury_create_check',{'check_type':'receivable','counterparty':'طرف حساب تست','amount':5000,'due_date':'1405/08/20','reference_number':'QA-ONLY-CHECK'})
if check.get('check_id'):run('treasury_check_status',{'status':'cleared'},{'check_id':check['check_id']})
run('online_save_channel_draft',{'account_label':'کانال آزمایشی','notes':'تنظیم آزمایشی؛ اتصال بیرونی ندارد'},{'channel':'digikala'})
content=actions.prepare({'operation':'create_content_draft','payload':{'channel':'instagram','title':'محتوای تست مستقل','body':'صرفاً آزمایش؛ منتشر نمی‌شود','scheduled_at':'2026-11-05T10:00:00+03:30'}},user)
try:
    cr=actions.confirm_proposal(content['proposal_id'],actions.Confirmation(confirm=True),user)['receipt']
    results.append({'operation':'create_content_draft','passed':True})
    run('social_review_content',{'decision':'approved','note':'تأیید تست؛ انتشار بیرونی خاموش'},{'item_id':cr['item']['id']})
except Exception as error:results.append({'operation':'create_content_draft','passed':False,'error':str(error)[:200]})
run('personnel_create_profile',{'name':'پرسنل تست جدید'})
base=run('base_create',{'name':'پایگاه تست مستقل','city':'کرمان','address':'نشانی تستی؛ محل واقعی نیست','type':'pharmacy'})
if base.get('id'):
    run('base_update',{'phone':'00000000000'},{'row_id':base['id']})
    run('map_set_base_location',{'lat':30.28,'lng':57.08,'accuracy_m':10},{'source':'kerman_bases_manual','base_id':base['id']})
    run('map_assign_portfolio',{'salesperson_id':user['salesperson_id'],'source':'kerman_bases_manual','base_id':base['id']})
    route=run('map_assign_route',{'user_id':user['id'],'source':'kerman_bases_manual','base_id':base['id'],'visit_date':date.today().isoformat(),'note':'QA-'+__import__('uuid').uuid4().hex})
    if route.get('id'):run('map_delete_route',params={'route_id':route['id']})
campaign=run('campaign_create',{'title':'کمپین تست مستقل','starts_at':'2026-11-01','ends_at':'2026-11-30','target_amount':100000,'reward_type':'fixed','reward_value':1000})
if campaign.get('campaign_id'):run('campaign_close',{'campaign_id':campaign['campaign_id']})
run('crm_create_followup',{'customer_name':'مشتری آزمون دستیار','visitor_name':'مدیر آزمون','interaction_type':'تماس','product_discussed':'کالای آزمون دستیار','notes':'یادداشت صرفاً تستی','next_followup_date':'2026-11-10'})
with engine.connect() as conn:interaction=conn.execute(text('SELECT MAX(id) FROM customer_interactions')).scalar()
if interaction:run('crm_change_stage',{'status':'پیگیری شد'},{'interaction_id':interaction})
proforma=run('proforma_create',{'customer_id':cid,'salesperson_id':user['salesperson_id'],'items':[{'product_id':pid,'quantity':1,'price_level':2}],'notes':'پیش‌فاکتور صرفاً تستی'})
pfid=proforma.get('id') or proforma.get('proforma_id')
if pfid:run('proforma_approve',params={'proforma_id':pfid});run('proforma_cancel',params={'proforma_id':pfid})
for entity,rows in [
 ('customers',[{'code':'QA-MANUAL-C','name':'مشتری ورود تست','credit_limit':'0'}]),
 ('products',[{'code':'QA-MANUAL-P','name':'کالای ورود تست','price':'100','price2':'120','stock':'5'}]),
 ('targets',[{'title':'تارگت ورود تست','salesperson_id':user['salesperson_id'],'target_amount':'100000','start_date':'1405/08/01','end_date':'1405/08/30'}]),
 ('batches',[{'product_code':'QA-ONLY-P','batch_code':'QA-BATCH-ENTRY','expiry_date':'1406/08/01','quantity':'5'}]),
]:run('enter_'+entity,{'unit':'TOMAN','rows':rows})
run('payroll_record_fact',{'event_date':date.today().isoformat(),'event_key':'QA-REWARD','kind':'reward','quantity':0,'amount':1000,'source_note':'پاداش کاملاً تستی در محیط جدا'},{'salesperson_id':user['salesperson_id']})
run('payroll_verify_source',{'source':'workdays','complete':True,'note':'تأیید کاملاً آزمایشی کارکرد'},{'salesperson_id':user['salesperson_id']},{'month':'1405-08'})
if account.get('id'):run('treasury_deactivate_account',params={'account_id':account['id']})
if expense.get('id'):run('treasury_deactivate_expense',params={'expense_id':expense['id']})
with engine.connect() as conn:
    staff=dict(conn.execute(text("SELECT * FROM users WHERE username='qa_visitor'")).mappings().one())
task_title='وظیفه گردش کامل '+__import__('uuid').uuid4().hex
prepared=actions.prepare({'operation':'create_task','payload':{'title':task_title,'assigned_to':staff['id']}},user)
receipt=actions.confirm_proposal(prepared['proposal_id'],actions.Confirmation(confirm=True),user)['receipt']
with engine.connect() as conn:task_id=conn.execute(text('SELECT id FROM tasks WHERE title=:title'),{'title':task_title}).scalar_one()
manager=user
user=staff
run('task_progress',{'progress':100,'status':'completed','note':'نتیجهٔ آزمایشی کار تکمیل شد'},{'task_id':task_id})
user=manager
run('task_review',{'decision':'approved','note':'نتیجهٔ آزمایشی بررسی شد'},{'task_id':task_id})
unique=__import__('uuid').uuid4().hex[:8]
target=run('enter_targets',{'unit':'IRR','rows':[{'title':'هدف حذف تست '+unique,'target_amount':1000,'start_date':'1405/08/01','end_date':'1405/08/30'}]})
if target.get('ids'):run('target_delete',params={'tid':target['ids'][0]})
with engine.begin() as conn:conn.execute(text('UPDATE customers SET credit_limit=1 WHERE id=:id'),{'id':cid})
proforma=run('proforma_create',{'customer_id':cid,'salesperson_id':user['salesperson_id'],'items':[{'product_id':pid,'quantity':1,'price_level':1}],'notes':'آزمون رد '+unique})
with engine.begin() as conn:conn.execute(text('UPDATE customers SET credit_limit=0 WHERE id=:id'),{'id':cid})
pfid=proforma.get('id') or proforma.get('proforma_id')
if pfid:run('proforma_reject',params={'proforma_id':pfid})
path=root/'audit-2026-11-03'/'assistant-commands-qa.json';path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps({'database':DB_CONFIG['database'],'production_data_changed':False,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
(root/'private_exports'/'assistant-qa-proposals.json').write_text(json.dumps({'proposals':proposals}),encoding='utf-8')
print(json.dumps({'cases':len(results),'passed':sum(x['passed'] for x in results),'failures':[x for x in results if not x['passed']]},ensure_ascii=False))
raise SystemExit(any(not r['passed'] for r in results))
