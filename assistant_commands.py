"""Explicit panel command catalog. Models never choose URLs or SQL.

Preparation validates against the real route body schema. Execution goes through
the same authenticated HTTP route and middleware as the manual panel.
"""
from datetime import date
from decimal import Decimal
from urllib.parse import quote, urlencode
from uuid import UUID, uuid4
import hashlib
import json
import re
import requests
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from db import engine
from operations import create_token, role_has_module_permission
from target_schema import PERSON_TARGET_FIELDS, normalize_person_target, validate_target_person


MANAGERS={'ceo','sales_manager'}
FINANCE={'ceo','finance'}
CATALOG_ROLES=MANAGERS|FINANCE


def command(label,module,method,path,roles=MANAGERS,table=None,key=None,fields=None,required=(),snapshot=None,db_key='id'):
    return dict(label=label,module=module,method=method,path=path,roles=roles,
                table=table,key=key,fields=fields,required=list(required),snapshot=snapshot,db_key=db_key)


COMMANDS={
 'daily_report_submit':command(
     'ثبت گزارش روزانه و در صورت درخواست کار پیگیری؛ مبلغ‌ها به ریال',
     'daily-reports','POST','/operations/submit-daily-report',MANAGERS|{'visitor','salesperson'},
     fields=['salesperson_id','assigned_user_id','customer_id','customer_name','visits_count','orders_count',
             'reported_sales_amount','reported_collections_amount','followup_task','summary','raw_text'],
     required=['summary','raw_text']),
 'kerman_customer_create':command(
     'افزودن مشتری محلی کرمان','kerman-bases','POST','/kerman/customers/add',
     fields=['name','customer_type','city','phone','medical_system_code','guild_license_code','latitude','longitude'],
     required=['name','customer_type']),
 'monthly_plan_create':command('تهیهٔ پیش‌نویس برنامهٔ ماهانهٔ چندپایگاهی','map','POST','/monthly-visit-plans',CATALOG_ROLES|{'visitor','salesperson'}),
 'monthly_plan_submit':command('ارسال برنامهٔ ماهانه برای تأیید مدیرعامل','map','POST','/monthly-visit-plans/{ident}/submit',CATALOG_ROLES|{'visitor','salesperson'}),
 'monthly_plan_review':command('تأیید یا برگشت برنامهٔ ماهانه','map','POST','/monthly-visit-plans/{ident}/review',{'ceo'}),
 'monthly_plan_workday':command('تطبیق اجرای برنامه با کارکرد حقوق','map','POST','/monthly-visit-plans/{ident}/workday-review',{'ceo'}),
 'crm_create_followup':command('ثبت پیگیری مشتری','crm','POST','/crm/interactions',CATALOG_ROLES|{'visitor','salesperson'},fields=['customer_name','visitor_name','interaction_type','product_discussed','notes','status','next_followup_date','followup_time'],required=['customer_name','interaction_type','product_discussed']),
 'crm_change_stage':command('تغییر مرحلهٔ پیگیری مشتری','crm','PATCH','/crm/interactions/{interaction_id}/status',CATALOG_ROLES|{'visitor','salesperson'},'customer_interactions','interaction_id',fields=['status'],required=['status']),
 'campaign_decide_proposal':command('تأیید یا رد پیشنهاد کمپین','campaigns','POST','/campaigns/ai/decide',fields=['suggestion_id','action'],required=['suggestion_id','action']),
 'payroll_record_fact':command('ثبت کارکرد یا پاداش مستند پرسنل','compensation','POST','/api/compensation/payroll/{salesperson_id}/facts',CATALOG_ROLES,fields=['event_date','event_key','kind','amount','quantity','product_id','brand','source_note','produced','edited','published'],required=['event_date','event_key','kind','source_note']),
 'payroll_verify_source':command('تأیید یا رفع تأیید منبع محاسبهٔ حقوق','compensation','POST','/api/compensation/payroll/{salesperson_id}/sources',CATALOG_ROLES,fields=['source','complete','note'],required=['source','complete','note']),
 'payroll_approve':command('تأیید فیش حقوقی پس از تطبیق کارکرد','compensation','POST','/api/compensation/payroll/{salesperson_id}/approve',CATALOG_ROLES,fields=['additions','deductions','note','expected_rule_version','expected_facts_version'],required=['note']),
 'base_create':command('تعریف پایگاه محلی','kerman-bases','POST','/crud/kerman_bases_manual',fields=['name','city','address','phone','type'],required=['name','city','address','type']),
 'base_update':command('اصلاح مشخصات پایگاه محلی','kerman-bases','PUT','/crud/kerman_bases_manual/{row_id}',MANAGERS,'kerman_bases_manual','row_id',fields=['name','city','address','phone','type']),
 'catalog_update_product':command('اصلاح قیمت، موجودی و وضعیت کالا','catalog','PATCH','/catalog/products/{product_id}',CATALOG_ROLES,'products','product_id'),
 'catalog_add_batch':command('ثبت بچ و تاریخ انقضای کالا','catalog','POST','/catalog/products/{product_id}/batches',CATALOG_ROLES),
 'catalog_link_channel':command('نگاشت کالا به کانال فروش','catalog','POST','/catalog/products/{product_id}/channels',CATALOG_ROLES),
 'catalog_reserve':command('رزرو موجودی محلی','catalog','POST','/catalog/products/{product_id}/reservations',CATALOG_ROLES),
 'catalog_restore_holoo':command('بازگرداندن مقدار کالا از آخرین منبع هلو','catalog','POST','/catalog/products/{product_id}/restore-holoo',CATALOG_ROLES,'products','product_id'),
 'inventory_update_policy':command(
     'ذخیره سیاست موجودی کالا با واحد تأییدشده و نسخه فعلی سیاست',
     'catalog','POST','/catalog/intelligence/policies/{erp_code}',CATALOG_ROLES,
     fields=['expected_revision','lead_days','review_days','safety_units','minimum_order',
             'pack_units','units_confirmed','source_note'],
     required=['expected_revision']),
 'inventory_order_create':command(
     'ثبت پیشنهاد خرید موجودی از تحلیل مستند انبار؛ بدون ارسال به تأمین‌کننده',
     'catalog','POST','/catalog/intelligence/orders',CATALOG_ROLES,
     fields=['erp_code','snapshot_id','policy_revision','window_days']),
 'inventory_order_review':command('بررسی پیش‌نویس درخواست خرید انبار','catalog','POST','/catalog/intelligence/orders/{order_id}/review',FINANCE,'inventory_order_drafts','order_id'),
 'treasury_create_account':command('ایجاد حساب بانک یا صندوق','treasury','POST','/treasury/accounts',FINANCE),
 'treasury_update_account':command('اصلاح مانده و ذخیرهٔ حساب','treasury','PATCH','/treasury/accounts/{account_id}',FINANCE,'cash_accounts','account_id'),
 'treasury_deactivate_account':command('غیرفعال کردن حساب','treasury','DELETE','/treasury/accounts/{account_id}',FINANCE,'cash_accounts','account_id'),
 'treasury_create_document':command('ثبت سند دریافتنی یا پرداختنی محلی','treasury','POST','/treasury/documents',FINANCE),
 'treasury_document_status':command('تغییر وضعیت سند مالی','treasury','PATCH','/treasury/documents/{document_id}/status',FINANCE,'financial_documents','document_id'),
 'treasury_create_expense':command('ثبت هزینهٔ ثابت','treasury','POST','/treasury/fixed-expenses',FINANCE),
 'treasury_update_expense':command('اصلاح هزینهٔ ثابت','treasury','PATCH','/treasury/fixed-expenses/{expense_id}',FINANCE,'fixed_expenses','expense_id'),
 'treasury_deactivate_expense':command('غیرفعال کردن هزینهٔ ثابت','treasury','DELETE','/treasury/fixed-expenses/{expense_id}',FINANCE,'fixed_expenses','expense_id'),
 'treasury_create_check':command('ثبت چک محلی','treasury','POST','/treasury/checks/manual',FINANCE),
 'treasury_check_status':command('اصلاح وضعیت چک','treasury','PATCH','/treasury/checks/{check_id}/status',FINANCE,'financial_documents','check_id'),
 'treasury_save_growth':command('ثبت برنامهٔ رشد سود','treasury','POST','/treasury/strategy/settings',{'ceo'}),
 'treasury_save_month':command('ثبت گزارش مالی یا بودجهٔ ماه','treasury','POST','/treasury/strategy/monthly',FINANCE),
 'treasury_save_operating_plan':command('ثبت برنامهٔ هزینه و نقدینگی','treasury','POST','/treasury/strategy/operating-plan',{'ceo'}),
 'treasury_refresh_holoo':command('درخواست دریافت خواندنی دادهٔ مالی هلو','treasury','POST','/treasury/strategy/holoo-refresh',FINANCE),
 'social_review_content':command('تأیید یا رد پیش‌نویس محتوا','social','POST','/integrations/content-calendar/{item_id}/review',MANAGERS,'social_content_calendar','item_id'),
 'online_save_channel_draft':command('ثبت تنظیمات پیش‌نویس کانال؛ بدون اتصال یا انتشار بیرونی','online-sales','PUT','/integrations/{channel}/draft'),
 'task_progress':command('ثبت پیشرفت کار خودم','tasks','PATCH','/tasks/{task_id}/progress',CATALOG_ROLES|{'visitor','salesperson'},'tasks','task_id'),
 'task_review':command('بررسی گزارش پایان کار','tasks','POST','/tasks/{task_id}/review',MANAGERS,'tasks','task_id'),
 'task_assign_campaign':command('تخصیص یک‌جای وظایف کمپین به پرسنل','tasks','POST','/tasks/campaign-assignments'),
 'personnel_create_profile':command('ایجاد پروفایل پرسنلی','manager','POST','/salespersons'),
 'personnel_update_identity':command('تغییر نام یا نام کاربری ویزیتور','manager','PATCH','/users/{user_id}',MANAGERS,'users','user_id',
     fields=['username','full_name'],snapshot=('id','username','full_name','role','salesperson_id','is_active')),
 'target_update':command('ویرایش مبلغ، پاداش، بازه، نوع یا باز و بسته‌کردن تارگت','personnel','PATCH','/targets/person-targets/{tid}',MANAGERS,'targets','tid',fields=PERSON_TARGET_FIELDS),
 'target_delete':command('حذف هدف فروش','personnel','DELETE','/targets/person-targets/{tid}',MANAGERS,'targets','tid'),
 'personnel_delete_account':command('حذف حساب کاربری پرسنل','manager','DELETE','/users/{user_id}',{'ceo'},'users','user_id',
     snapshot=('id','username','full_name','role','salesperson_id','is_active')),
 'site_product_update':command('اصلاح نمایش، دسته‌بندی یا تخفیف کالای فروشگاه','online-sales','PATCH','/site-cms/products/{code}',{'ceo'},'products','code',
     snapshot=('code','name','price'),db_key='code'),
 'site_product_set_price':command('تغییر قیمت محلی کالای فروشگاه','online-sales','POST','/site-cms/products/{code}/price',{'ceo'},'products','code',
     snapshot=('code','name','price'),db_key='code'),
 'site_banner_create':command('ایجاد بنر فروشگاه','online-sales','POST','/site-cms/banners',{'ceo'}),
 'site_banner_update':command('ویرایش یا غیرفعال کردن بنر فروشگاه','online-sales','PATCH','/site-cms/banners/{banner_id}',{'ceo'},'site_banners','banner_id'),
 'site_banner_delete':command('حذف بنر فروشگاه','online-sales','DELETE','/site-cms/banners/{banner_id}',{'ceo'},'site_banners','banner_id'),
 'site_order_status':command('تغییر وضعیت سفارش فروشگاه','online-sales','PATCH','/site-orders/{order_id}/status',MANAGERS,'site_orders','order_id',
     snapshot=('id','status')),
 'marketing_lead_create':command('ثبت مخاطب بالقوهٔ بازاریابی','online-sales','POST','/marketing/leads'),
 'marketing_refresh_demand':command('به‌روزرسانی گزارش تقاضای بازاریابی','online-sales','POST','/marketing/refresh-demand'),
 'marketing_generate_content':command('تولید پیش‌نویس محتوای بازاریابی','online-sales','POST','/marketing/generate-content'),
 'marketing_lead_delete':command('حذف مخاطب بالقوهٔ بازاریابی','online-sales','DELETE','/marketing/leads/{lead_id}',MANAGERS,'marketing_leads','lead_id',
     snapshot=('id','name','city','status')),
 'marketing_schedule_content':command('انتقال محتوای بازاریابی به تقویم','online-sales','POST','/marketing/content/{item_id}/to-calendar',MANAGERS,'marketing_content','item_id',
     snapshot=('id','title')),
 'route_physician_create':command('ثبت پزشک در فهرست برنامه‌ریزی مسیر','manager','POST','/route-builder/physicians'),
 'route_physician_delete':command('حذف پزشک از فهرست برنامه‌ریزی مسیر','manager','DELETE','/route-builder/physicians/{physician_id}',MANAGERS,'physicians','physician_id',
     snapshot=('id','name','city','specialty')),
 'campaign_create':command('ایجاد کمپین فروش','campaigns','POST','/campaigns',fields=['title','description','starts_at','ends_at','target_amount','reward_type','reward_value','reward_note'],required=['title','starts_at','ends_at','target_amount','reward_type','reward_value']),
 'campaign_close':command('بستن کمپین','campaigns','POST','/campaigns/close',fields=['campaign_id'],required=['campaign_id']),
 'map_assign_route':command('تعیین مسیر ویزیت پرسنل','map','POST','/api/compensation/visit-routes',fields=['user_id','source','base_id','visit_date','stop_order','note'],required=['user_id','source','base_id','visit_date']),
 'map_delete_route':command('حذف برنامهٔ مسیر','map','DELETE','/api/compensation/visit-routes/{route_id}',MANAGERS,'visit_route_assignments','route_id'),
 'base_delete':command('حذف پایگاه محلی','kerman-bases','DELETE','/crud/kerman_bases_manual/{row_id}',MANAGERS,'kerman_bases_manual','row_id'),
 'map_set_base_location':command('اصلاح موقعیت مرجع پایگاه با مختصات واقعی','map','PUT','/api/compensation/bases/{source}/{base_id}/location',fields=['lat','lng','accuracy_m','visit_radius_m'],required=['lat','lng']),
 'map_assign_portfolio':command('انتساب پایگاه به ویزیتور','map','POST','/api/compensation/base-portfolios'),
 'map_review_base':command('بررسی پیشنهاد پایگاه','map','POST','/api/compensation/base-proposals/{proposal_id}/review',MANAGERS,'base_proposals','proposal_id'),
 'map_review_checkin':command('بررسی حضور ثبت‌شده در پایگاه','map','POST','/api/compensation/base-checkins/{checkin_id}/review',MANAGERS,'base_checkins','checkin_id',fields=['decision','note'],required=['decision','note']),
 'proforma_create':command('ثبت پیش‌فاکتور و رزرو محلی؛ بدون ارسال به هلو','proformas','POST','/operations/proformas',CATALOG_ROLES|{'visitor','salesperson'}),
 'proforma_generate_export':command('ساخت فایل خروجی پیش‌فاکتور برای تاریخ منتخب','proformas','POST','/operations/proformas/exports/generate',fields=['date']),
 'training_create':command('ساخت پیش‌نویس دورهٔ آموزشی','tasks','POST','/training/programmes',{'ceo'}),
 'training_generate':command('تولید دوره از منابع منتخب','tasks','POST','/training/generate',{'ceo'}),
 'training_publish':command('انتشار دوره و تخصیص به فراگیران منتخب','tasks','POST','/training/programmes/{ident}/publish',{'ceo'},'training_programmes','ident',
     snapshot=('id','owner_id','title','digest','state')),
 'proforma_approve':command('تأیید داخلی پیش‌فاکتور','proformas','POST','/operations/proformas/{proforma_id}/approve',MANAGERS,'proforma_invoices','proforma_id'),
 'proforma_reject':command('رد پیش‌فاکتور و آزادسازی رزرو','proformas','POST','/operations/proformas/{proforma_id}/reject',MANAGERS,'proforma_invoices','proforma_id'),
 'proforma_cancel':command('لغو پیش‌فاکتور و آزادسازی رزرو','proformas','POST','/operations/proformas/{proforma_id}/cancel',CATALOG_ROLES|{'visitor','salesperson'},'proforma_invoices','proforma_id'),
}

