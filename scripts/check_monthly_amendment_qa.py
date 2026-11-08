"""In-month amendments preserve past execution, payroll and route identity."""
from pathlib import Path
from datetime import datetime,time,timedelta
from uuid import uuid4
from unittest.mock import patch
import sys,json,jdatetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import DB_CONFIG
from db import engine
from sqlalchemy import text
from fastapi import HTTPException
import monthly_visit_plans as plans
assert DB_CONFIG['database']=='kiarad_assistant_qa_20261103'
tag=uuid4().hex[:8];name='نیروی ماهانه '+tag
with engine.begin() as c:
    ceo=dict(c.execute(text("SELECT * FROM users WHERE username='qa_assistant'")).mappings().one())
    sp=c.execute(text('INSERT INTO salespersons(name) VALUES(:name) RETURNING id'),{'name':name}).scalar_one()
    staff=dict(c.execute(text("INSERT INTO users(username,full_name,password_hash,role,is_active,salesperson_id,password_version,created_at) SELECT :login,:name,password_hash,'visitor',1,:sp,0,NOW() FROM users WHERE username='qa_visitor' RETURNING *"),{'login':'qa_amend_'+tag,'name':name,'sp':sp}).mappings().one())
    bases=[c.execute(text("INSERT INTO kerman_bases_manual(name,city,address,type) VALUES(:n,'کرمان','نشانی تستی مستقل','pharmacy') RETURNING id"),{'n':'پایگاه اصلاح '+tag+' '+str(i)}).scalar_one() for i in range(2)]
persian=jdatetime.date.fromgregorian(date=plans.iran_today()+timedelta(days=70));month=f'{persian.year:04d}-{persian.month:02d}'
start,_=plans.month_window(month);past=start+timedelta(days=4);future=start+timedelta(days=20);revised=start+timedelta(days=22);now=start+timedelta(days=6)
def stop(day,base,objective='هدف ویزیت تستی'):
    return {'visit_date':day,'base_source':'kerman_bases_manual','base_id':base,'stop_order':1,'objective':objective}
def draft(stops):return plans.create_draft(plans.Draft(user_id=staff['id'],month=month,stops=stops),staff)['id']
with patch.object(plans,'iran_today',return_value=start):
    old=draft([stop(past,bases[0]),stop(future,bases[1])]);plans.submit(old,staff);plans.review(old,plans.Decision(decision='approved',note='تصویب اولیهٔ برنامه تستی'),ceo)
original=plans.detail(old,ceo);past_route=original['stops'][0]['route_id'];future_route=original['stops'][1]['route_id']
with engine.begin() as c:
    c.execute(text("INSERT INTO base_checkins(salesperson_id,base_source,base_id,latitude,longitude,accuracy_m,distance_m,status,checked_in_at) VALUES(:sp,'kerman_bases_manual',:b,30,57,10,0,'verified',:t)"),{'sp':sp,'b':bases[0],'t':datetime.combine(past,time(10))})
    c.execute(text('''INSERT INTO daily_reports(salesperson_id,report_date,visits_count,new_customers_count,orders_count,lost_orders_count,reported_sales_amount,reported_collections_amount,created_at)
        VALUES(:sp,:d,1,0,0,0,0,0,NOW())'''),{'sp':sp,'d':past})
checks=[]
with patch.object(plans,'iran_today',return_value=now):
    fact=plans.review_workday(old,plans.Workday(work_date=past,credited_days=1,note='تطبیق شواهد واقعی تست و روز کارکرد'),ceo)['payroll_fact_id']
    new=draft([stop(revised,bases[1],'هدف اصلاح‌شدهٔ آینده')]);plans.submit(new,staff)
    with engine.connect() as c:assert c.execute(text('SELECT 1 FROM visit_route_assignments WHERE id=:id'),{'id':future_route}).scalar()
    checks.append('draft_does_not_replace_active_routes')
    plans.review(new,plans.Decision(decision='approved',note='تأیید اصلاح فقط آینده در میانهٔ ماه'),ceo)
    current=plans.detail(new,ceo)
    assert {s['visit_date'] for s in current['stops']}=={past,revised}
    assert next(s['route_id'] for s in current['stops'] if s['visit_date']==past)==past_route
    checks.append('past_stop_and_route_identity_preserved')
    assert plans.detail(old,ceo)['plan']['status']=='superseded'
    checks.append('old_snapshot_and_history_preserved')
    with engine.connect() as c:
        assert not c.execute(text('SELECT 1 FROM visit_route_assignments WHERE id=:id'),{'id':future_route}).scalar()
        assert c.execute(text('SELECT fact_id FROM monthly_visit_workday_reviews WHERE plan_id=:p AND work_date=:d'),{'p':new,'d':past}).scalar_one()==fact
        assert c.execute(text('SELECT COUNT(*) FROM compensation_facts WHERE salesperson_id=:sp AND kind=\'workday\''),{'sp':sp}).scalar_one()==1
    checks.extend(['only_untouched_future_route_replaced','payroll_fact_preserved_without_duplication'])
    try:plans.review_workday(new,plans.Workday(work_date=past,credited_days=1,note='تلاش دوباره برای ثبت کارکرد'),ceo)
    except HTTPException as e:assert e.status_code==409
    else:raise AssertionError('Duplicate payroll accepted')
    bad=draft([stop(now,bases[0]),stop(revised+timedelta(days=1),bases[1])]);plans.submit(bad,staff)
    try:plans.review(bad,plans.Decision(decision='approved',note='تلاش تغییر روز جاری'),ceo)
    except HTTPException as e:assert e.status_code==409
    else:raise AssertionError('Today was changed')
    assert plans.detail(new,ceo)['plan']['status']=='approved'
    checks.append('invalid_amendment_rolls_back_and_keeps_active_plan')
report={'passed':True,'checks':checks,'production_data_changed':False}
root=Path(__file__).resolve().parents[1]
(root/'audit-2026-11-03/monthly-amendment-qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'private_exports/monthly-model-fixture.json').write_text(json.dumps({'plan_id':new,'month':month,'person_name':name,'user_id':staff['id'],'username':staff['username'],'bases':bases,'tag':tag,'future_date':str(revised)},ensure_ascii=False),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
