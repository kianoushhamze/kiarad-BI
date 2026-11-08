"""End-to-end monthly planning and payroll evidence, synthetic database only."""
from pathlib import Path
from datetime import timedelta,datetime,time
from uuid import uuid4
from unittest.mock import patch
import sys,json,requests,jdatetime,os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db import engine
from sqlalchemy import text
from config import DB_CONFIG
from operations import create_token
import monthly_visit_plans as plans
assert DB_CONFIG['database']=='kiarad_assistant_qa_20261103'
with engine.connect() as c:
    ceo=dict(c.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
    staff=dict(c.execute(text("SELECT * FROM users WHERE username='qa_visitor'")).mappings().one())
with engine.begin() as c:
    sp=c.execute(text("INSERT INTO salespersons(name) VALUES('ویزیتور برنامهٔ تست مستقل') RETURNING id")).scalar_one()
    staff=dict(c.execute(text("INSERT INTO users(username,full_name,password_hash,role,is_active,salesperson_id,password_version,created_at) SELECT :name,'ویزیتور برنامهٔ تست مستقل',password_hash,'visitor',1,:sp,0,NOW() FROM users WHERE username='qa_visitor' RETURNING *"),{'name':'qa_month_'+uuid4().hex[:12],'sp':sp}).mappings().one())
today=plans.iran_today();persian=jdatetime.date.fromgregorian(date=today+timedelta(days=65));month=f'{persian.year:04d}-{persian.month:02d}'
day=jdatetime.date(persian.year,persian.month,10).togregorian()
tag=uuid4().hex[:8]
with engine.begin() as c:
    bases=[c.execute(text("INSERT INTO kerman_bases_manual(name,city,address,type) VALUES(:n,'کرمان','نشانی کاملاً تستی','pharmacy') RETURNING id"),{'n':'پایگاه برنامه '+tag+str(i)}).scalar_one() for i in range(2)]
session=requests.Session();session.trust_env=False
QA_BASE=os.getenv('KIARAD_QA_BASE_URL','http://127.0.0.1:8001')
checks=[]
def request(method,path,user,body=None,expected=200):
    response=session.request(method,QA_BASE+'/monthly-visit-plans'+path,headers={'Authorization':'Bearer '+create_token(user)},json=body,timeout=20)
    assert response.status_code==expected,(path,response.status_code,response.text[:250])
    return response.json()
body={'user_id':staff['id'],'month':month,'stops':[{'visit_date':str(day),'base_source':'kerman_bases_manual','base_id':bid,'stop_order':i+1,'objective':'ویزیت تست و ثبت گزارش'} for i,bid in enumerate(bases)]}
pid=request('POST','',staff,body,201)['id']
with engine.connect() as c:assert c.execute(text('SELECT COUNT(*) FROM monthly_visit_plan_stops WHERE plan_id=:id AND route_id IS NOT NULL'),{'id':pid}).scalar()==0
checks.append('draft_does_not_publish')
request('POST',f'/{pid}/submit',staff)
request('POST',f'/{pid}/review',staff,{'decision':'approved','note':'تلاش غیرمجاز'},403);checks.append('staff_cannot_approve')
request('POST',f'/{pid}/review',ceo,{'decision':'approved','note':'مصوبهٔ تست مستقل'})
detail=request('GET',f'/{pid}',staff);assert len(detail['stops'])==2 and all(s['route_id'] for s in detail['stops']);checks.append('ceo_publishes_all_stops')
old=pid
pid=request('POST','',staff,{**body,'note':'اصلاح برنامه پیش از شروع ماه'},201)['id']
request('POST',f'/{pid}/submit',staff)
assert request('GET',f'/{old}',staff)['plan']['status']=='approved'
request('POST',f'/{pid}/review',ceo,{'decision':'approved','note':'تأیید نسخهٔ اصلاح‌شده پیش از شروع ماه'})
assert request('GET',f'/{old}',staff)['plan']['status']=='superseded'
checks.append('revision_changes_routes_only_after_ceo_approval')
other=request('POST','',ceo,{**body,'user_id':ceo['id']},201)['id'];request('POST',f'/{other}/submit',ceo)
request('GET',f'/{other}',staff,expected=403);checks.append('staff_cannot_read_other_plan')
request('POST',f'/{other}/review',ceo,{'decision':'approved','note':'آزمون تداخل نیروها'},409);checks.append('cross_person_conflict_blocked')
review=plans.Workday(work_date=day,credited_days=1,note='تطبیق تستی تمام ویزیت‌ها و گزارش کار')
with patch.object(plans,'iran_today',return_value=day+timedelta(days=1)):
    try:plans.review_workday(pid,review,ceo)
    except Exception as error:assert getattr(error,'status_code',None)==422
    else:raise AssertionError('No-evidence workday accepted')
checks.append('no_evidence_no_workday')
with engine.begin() as c:
    for bid in bases:c.execute(text("INSERT INTO base_checkins(salesperson_id,base_source,base_id,latitude,longitude,accuracy_m,distance_m,status,checked_in_at) VALUES(:sp,'kerman_bases_manual',:b,30,57,10,0,'verified',:t)"),{'sp':staff['salesperson_id'],'b':bid,'t':datetime.combine(day,time(10))})
    c.execute(text('''INSERT INTO daily_reports(salesperson_id,report_date,visits_count,new_customers_count,orders_count,lost_orders_count,reported_sales_amount,reported_collections_amount,created_at)
        VALUES(:sp,:d,2,0,0,0,0,0,NOW())'''),{'sp':staff['salesperson_id'],'d':day})
with patch.object(plans,'iran_today',return_value=day+timedelta(days=1)):
    receipt=plans.review_workday(pid,review,ceo);assert receipt['payroll_fact_id'] and not receipt['payroll_approved']
    try:plans.review_workday(pid,review,ceo)
    except Exception as error:assert getattr(error,'status_code',None)==409
    else:raise AssertionError('duplicate workday review accepted')
checks.append('verified_workday_creates_one_payroll_fact')
checks.append('duplicate_workday_review_blocked')
with engine.connect() as c:assert c.execute(text("SELECT COUNT(*) FROM compensation_facts WHERE event_key=:key"),{'key':f'monthly-plan:{pid}:{day}'}).scalar()==1
request('POST',f'/{pid}/review',ceo,{'decision':'approved','note':'تأیید دوباره'},409);checks.append('approval_replay_blocked')
with engine.begin() as c:
    sp=c.execute(text("INSERT INTO salespersons(name) VALUES('ویزیتور آزمون روز ردشده') RETURNING id")).scalar_one()
    negative=dict(c.execute(text("INSERT INTO users(username,full_name,password_hash,role,is_active,salesperson_id,password_version,created_at) SELECT :name,'ویزیتور آزمون روز ردشده',password_hash,'visitor',1,:sp,0,NOW() FROM users WHERE username='qa_visitor' RETURNING *"),{'name':'qa_zero_'+uuid4().hex[:12],'sp':sp}).mappings().one())
negative_day=day+timedelta(days=3)
zero=request('POST','',negative,{**body,'user_id':negative['id'],'stops':[{**s,'visit_date':str(negative_day)} for s in body['stops']]},201)['id']
request('POST',f'/{zero}/submit',negative);request('POST',f'/{zero}/review',ceo,{'decision':'approved','note':'برنامهٔ تست روز ردشده'})
with patch.object(plans,'iran_today',return_value=negative_day+timedelta(days=1)):
    rejected=plans.review_workday(zero,plans.Workday(work_date=negative_day,credited_days=0,note='عدم انجام وظیفه؛ کارکرد این روز صفر است'),ceo)
with engine.connect() as c:
    assert c.execute(text('SELECT quantity FROM compensation_facts WHERE id=:id'),{'id':rejected['payroll_fact_id']}).scalar_one()==0
checks.append('zero_day_is_explicit_payroll_evidence_not_shift_fallback')
report={'passed':True,'checks':checks,'production_data_changed':False,'month':month}
(Path(__file__).resolve().parents[1]/'audit-2026-11-03/monthly-plans-qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