for entity,label,module in [('customers','مشتری','customers'),('products','کالا','catalog'),('targets','تارگت','personnel'),('batches','بچ و انقضا','catalog'),('sales-assignments','انتساب فروش','personnel')]:
    COMMANDS['enter_'+entity.replace('-','_')]=command('ورود یا اصلاح '+label,module,'ENTRY',entity,MANAGERS if entity=='targets' else CATALOG_ROLES)


class CommandPayload(BaseModel):
    model_config=ConfigDict(extra='forbid')
    body:dict=Field(default_factory=dict)
    path_params:dict=Field(default_factory=dict)
    query_params:dict=Field(default_factory=dict)


def authorize(name,user):
    spec=COMMANDS.get(name)
    if not spec:raise HTTPException(422,'این عملیات اجرایی پشتیبانی نمی‌شود.')
    role=user.get('role')
    permission = 'can_delete' if spec['method'] == 'DELETE' else 'can_write'
    if not user.get('id') or role not in spec['roles'] or not role_has_module_permission(role,spec['module'],permission):
        raise HTTPException(403,'مجوز اجرای این عملیات فعال نیست.')
    return spec


def panel_routes(items):
    for route in items:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, 'original_router'):
            yield from panel_routes(route.original_router.routes)


def route_for(spec):
    from api import app
    route_path=spec['path'].replace('/crud/kerman_bases_manual','/crud/{table}')
    for route in panel_routes(app.routes):
        if isinstance(route,APIRoute) and route.path==route_path and spec['method'] in route.methods:
            return route
    raise HTTPException(503,'مسیر عملیاتی پنل آماده نیست.')


