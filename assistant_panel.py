"""All panel domains through fixed, authenticated, read-only API resources."""
from datetime import date
from typing import Literal

import jdatetime
import requests
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
from operations import role_has_module_permission, create_token
from iran_time import iran_today

RESOURCES={
 'monthly_visit_plans':('map','/monthly-visit-plans'),
 'monthly_visit_plan_options':('map','/monthly-visit-plans/options'),
 'monthly_visit_plan_detail':('map','/monthly-visit-plans/{plan_id}'),
 'command_center':('management','/reports/summary'),
 'sales_trend':('management','/reports/sales-trend'),
 'treasury_overview':('treasury','/treasury/overview'),
 'treasury_forecast':('treasury','/treasury/forecast'),
 'treasury_checks':('treasury','/treasury/checks/balance-sheet'),
 'treasury_strategy':('treasury','/treasury/strategy/overview'),
 'treasury_excel':('treasury','/treasury/excel/reports'),
 'debtors':('debtors','/treasury/debtors'),
 'online_channels':('online-sales','/integrations'),
 'site_products':('site-cms','/site-cms/products'),
 'site_orders':('site-cms','/site-orders/all'),
 'site_banners':('site-cms','/site-cms/banners'),
 'social_calendar':('social','/integrations/content-calendar'),
 'map_locations':('map','/operations/locations/latest'),
 'map_routes':('map','/api/compensation/visit-routes'),
 'map_checkins':('map','/api/compensation/base-checkins'),
 'map_coverage':('map','/api/compensation/visit-coverage'),
 'base_proposals':('map','/api/compensation/base-proposals'),
 'bases':('kerman-bases','/kerman/coach/bases'),
 'base_readiness':('kerman-bases','/kerman/coach/readiness'),
 'public_registry':('kerman-bases','/kerman/coach/public-registry'),
 'customers':('customers','/directory/customers'),
 'products':('catalog','/catalog/products'),
 'inventory_orders':('catalog','/catalog/intelligence/orders'),
 'holoo_status':('catalog','/holoo/status'),
 'proformas':('proformas','/operations/proformas/my'),
 'holoo_queue':('proformas','/operations/proformas/holoo-queue'),
 'campaigns':('campaigns','/campaigns'),
 'campaign_proposals':('campaigns','/campaigns/ai/pending'),
 'tasks':('tasks','/tasks'),
 'daily_reports':('daily-reports','/daily-reports'),
 'voice_reports':('voice-report','/operations/voice-reports'),
 'crm':('crm','/crm/interactions'),
 'person_targets':('personnel','/targets/person-targets'),
 'my_targets':('personnel','/targets/my-summary'),
 'personnel':('manager','/users'),
 'visitor_performance':('visitor-kpis','/operations/visitors/kpis'),
 'notifications':('assistant','/notifications'),
 'data_sources':('data-entry','/data-entry/schema'),
 'team_messages':('team-chat','/chat/messages'),
 # داشبوردها و گزارش‌های مدیریتی
 'dashboard_full':('visitor-kpis','/dashboard/full'),
 'dashboard_ceo':('management','/dashboard/ceo'),
 'dashboard_executive':('management','/dashboard/executive'),
 'dashboard_finance':('treasury','/dashboard/finance'),
 'dashboard_inventory':('catalog','/dashboard/inventory'),
 'live_ai_insights':('management','/dashboard/live-ai-insights'),
 'bi_dashboard':('management','/bi/dashboard'),
 'report_customer_scores':('management','/reports/customer-scores'),
 'report_inactive_customers':('management','/reports/inactive-customers'),
 'report_recommendations':('management','/reports/recommendations'),
 'report_target':('management','/reports/target'),
 'omni_search':('management','/search/omni'),
 'company_targets':('management','/targets/company'),
 'custom_targets':('visitor-kpis','/targets/custom-list'),
 'salespersons':('manager','/salespersons'),
 'roles':('management','/roles'),
 'role_modules':('management','/roles/all-modules'),
 'staff_performance':('management','/staff/performance'),
 'visitors_overview':('visitors','/visitors/overview'),
 # عملیات، مشتری و کالا
 'operations_customers':('proformas','/operations/customers-list'),
 'operations_products':('proformas','/operations/products-list'),
 'customer_credit':('debtors','/operations/customers/{customer_id}/credit'),
 'customer_ledger':('debtors','/operations/customers/{customer_id}/ledger'),
 'catalog_intelligence':('catalog','/catalog/intelligence'),
 'catalog_sync_runs':('catalog','/catalog/sync-runs'),
 'catalog_files':('catalog','/catalog-files'),
 'product_batches':('catalog','/catalog/products/{product_id}/batches'),
 'product_channels':('catalog','/catalog/products/{product_id}/channels'),
 'campaign_leaderboard':('campaigns','/campaigns/leaderboard'),
 'proforma_exports':('proformas','/operations/proformas/exports'),
 # هلو
 'holoo_errors':('management','/holoo/errors'),
 'holoo_history':('management','/holoo/history'),
 'holoo_payment_options':('proformas','/holoo/payment-options'),
 # حقوق، قرارداد، حضور و پایگاه
 'payroll_people':('payroll','/api/compensation/payroll-people'),
 'payroll_detail':('payroll','/api/compensation/payroll/{salesperson_id}'),
 'payroll_facts':('payroll','/api/compensation/payroll/{salesperson_id}/facts'),
 'contract_detail':('payroll','/api/compensation/contract/{salesperson_id}'),
 'contract_history':('payroll','/api/compensation/contract/{salesperson_id}/history'),
 'attendance_status':('map','/api/compensation/attendance/status'),
 'compensation_bases':('kerman-bases','/api/compensation/bases'),
 # گزارش صوتی
 'voice_customers':('voice-report','/operations/voice-customers'),
 'speech_readiness':('voice-report','/operations/speech-readiness'),
 # کرمان
 'kerman_action_plan':('kerman-bases','/kerman/action-plan/monthly'),
 'kerman_weekly_summary':('kerman-bases','/kerman/weekly-meeting-summary'),
 'kerman_customers_by_type':('kerman-bases','/kerman/customers/by-type'),
 'kerman_coach_customers':('kerman-bases','/kerman/coach/customers'),
 'plan_reconciliation':('map','/monthly-visit-plans/{plan_id}/reconciliation'),
 'task_assignees':('tasks','/tasks/assignees'),
 'task_campaign_assignments':('tasks','/tasks/campaign-assignments'),
 'task_updates':('tasks','/tasks/{task_id}/updates'),
}


