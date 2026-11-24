"""Evidence-based target pace and portfolio signals; never disciplinary findings."""
from datetime import date,datetime,timedelta
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import text
from db import engine
from iran_time import iran_today


def pace(target,actual,today):
    begin,end=target['start_date'],target['end_date']
    amount=Decimal(str(target['target_amount']))
    if not begin or not end or begin>end or not amount.is_finite() or amount<=0:return {'assessable':False,'reason':'invalid_target'}
    # Evaluate through yesterday: an unfinished working day is not a missed full day.
    through=min(end,today-timedelta(days=1));elapsed=max(0,(through-begin).days+1);days=(end-begin).days+1
    if actual is None:return {'assessable':False,'reason':'missing_or_ambiguous_sales_source'}
    actual=Decimal(str(actual))
    if not actual.is_finite():return {'assessable':False,'reason':'nonfinite_sales'}
    expected=Decimal(elapsed)/days*100;achieved=actual/amount*100;gap=expected-achieved
    return {'assessable':True,'through':through,'actual_irr':str(actual),'target_irr':str(amount),'elapsed_days':elapsed,'period_days':days,'expected_percent':str(round(expected,1)),'achieved_percent':str(round(achieved,1)),'gap_percentage_points':str(round(gap,1)),'behind_pace':elapsed>=3 and gap>=15,'basis':'linear_time_pace_not_sales_forecast','disciplinary_finding':False}


def signals(user_ids,user):
    from agent_center import ceo
    ceo(user)
    if not user_ids or len(user_ids)>50 or any(type(x) is not int or x<=0 for x in user_ids):raise HTTPException(422,'یک تا پنجاه فرد مشخص لازم است.')
    today=iran_today();items=[]
    with engine.connect() as c:
        people=c.execute(text("SELECT id,full_name,salesperson_id FROM users WHERE id=ANY(:ids) AND is_active::text IN ('1','true','t')"),{'ids':user_ids}).mappings().all()
        for person in people:
            entry={'user_id':person['id'],'full_name':person['full_name'],'salesperson_id':person['salesperson_id'],'targets':[],'coverage':None,'missing_data':[]}
            if not person['salesperson_id']:entry['missing_data'].append('انتساب فروش به فرد مشخص نشده است.');items.append(entry);continue
            targets=c.execute(text("SELECT id,title,target_amount,start_date,end_date,product_focus,target_type FROM targets WHERE salesperson_id=:sp AND status='active' AND (start_date IS NULL OR start_date<=:today) AND (end_date IS NULL OR end_date>=:cutoff) ORDER BY id DESC LIMIT 51"),{'sp':person['salesperson_id'],'today':today,'cutoff':today-timedelta(days=30)}).mappings().all()
            if len(targets)>50:entry['missing_data'].append('بیش از پنجاه هدف فعال؛ ابتدا اهداف قدیمی را تعیین تکلیف کنید.');targets=[]
            for t in targets:
                if t['target_type'] == 'تسویه':
                    entry['targets'].append({'id':t['id'],'title':t['title'],'assessable':False,'reason':'collection_evidence_required'});continue
                if not t['start_date'] or not t['end_date'] or t['start_date']>t['end_date']:
                    entry['targets'].append({'id':t['id'],'title':t['title'],'assessable':False,'reason':'missing_target_period'});continue
                # Legacy target_type describes period; explicit numeric-unit targets are not treated as money.
                if any(word in (t['target_type'] or '') for word in ('تعداد','واحد','quantity','units')):
                    entry['targets'].append({'id':t['id'],'title':t['title'],'assessable':False,'reason':'nonmonetary_target'});continue
                focus=(t['product_focus'] or '').strip();begin=t['start_date'];end=min(t['end_date']+timedelta(days=1),today);actual=None;basis='invoice_totals_recorded_IRR'
                if focus:
                    products=c.execute(text('SELECT id FROM products WHERE code=:focus OR name=:focus LIMIT 2'),{'focus':focus}).scalars().all()
                    if len(products)==1:
                        actual=c.execute(text('SELECT SUM(si.quantity*si.price) FROM sale_items si JOIN sales s ON s.id=si.sale_id WHERE s.salesperson_id=:sp AND si.product_id=:pid AND s.date>=:begin AND s.date<:end'),{'sp':person['salesperson_id'],'pid':products[0],'begin':begin,'end':end}).scalar();basis='product_gross_lines_before_invoice_discount_IRR'
                else:actual=c.execute(text('SELECT SUM(total_amount) FROM sales WHERE salesperson_id=:sp AND date>=:begin AND date<:end'),{'sp':person['salesperson_id'],'begin':begin,'end':end}).scalar()
                # SUM(NULL) remains missing: a failed/incomplete import must not become an accusation of zero sales.
                entry['targets'].append({'id':t['id'],'title':t['title'],'product_focus':focus,'sales_basis':basis,**pace(t,actual,today)})
            items.append(entry)
    from visit_coverage import coverage
    for entry in items:
        if not entry['salesperson_id']:continue
        portfolio=coverage(entry['salesperson_id'],user)['items'];due=[p for p in portfolio if p['status'] in {'overdue','due_today','never_visited'}]
        entry['coverage']={'assigned_bases':len(portfolio),'due_or_overdue_bases':len(due),'examples':[{'name':p['base_name'],'status':p['status']} for p in due[:10]],'basis':'explicit_assignments_and_verified_checkins','gps_stops_are_not_verified_visits':True}
        if not portfolio:entry['missing_data'].append('پرتفوی فعالی به فرد تخصیص داده نشده؛ پوشش قابل ارزیابی نیست.')
    return {'items':items,'as_of':today,'disciplinary_or_payroll_changes':False,'growth_guaranteed':False}