def catalog(user,module=None,operation=None):
    module={'targets':'personnel','contracts':'compensation','inventory':'catalog','customers':'customers','social_calendar':'social',
            'site-cms':'online-sales','marketing':'online-sales','route-builder':'manager'}.get(module,module)
    if operation in COMMANDS:module=COMMANDS[operation]['module']
    if operation and operation not in COMMANDS:
        return {'status':'unknown_operation','message':'نام عملیات را حدس نزن؛ از فهرست زیر انتخاب و ساختار دقیق آن را دریافت کن.',
                'operations':catalog(user,module)['operations']}
    result=[]
    for name,spec in COMMANDS.items():
        if module and module!=spec['module'] or operation and operation!=name:continue
        try:authorize(name,user)
        except HTTPException:continue
        item={'operation':name,'label':spec['label'],'module':spec['module'],
              'path_parameters':re.findall(r'{(\w+)}',spec['path']),'payload_shape':{'body':'اطلاعات عملیات','path_params':'شناسه‌های رکورد'},'confirmation_required':True}
        if operation:
            if spec['method']=='ENTRY':
                from data_entry import SPECS
                fields=SPECS[spec['path']]['fields']
                item['body_schema']={'type':'object','required':['unit','rows'],'additionalProperties':False,'properties':{
                    'unit':{'type':'string','enum':['IRR','TOMAN']},'rows':{'type':'array','minItems':1,'maxItems':500,
                    'items':{'type':'object','additionalProperties':False,'required':[f[0] for f in fields if f[3]],
                    'properties':{key:{'description':label,'type':['string','number'] if kind not in {'text','date'} else 'string'} for key,label,kind,_ in fields}}}}}
                item['payload_example']={'body':{'unit':'TOMAN','rows':[{key:('شناسهٔ واقعی از فهرست پرسنل' if key=='salesperson_id' else label) for key,label,_,needed in fields if needed or key=='salesperson_id'}]},'path_params':{}}
            else:
                route=route_for(spec)
                model=route.body_field.field_info.annotation if route.body_field else None
                item['body_schema']=model.model_json_schema() if isinstance(model,type) and issubclass(model,BaseModel) else {'fields':spec['fields'] or [],'required':spec['required']}
                if isinstance(model, type) and issubclass(model, BaseModel) and spec['fields'] is not None:
                    schema = item['body_schema']
                    schema['properties'] = {key: value for key, value in schema['properties'].items() if key in spec['fields']}
                    schema['required'] = sorted(set(schema.get('required', [])) & set(spec['fields']) | set(spec['required']))
                    schema['additionalProperties'] = False
                item['query_parameters']=[{'name':f.name,'required':f.field_info.is_required()} for f in route.dependant.query_params]
        result.append(item)
    return {'operations':result,'notes':['شناسه را از منابع مجاز بخوان؛ نام مبهم را سؤال کن.','مبالغ مدل‌های مالی ریال هستند. ورود گروهی واحد صریح دارد.','ورود رمز، بارگذاری فایل، ضبط صوت و ثبت موقعیت زنده در فرم بومی انجام می‌شود.','این عملیات ارسال مالی به هلو یا انتشار بیرونی محتوا انجام نمی‌دهند.']}