MONTH_REQUIRED = {'monthly_visit_plans', 'payroll_detail'}
DASHBOARD_PERIOD_RESOURCES = {'dashboard_full', 'live_ai_insights'}


class PanelReadArgs(BaseModel):
    model_config=ConfigDict(extra='forbid')
    resource:str=Field(max_length=60)
    query:str=Field(default='',max_length=100)
    salesperson_id:int|None=Field(default=None,gt=0)
    days:int=Field(default=30,ge=1,le=365)
    month: str | None = Field(default=None, pattern=r'^14\d{2}-(0[1-9]|1[0-2])$')
    period: Literal['month', '30d', '90d'] | None = None
    up_to_date: date | None = None
    plan_id:int|None=Field(default=None,gt=0)
    customer_id:int|None=Field(default=None,gt=0)
    product_id:int|None=Field(default=None,gt=0)
    task_id:int|None=Field(default=None,gt=0)


def read_panel(args,user):
    a=PanelReadArgs.model_validate(args)
    if a.resource=='capabilities':
        return {'resources':[{'resource':key,'module':module} for key,(module,_) in RESOURCES.items()
            if user.get('role')=='ceo' or (module!='site-cms' and role_has_module_permission(user.get('role',''),module,'can_read'))],
            'note':'هر منبع با احراز هویت خود کاربر خوانده می‌شود؛ نبود دیتای اتصال، مجوز حدس آمار نیست.'}
    if a.resource not in RESOURCES:raise HTTPException(422,'منبع خواندن پشتیبانی نمی‌شود.')
    module,path=RESOURCES[a.resource]
    # Path params (plan_id, customer_id, ...) must come from real report data, never guessed.
    path_args={'plan_id':a.plan_id,'customer_id':a.customer_id,'product_id':a.product_id,
               'task_id':a.task_id,'salesperson_id':a.salesperson_id}
    consumed=set()
    import re as _re
    for name in _re.findall(r'\{(\w+)\}',path):
        value=path_args.get(name)
        if not value:
            raise HTTPException(422,f'شناسهٔ {name} را از گزارش واقعی انتخاب کنید؛ حدس زدن مجاز نیست.')
        path=path.replace('{'+name+'}',str(value));consumed.add(name)
    if user.get('role')!='ceo' and (module=='site-cms' or not role_has_module_permission(user.get('role',''),module,'can_read')):
        raise HTTPException(403,'این ماژول در دسترسی شما نیست.')
    params = {'q': a.query, 'days': a.days}
    if a.month:
        params['month'] = a.month
    elif a.resource in MONTH_REQUIRED:
        month = jdatetime.date.fromgregorian(date=iran_today())
        params['month'] = f'{month.year:04d}-{month.month:02d}'
    if a.period and a.resource in DASHBOARD_PERIOD_RESOURCES:
        params['range'] = a.period
    if a.up_to_date and a.resource == 'plan_reconciliation':
        params['up_to_date'] = a.up_to_date.isoformat()
    if a.salesperson_id and 'salesperson_id' not in consumed:
        params['salesperson_id'] = a.salesperson_id

    session=requests.Session();session.trust_env=False
    response=session.get('http://127.0.0.1:8000'+path,
        headers={'Authorization':'Bearer '+create_token(user)},
        params=params,timeout=35)
    if response.status_code!=200:
        return {'status':'access_denied' if response.status_code in {401,403} else 'source_unavailable',
                'http_status':response.status_code,'resource':a.resource,'message':'منبع خوانده نشد؛ نتیجه صفر یا موفق نیست.'}
    if len(response.content)>2*1024*1024:raise HTTPException(422,'گزارش بزرگ است؛ گزارش تخصصی محدودتر را بخوانید.')
    from assistant_reports import trim
    return {'resource':a.resource,'module':module,'source_path':path,'data':trim(response.json()),
            'note':'فهرست‌ها محدود می‌شوند؛ جمع‌زدن صفحهٔ محدود به معنی جمع کل نیست. پارامتر فیلتر فقط در صورت پشتیبانی منبع اعمال می‌شود.'}