def path_for(spec,params):
    expected=set(re.findall(r'{(\w+)}',spec['path']))
    if set(params)!=expected:raise HTTPException(422,'شناسه‌های مسیر کامل یا معتبر نیستند.')
    clean={}
    for key,value in params.items():
        if key=='source':
            if value not in {'pharmacies','cosmetics_shops','kerman_bases_manual'}:raise HTTPException(422,'نوع پایگاه معتبر نیست.')
        elif key=='channel':
            from integrations import CHANNELS
            if value not in CHANNELS:raise HTTPException(422,'کانال معتبر نیست.')
        elif key in {'code', 'erp_code'}:
            max_length = 200 if key == 'erp_code' else 80
            if not isinstance(value, str) or not re.fullmatch(r'[\w.+ -]+', value) or len(value) > max_length or value in {'.', '..'}:
                raise HTTPException(422,'کد کالا معتبر نیست.')
            value = quote(value, safe='')
        elif key == 'ident' and spec['path'].startswith('/training/programmes/'):
            try:
                value = str(UUID(value))
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(422, 'شناسهٔ دوره معتبر نیست.') from None
        elif type(value) is not int or value<=0:raise HTTPException(422,'شناسه باید عدد مثبت و واقعی باشد.')
        clean[key]=value
    return spec['path'].format(**clean)


def before_state(spec,params,user):
    if not spec['table']:return None
    with engine.connect() as conn:
        columns = ', '.join(spec['snapshot']) if spec.get('snapshot') else '*'
        row=conn.execute(text(f"SELECT {columns} FROM {spec['table']} WHERE {spec.get('db_key', 'id')}=:id"),{'id':params[spec['key']]}).mappings().first()
        product_meta = None
        if row and spec['path'] == '/site-cms/products/{code}':
            product_meta = conn.execute(text('SELECT site_category, image_url, hidden, discount_price_irr FROM cms_product_meta WHERE code=:code'),
                                        {'code':params['code']}).mappings().first()
    if not row:raise HTTPException(404,'رکورد موردنظر پیدا نشد.')
    if spec['module']=='tasks' and user['role'] not in MANAGERS and row['assigned_to']!=user['id']:
        raise HTTPException(403,'این کار متعلق به شما نیست.')
    if spec['module']=='proformas' and user['role'] not in MANAGERS and row.get('salesperson_id')!=user.get('salesperson_id'):
        raise HTTPException(403,'این پیش‌فاکتور متعلق به شما نیست.')
    if spec['module']=='crm' and user['role'] not in MANAGERS and row.get('owner_user_id')!=user['id']:
        raise HTTPException(403,'این پیگیری متعلق به شما نیست.')
    if spec['table']=='users' and user['role'] != 'ceo' and row['role'] not in {'visitor','salesperson'}:
        raise HTTPException(403,'تغییر حساب مدیریتی فقط در دسترسی مدیرعامل است.')
    if spec['table'] == 'training_programmes' and row['owner_id'] != user['id']:
        raise HTTPException(404, 'دوره متعلق به این حساب پیدا نشد.')
    result = dict(row)
    if product_meta is not None:
        result['storefront'] = dict(product_meta)
    return jsonable_encoder(result)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def validate_dict(name,body):
    if name == 'daily_report_submit' and not all(isinstance(body[key], str) and body[key].strip() for key in ('summary', 'raw_text')):
        raise HTTPException(422, 'متن گزارش و خلاصه لازم است.')
    if name == 'kerman_customer_create':
        if not isinstance(body['name'], str) or not body['name'].strip() or body['customer_type'] not in ('pharmacy','doctor','cosmetics_shop'):
            raise HTTPException(422, 'نام و نوع معتبر مشتری لازم است.')
        lat, lng = body.get('latitude'), body.get('longitude')
        if lat is not None or lng is not None:
            try:
                if not -90 <= float(lat) <= 90 or not -180 <= float(lng) <= 180:
                    raise ValueError()
            except (TypeError, ValueError):
                raise HTTPException(422, 'عرض و طول جغرافیایی معتبر لازم است.') from None
    if name=='campaign_create':
        try:
            if not str(body['title']).strip() or len(body['title'])>200 or date.fromisoformat(body['starts_at'])>date.fromisoformat(body['ends_at']):raise ValueError()
            for key in ('target_amount','reward_value'):
                v=Decimal(str(body[key]))
                if not v.is_finite() or v<0 or v>10**15:raise ValueError()
            if body['reward_type'] not in {'fixed','percent','percentage'}:raise ValueError()
        except (ValueError,TypeError,KeyError):raise HTTPException(422,'عنوان، بازه و مبالغ کمپین معتبر لازم است.') from None
    if name=='map_assign_route':
        try:
            date.fromisoformat(body['visit_date'])
            if any(type(body[k]) is not int or body[k]<=0 for k in ('user_id','base_id')) or body['source'] not in {'pharmacies','cosmetics_shops','kerman_bases_manual'}:raise ValueError()
        except (ValueError,TypeError,KeyError):raise HTTPException(422,'اطلاعات مسیر معتبر نیست.') from None
    if name=='map_set_base_location':
        try:
            lat,lng=float(body['lat']),float(body['lng'])
            if not -90<=lat<=90 or not -180<=lng<=180:raise ValueError()
            if body.get('accuracy_m') is not None and not 0<=float(body['accuracy_m'])<=100:raise ValueError()
        except (ValueError,TypeError,KeyError):raise HTTPException(422,'مختصات و دقت معتبر لازم است.') from None
    if name=='campaign_close' and (type(body.get('campaign_id')) is not int or body['campaign_id']<=0):raise HTTPException(422,'کمپین معتبر لازم است.')


def prepare(name,payload,user):
    spec=authorize(name,user)
    p=CommandPayload.model_validate(payload)
    if name == 'personnel_delete_account' and p.path_params.get('user_id') in {1, user['id']}:
        raise HTTPException(403, 'حذف حساب خودتان یا مدیرعامل اصلی مجاز نیست.')
    if spec['method']=='ENTRY':
        from data_entry import ManualInput,manual_preview
        if p.path_params or p.query_params:raise HTTPException(422,'ورود گروهی پارامتر مسیر ندارد.')
        entry=ManualInput.model_validate(p.body)
        preview=manual_preview(spec['path'],entry,user)
        return {'body':entry.model_dump(mode='json'),'path_params':{},'_batch_id':preview['id']}, {'display':{'operation':spec['label']},'entry_preview':preview}
    path_for(spec,p.path_params)
    route=route_for(spec)
    fields={f.name:f for f in route.dependant.query_params}
    if set(p.query_params)-set(fields):raise HTTPException(422,'پارامتر ناشناختهٔ عملیات.')
    query={}
    for key,field in fields.items():
        if field.field_info.is_required() and key not in p.query_params:raise HTTPException(422,'پارامتر لازم مشخص نشده است: '+key)
        if key in p.query_params:
            value,errors=field.validate(p.query_params[key],{},loc=('query',key))
            if errors:raise HTTPException(422,'پارامتر معتبر نیست.')
            query[key]=value
    if route.body_field:
        model=route.body_field.field_info.annotation
        fields=set(model.model_fields) if isinstance(model,type) and issubclass(model,BaseModel) else set(spec['fields'] or [])
        if spec['fields'] is not None:
            fields &= set(spec['fields'])
        if set(p.body)-fields or any(key not in p.body for key in spec['required']):raise HTTPException(422,'اطلاعات عملیات ناقص است یا فیلد ناشناخته دارد.')
        body_input = p.body
        if name == 'inventory_order_create':
            body_input = {**p.body, 'submission_key': str(uuid4())}
        validated,errors=route.body_field.validate(body_input,{},loc=('body',))
        if errors:raise HTTPException(422,'ساختار اطلاعات با فرم پنل سازگار نیست.')
        body=jsonable_encoder(validated, exclude_unset=True)
        validate_dict(name,body)
        if name == 'daily_report_submit':
            if user['role'] in MANAGERS:
                if not body.get('salesperson_id'):
                    raise HTTPException(422, 'پروفایل پرسنل را مشخص کنید.')
            else:
                if not user.get('salesperson_id'):
                    raise HTTPException(403, 'حساب شما به پروفایل پرسنل متصل نیست.')
                body['salesperson_id'] = user['salesperson_id']
                body['assigned_user_id'] = user['id']
            if body.get('followup_task') and not role_has_module_permission(user['role'], 'tasks', 'can_write'):
                raise HTTPException(403, 'مجوز ساخت کار پیگیری ندارید.')
            body['submission_key'] = str(validated.submission_key)
        if name == 'monthly_plan_create':
            from monthly_visit_plans import validate_draft
            with engine.connect() as conn:
                validate_draft(conn, validated, user)
    else:
        if p.body:raise HTTPException(422,'این عملیات بدنهٔ اطلاعاتی ندارد.')
        body={}
    state=before_state(spec,p.path_params,user)
    if name == 'target_update':
        body = normalize_person_target(body, existing=state)
        if body.get('salesperson_id') is not None:
            with engine.connect() as conn:
                validate_target_person(conn, body)
    return {'body':body,'path_params':p.path_params,'query_params':query}, {'before':state,'before_hash':fingerprint(state),'display':{'operation':spec['label']}}


def dispatch(spec,path,body,user):
    with engine.connect() as conn:
        actor=conn.execute(text('SELECT id,role,salesperson_id,password_version,is_active FROM users WHERE id=:id'),{'id':user['id']}).mappings().first()
    if not actor or not actor['is_active'] or actor['role']!=user['role']:
        raise HTTPException(403,'حساب یا نقش کاربر پس از پیشنهاد تغییر کرده است.')
    session=requests.Session();session.trust_env=False
    response=session.request(spec['method'],'http://127.0.0.1:8000'+path,
        headers={'Authorization':'Bearer '+create_token(dict(actor))},json=body or None,timeout=45,allow_redirects=False)
    if not 200<=response.status_code<300:
        # The caller marks this proposal for review: timeout/error is never retried.
        try:detail=response.json().get('detail','عملیات پنل موفق نبود.')
        except (ValueError,AttributeError):detail='عملیات پنل موفق نبود.'
        raise HTTPException(response.status_code if 400<=response.status_code<600 else 502,detail)
    return response.json()


def execute(name,payload,baseline,user):
    spec=authorize(name,user)
    if spec['method']=='ENTRY':
        from data_entry import commit,Confirm
        return commit(spec['path'],payload['_batch_id'],Confirm(confirm=True),user)
    path=path_for(spec,payload['path_params'])
    if payload.get('query_params'):path+='?'+urlencode(payload['query_params'])
    if fingerprint(before_state(spec,payload['path_params'],user))!=baseline.get('before_hash'):
        raise HTTPException(409,'رکورد پس از پیش‌نمایش تغییر کرده؛ پیشنهاد تازه لازم است.')
    return dispatch(spec,path,payload['body'],user)
