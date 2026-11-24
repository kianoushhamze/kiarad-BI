"""Bounded, actor-authorized read tools for the dashboard assistant.

Tool arguments never contain SQL, URLs, roles or credentials. Writes remain in
the existing authenticated forms after human review.
"""
from datetime import date, timedelta
from decimal import Decimal
import json
import logging
from typing import Literal
from urllib.parse import urlencode

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import text
from db import engine
from iran_time import iran_today, iran_month_bounds
from operations import MANAGER_ROLES, role_has_module_permission
from assistant_commands import COMMANDS
from assistant_panel import RESOURCES as PANEL_RESOURCES
from assistant_intake import BlankTargetRows, Targets, VisitCoverage

logger = logging.getLogger(__name__)


class ReportArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    section: Literal['sales', 'customers', 'team', 'tasks', 'proformas', 'routes', 'payroll', 'treasury', 'catalog', 'crm', 'daily_reports', 'campaigns', 'content', 'capabilities', 'contracts', 'attendance', 'public_registry', 'channels']
    query: str = Field(default='', max_length=100)
    days: int = Field(default=30, ge=1, le=365)
    period: Literal['rolling', 'current_jalali_month'] = 'rolling'
    salesperson_id: int | None = Field(default=None, gt=0)
    month: str | None = Field(default=None, pattern=r'^1[34]\d{2}-(0[1-9]|1[0-2])$')


class TargetArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    scope: Literal['company', 'person']
    salesperson_id: int | None = Field(default=None, gt=0)
    amount: Decimal = Field(gt=0, le=10**14)
    unit: Literal['IRR', 'toman']
    period: Literal['current_jalali_month', 'custom']
    start_date: date | None = None
    end_date: date | None = None
    title: str = Field(default='تارگت فروش', min_length=2, max_length=160)
    product_focus: str = Field(default='', max_length=150)


class ContractReviewArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    salesperson_id: int = Field(gt=0)
    description: str = Field(min_length=10, max_length=4000)


class PublicSearch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=5, max_length=500)


class CatalogSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=2, max_length=2000)


def prepare_contract_review(args, user):
    from compensation import COMPENSATION_ADMIN_ROLES
    if user.get('role') not in COMPENSATION_ADMIN_ROLES:
        raise HTTPException(403, 'تعریف قرارداد در دسترسی شما نیست.')
    a = ContractReviewArgs.model_validate(args)
    with engine.connect() as conn:
        person = conn.execute(text('SELECT name FROM salespersons WHERE id=:id'), {'id': a.salesperson_id}).scalar()
    if person is None:
        return {'status': 'person_not_found'}
    return {'status': 'review_only', 'saved': False, 'person': person,
            'review_href': '/compensation?' + urlencode({'salesperson_id': a.salesperson_id, 'assistant_description': a.description}),
            'message': 'شرح قرارداد به فرم بازبینی منتقل می‌شود؛ پیشنهاد قواعد، بررسی ابهام‌ها و تأیید نهایی در همان فرم است.'}


REPORT_TOOLS = [
    {'type':'function','function':{'name':'panel_operations','description':'فهرست عملیات اجرایی مجاز کل پنل. ابتدا بر اساس module فهرست را بخوان، سپس operation مشخص را برای ساختار دقیق body و path_params بخوان. با prepare_panel_operation پیشنهاد قابل تأیید بساز. نام و شناسه را از گزارش معتبر پیدا کن.','parameters':{'type':'object','properties':{'module':{'type':'string'},'operation':{'type':'string'}},'additionalProperties':False}}},
    {'type':'function','function':{'name':'read_contract_people','description':'پرسنل و قراردادهای پنل: نام و شناسهٔ واقعی افراد مجاز برای بررسی یا تعریف قرارداد را بخوان. از کاربر شناسهٔ داخلی نخواه؛ نام را در این فهرست تطبیق بده و در صورت ابهام سؤال کن.','parameters':{'type':'object','properties':{},'additionalProperties':False}}},
    {'type':'function','function':{'name':'read_panel_module','description':'خواندن مجاز همهٔ حوزه‌های پنل؛ خزانه، چک، پیش‌بینی، اکسل، آنلاین، تقویم فضای مجازی، نقشه و موقعیت و پوشش، پایگاه، مشتری، کالا، سفارش انبار، صف هلو، کمپین، وظایف، گزارش کار و صوت، پرسنل، تارگت، گفت‌وگوی تیم، داشبوردهای مدیریتی و اجرایی، امتیاز و سکوت مشتری، عملکرد پرسنل، خطاهای هلو، حقوق و قرارداد و حضور، برنامهٔ ماهانه و تطبیق آن. ابتدا capabilities را برای منابع قابل دسترسی بخوان. برای منابع دارای شناسه (customer_id، product_id، plan_id، task_id، salesperson_id) شناسه را از گزارش واقعی بردار؛ دورهٔ گزارش را با month (شمسی)، period برای داشبورد و up_to_date برای تطبیق ویزیت مشخص کن؛ حدس زدن مجاز نیست. فقط اطلاعات همین منبع را مبنا قرار بده؛ نبود اتصال را آمار صفر فرض نکن.',
     'parameters':{'type':'object','properties':{'resource':{'type':'string','enum':['capabilities', *PANEL_RESOURCES]},'query':{'type':'string'},'days':{'type':'integer','minimum':1,'maximum':365},'month':{'type':'string','description':'ماه شمسی با رقم انگلیسی، مانند 1405-09'},'period':{'type':'string','enum':['month','30d','90d']},'up_to_date':{'type':'string','format':'date','description':'تاریخ برش گزارش تطبیق ویزیت به میلادی (YYYY-MM-DD)'},'salesperson_id':{'type':'integer','minimum':1},'customer_id':{'type':'integer','minimum':1},'product_id':{'type':'integer','minimum':1},'plan_id':{'type':'integer','minimum':1},'task_id':{'type':'integer','minimum':1}},'required':['resource'],'additionalProperties':False}}},
    {'type':'function','function':{'name':'prepare_panel_operation',
     'description':'پیش‌نمایش عملیات با تأیید جداگانهٔ کاربر: create_task با عنوان و شناسهٔ کاربر مسئول، create_daily_report برای گزارش کار خود کاربر با تاریخ میلادی معتبر و آمار تصریح‌شده، save_contract با salesperson_id و month شمسی سال-ماه و description شامل شرایط صریح مدیر. شناسه‌ها را از گزارش واقعی بخوان؛ هیچ مبلغ، آمار، تاریخ یا مسئول را حدس نزن. قرارداد دارای ابهام ثبت نمی‌شود. این ابزار فقط پیشنهاد ذخیره می‌کند، نه عملیات نهایی.',
     'parameters':{'type':'object','properties':{'operation':{'type':'string'},'payload':{'type':'object'}},'required':['operation','payload'],'additionalProperties':False}}},
    {'type': 'function', 'function': {'name': 'prepare_contract_review',
     'description': 'انتقال شرح صریح قرارداد کاربر به فرم حقوق همان شخص برای پیشنهاد قواعد و تایید نهایی؛ بدون ذخیره یا تصویب. شناسه شخص را از گزارش تیم دریافت کن؛ نام مبهم یا نرخ نامعلوم را حدس نزن.',
     'parameters': ContractReviewArgs.model_json_schema()}},
    {'type': 'function', 'function': {'name': 'read_business_report',
     'description': 'گزارش واقعی و مجاز داشبورد: فروش و روند و کالا، مشتری، تیم و تارگت، کارها، پیش‌فاکتور، مسیر، حقوق ماه مشخص، خزانه، تحلیل انبار، پیگیری مشتری، گزارش روزانه، کمپین یا تقویم محتوا. query نام واقعی فارسی/لاتین یا کد؛ ابهام را از کاربر بپرس. گزارش غایب یا خطادار صفر نیست.',
     'parameters': ReportArgs.model_json_schema()}},
    {'type': 'function', 'function': {'name': 'prepare_target',
     'description': 'فقط پیش‌نویس تارگت با پیوند فرم بازبینی؛ چیزی ذخیره نمی‌کند. مبلغ و واحد و فرد/شرکت و بازه باید صریح از کاربر معلوم باشند. اگر هرکدام نامعلوم است ابتدا بپرس. ماه جاری شمسی با سرور محاسبه می‌شود. برای فرد ابتدا شناسهٔ یکتای واقعی را از گزارش تیم بگیر.',
     'parameters': TargetArgs.model_json_schema()}},
]

# Keep legacy form helpers callable for old clients, but present one consistent
# executable proposal path to the model instead of competing form-only tools.
REPORT_TOOLS=[tool for tool in REPORT_TOOLS if tool['function']['name'] not in {'prepare_target','prepare_contract_review'}]
for tool in REPORT_TOOLS:
    if tool['function']['name']=='read_panel_module':
        tool['function']['parameters']['properties']['month']={'type':'string','description':'ماه شمسی سال-ماه برای برنامه ماهانه مانند 1405-09'}
        tool['function']['parameters']['properties']['plan_id']={'type':'integer','minimum':1,'description':'شناسهٔ واقعی برنامه از فهرست مجاز برای تحلیل جزئیات و تطبیق عملکرد'}
    if tool['function']['name']=='panel_operations':
        tool['function']['parameters']['properties']['operation']['enum']=list(COMMANDS)
        tool['function']['parameters']['properties']['module']['enum']=sorted({s['module'] for s in COMMANDS.values()})
    if tool['function']['name']=='prepare_panel_operation':
        tool['function']['parameters']['properties']['operation']['enum']=['create_task','create_daily_report','save_contract','create_content_draft',*(name for name in COMMANDS if name != 'enter_targets')]
        tool['function']['description']='آماده‌کردن عملیات واقعی برای صفحهٔ تأیید: وظیفه، گزارش کار، قرارداد، محتوا و عملیات تمام ماژول‌ها. برای نام و ساختار عملیات جدید ابتدا panel_operations را بخوان. عملیات جدید payload شامل body، path_params و در صورت نیاز query_params دارد. تا تأیید کاربر فقط پیشنهاد ذخیره می‌شود؛ عملیات تجاری اجرا نشده است.'


# Multi-step mission tools use the same actor and never approve their own plans.
REPORT_TOOLS.extend([
    {'type':'function','function':{'name':'prepare_agent_mission','description':'ساخت برنامه چندمرحله‌ای تخصصی با حدود اختیار، بازبینی یک‌جای برنامه و رسید اجرا. برای هدف‌های ترکیبی فروش، مالی، منابع انسانی، آموزش، قرارداد و برنامه‌ریزی بلندمدت استفاده کن؛ این ابزار فقط پیش‌نویس می‌سازد.',
        'parameters':{'type':'object','properties':{'objective':{'type':'string','minLength':5,'maxLength':6000},'domains':{'type':'array','items':{'type':'string','enum':['sales','marketing','finance','hr','logistics','inventory','customer_care','legal','coordination']},'minItems':1,'maxItems':9}},'required':['objective','domains'],'additionalProperties':False}}},
    {'type':'function','function':{'name':'read_agent_missions','description':'خواندن وضعیت و نتایج مأموریت‌های متعلق به مدیر؛ انجام کار فقط با رسید واقعی گزارش می‌شود.',
        'parameters':{'type':'object','properties':{},'additionalProperties':False}}},
])

REPORT_TOOLS.extend([
    {'type': 'function', 'function': {'name': 'prepare_sales_targets',
     'description': 'پیش‌نمایش تارگت تکی یا گروهی. اگر چند برند برای یک فرد است نام فرد را در person اصلی و هر برند، نوع و مبلغش را در یک ردیف بگذار. اگر واحد مشترک فقط انتهای فهرست آمده در shared_unit بده و عبارت مبلغ هر ردیف را همان‌گونه که گفته شده نقل کن. «وصول» یا «تسویه» kind=settlement است. ماه نامعلوم در پیش‌نمایش ماه جاری است. اگر عنوانی نداده عنوان را حذف کن. واحد را تبدیل نکن و تارگت قدیمی را با درخواست تازه ادغام نکن. اگر عنوان و کالای هدف متناقض‌اند، همان مورد را بپرس.',
     'parameters': Targets.model_json_schema()}},
    {'type': 'function', 'function': {'name': 'open_target_template',
     'description': 'بازکردن فرم ورود دستی با تعداد مشخص ردیف تارگت خالی و قابل ویرایش. وقتی کاربر می‌خواهد بعداً مقادیر را خودش وارد کند این ابزار را بزن. نام و مبلغ ساختگی لازم نیست.',
     'parameters': BlankTargetRows.model_json_schema()}},
    {'type': 'function', 'function': {'name': 'prepare_visit_coverage',
     'description': 'تبدیل خواستهٔ برنامهٔ ویزیت برای یک پرسنل و شهرها به پوشش مبتنی بر پایگاه‌های واقعی. برای چند بار پوشش تمام پایگاه‌های یک شهر scope=all_bases و visits=تعداد دفعات. برای سفر به یک شهر بدون انتخاب پایگاه scope=trip. اگر کاربر پایگاه‌ها یا روزهای شمسی ماه را مشخص کرده، همان‌ها را بده؛ در غیر این صورت ابزار پوشش و کمبود اطلاعات را گزارش می‌کند. نیاز به شناسهٔ داخلی نیست.',
     'parameters': VisitCoverage.model_json_schema()}},
    {'type': 'function', 'function': {'name': 'search_public_web',
     'description': 'جست‌وجوی فقط‌خواندنی اطلاعات عمومی به‌روز خارج از پنل. پرسش را با اطلاعات عمومی و بدون دادهٔ داخلی شرکت، اطلاعات مشتری، مختصات یا رمز بنویس. نتیجه را با لینک منبع و محدودیت گزارش کن.',
     'parameters': PublicSearch.model_json_schema()}},
    {'type': 'function', 'function': {'name': 'analyze_catalog_selection',
     'description': 'گزارش موجودی، قیمت، گردش و فروش برند یا کالای شرکت با هویت واقعی. سؤال و بازهٔ کاربر را حفظ کن؛ این ابزار برای پرسش آموزشی یا اطلاعات عمومی محصول نیست.',
     'parameters': CatalogSelection.model_json_schema()}},
])

REPORT_TOOLS.extend([
 {'type':'function','function':{'name':'specialist_tools','description':'فهرست ابزار تخصصی واقعی و ساختار ورودی: سناریوی تارگت سالانه، تحلیل GPS، قرارداد مستند و آموزش. پیش‌نویس‌های نوشتنی از مسیر مأموریت بازبینی می‌شوند.','parameters':{'type':'object','properties':{},'additionalProperties':False}}},
 {'type':'function','function':{'name':'read_specialist_analysis','description':'اجرای تحلیل تخصصی خواندنی؛ هیچ پیام، تارگت، قرارداد یا وظیفه‌ای را ثبت یا ارسال نمی‌کند.','parameters':{'type':'object','properties':{'operation':{'type':'string','enum':['team_signals','target_scenarios','tracking_analytics','contract_review','training_progress','training_my_courses']},'payload':{'type':'object'}},'required':['operation','payload'],'additionalProperties':False}}}
])

def rows(conn, sql, params=None):
    return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]


def allowed(user, module):
    return user.get('role') == 'ceo' or role_has_module_permission(str(user.get('role', '')), module, 'can_read')


def trim(value, max_rows=20):
    """Bound provider payloads; never truncate a ledger and present it as a total."""
    if isinstance(value, dict):
        return {k: trim(v, max_rows) for k, v in value.items() if k not in {'phone', 'mobile', 'card_number', 'iban', 'bank_account_number', 'history'}}
    if isinstance(value, list):
        return {'rows': [trim(v, max_rows) for v in value[:max_rows]], 'total_rows': len(value), 'limited': len(value)>max_rows}
    return value


def prepare_target(args, user):
    if user.get('role') not in MANAGER_ROLES:
        raise HTTPException(403, 'تعریف تارگت فقط با مدیر است.')
    a = TargetArgs.model_validate(args)
    if a.scope == 'person' and not a.salesperson_id:
        return {'status': 'needs_information', 'missing': ['فرد موردنظر']}
    if a.scope == 'company' and a.salesperson_id is not None:
        return {'status': 'invalid_scope'}
    with engine.connect() as conn:
        person = conn.execute(text('SELECT name FROM salespersons WHERE id=:id'), {'id': a.salesperson_id}).scalar() if a.salesperson_id else None
    if a.salesperson_id and person is None:
        return {'status': 'person_not_found'}
    if a.period == 'current_jalali_month':
        begin, end = iran_month_bounds()
        end -= timedelta(days=1)
    else:
        begin, end = a.start_date, a.end_date
    if not begin or not end or begin > end or (end-begin).days > 366:
        return {'status': 'needs_information', 'missing': ['بازهٔ شروع و پایان معتبر']}
    amount_irr = a.amount * (10 if a.unit == 'toman' else 1)
    draft = {'title': a.title, 'target_amount': str(amount_irr), 'salesperson_id': a.salesperson_id,
             'start_date': begin.isoformat(), 'end_date': end.isoformat(), 'product_focus': a.product_focus,
             'period_type': 'ماهانه' if a.period == 'current_jalali_month' else 'بازهٔ مشخص', 'target_type': 'فروش', 'bonus_reward': 0, 'status': 'active'}
    href = '/person-targets?' + urlencode({'assistant_draft': json.dumps(draft, ensure_ascii=False)})
    return {'status': 'draft_only', 'saved': False, 'requires_human_review': True, 'person': person or 'شرکت',
            'draft': draft, 'amount_unit': 'IRR', 'review_href': href,
            'message': 'پیش‌نویس آماده است؛ پیوند فرم را نمایش بده. پس از بازبینی کاربر و زدن ذخیره ثبت می‌شود؛ فعلاً ثبت نشده است.'}


def read_report(a, user):
    from assistant_inventory import normalize
    a.query=normalize(a.query)
    role = str(user.get('role', ''))
    manager = role in MANAGER_ROLES
    own = user.get('salesperson_id') or -1
    if a.section == 'capabilities':
        from assistant_commands import catalog
        return {'read_sections': ['sales','customers','team','tasks','proformas','routes','payroll','treasury','catalog','crm','daily_reports','campaigns','content','contracts','attendance','public_registry','channels'],
                'role_filtered': True, 'operations':catalog(user)['operations'],
                'writes': 'عملیات موجود در فهرست با پیش‌نمایش و تأیید جداگانه اجرا می‌شوند. ارسال مالی به هلو و انتشار بیرونی مستقل‌اند.'}
    if a.section in {'contracts','attendance'}:
        if not allowed(user,'compensation' if a.section=='contracts' else 'map'):
            raise HTTPException(403,'این بخش در دسترسی شما نیست.')
        sid=a.salesperson_id or own
        if sid==-1:return {'status':'needs_information','missing':['پرسنل موردنظر']}
        from compensation import get_contract,attendance_status
        if a.section=='contracts':
            if not a.month:return {'status':'needs_information','missing':['ماه شمسی قرارداد']}
            return trim(get_contract(sid,a.month,user))
        return trim(attendance_status(sid,user))
    if a.section in {'public_registry','channels'}:
        if not manager:raise HTTPException(403,'فهرست منابع و اتصال‌ها فقط برای مدیر است.')
        if a.section=='channels':
            from integrations import list_integrations
            return trim(list_integrations(user))
        from field_intelligence import public_registry
        return trim(public_registry(q=a.query,batch='',offset=0,limit=20,user=user))
    module = {'sales':'visitors', 'customers':'customers', 'team':'visitors', 'tasks':'tasks', 'proformas':'proformas',
              'routes':'map', 'payroll':'payroll', 'treasury':'treasury', 'catalog':'catalog',
              'crm':'crm','daily_reports':'daily-reports','campaigns':'campaigns','content':'social'}[a.section]
    if not (a.section == 'catalog' and role in {'ceo','finance','sales_manager'}) and not allowed(user, module):
        raise HTTPException(403, 'این گزارش در محدودهٔ دسترسی شما نیست.')
    if a.section == 'treasury':
        if role not in {'ceo','finance'}:
            raise HTTPException(403, 'گزارش مالی شرکت در دسترسی شما نیست.')
        from treasury_strategy import strategy_overview
        value = strategy_overview(user)
        keys = ('as_of','current_month','currency','operating_plan','operating_projection','growth','projection','collections','coverage','warnings','actions','definitions','purchase_estimate','excel_estimate','approved_actuals','holoo_snapshot')
        return trim({k:value[k] for k in keys if k in value})
    if a.section == 'routes':
        from compensation import list_visit_routes
        target_user = None
        if a.query or a.salesperson_id:
            with engine.connect() as conn:
                people=rows(conn,'''SELECT u.id,sp.id AS salesperson_id,sp.name FROM users u JOIN salespersons sp ON sp.id=u.salesperson_id
                    WHERE u.is_active=1 AND sp.name ILIKE :q'''+('' if manager else ' AND u.id=:uid'),{'q':'%'+a.query+'%','uid':user['id']})
            if a.salesperson_id:
                people=[r for r in people if r['salesperson_id']==a.salesperson_id]
            if len(people)!=1:
                return {'status':'ambiguous' if people else 'not_found','candidates':people}
            target_user=people[0]['id']
        return trim(list_visit_routes(user_id=target_user, visit_date=iran_today(), user=user))
    if a.section == 'payroll':
        sid = a.salesperson_id or own
        if role not in {'ceo','finance','sales_manager'} and sid != own:
            raise HTTPException(403, 'حقوق سایر اشخاص مجاز نیست.')
        if sid == -1:
            return {'status':'needs_information','missing':['فرد موردنظر']}
        if not a.month:
            return {'status':'needs_information','missing':['ماه شمسی حقوق به شکل سال-ماه']}
        from compensation import payroll_summary
        return trim(payroll_summary(sid, a.month, user))
    today = iran_today()
    begin = iran_month_bounds(today)[0] if a.period == 'current_jalali_month' else today-timedelta(days=a.days-1)
    end = today+timedelta(days=1)
    p = {'begin':begin,'end':end,'sp':own,'q':'%'+a.query.replace('%','').replace('_','')+'%'}
    scope = '' if manager else ' AND s.salesperson_id=:sp'
    if a.section == 'sales':
        if a.query:
            return {'status':'needs_selection','message':'برای نام کالا/برند بخش catalog، برای نام مشتری بخش customers و برای نام فرد بخش team را بخوان؛ گزارش کل فروش فیلتر متنی ندارد.'}
        if a.salesperson_id:
            if not manager and a.salesperson_id!=own:
                raise HTTPException(403,'فروش سایر اشخاص مجاز نیست.')
            p['sp']=a.salesperson_id
            scope=' AND s.salesperson_id=:sp'
    with engine.connect() as conn:
        conn.execute(text('SET LOCAL statement_timeout=12000'))
        from holoo_operational_sync import operational_status
        from assistant_inventory import business_date
        metadata = {'source':'داشبورد؛ نسخهٔ همگام‌شدهٔ هلو و رکوردهای محلی', 'currency':'IRR', 'from_date':begin, 'to_date':today,
                    'period_display':{'from':business_date(begin),'to':business_date(today),'timezone':'Asia/Tehran'},
                    'scope':'company' if manager else 'only_explicitly_attributed_to_you', 'data_sync':operational_status(conn,manager),
                    'amount_definition':'فروش خالص پس از تخفیف و برگشت، بدون مالیات؛ تعداد سند شامل برگشت. نبود انتساب ویزیتور به معنای نبود عملکرد واقعی نیست.'}
        applied=metadata['data_sync'].get('snapshot_id')
        coverage=conn.execute(text("SELECT payload->>'from_date' AS from_date,payload->>'to_date' AS to_date FROM holoo_financial_snapshots WHERE id=:id"),{'id':applied}).mappings().first() if applied else None
        metadata['source_coverage']=dict(coverage) if coverage else None
        covered=bool(coverage and coverage['from_date']<=begin.isoformat() and coverage['to_date']>=today.isoformat())
        metadata['requested_period_covered_by_holoo']=covered
        metadata['coverage_note']='آمار، رکوردهای موجود سامانه است؛ بازهٔ خارج پوشش منبع، عملکرد صفر واقعی را ثابت نمی‌کند.'
        if a.section=='sales' and a.salesperson_id:
            metadata['scope']='selected_person'
            metadata['salesperson_id']=a.salesperson_id
        if a.section == 'catalog':
            from assistant_inventory import resolve_selection, inventory_answer
            products = rows(conn, '''SELECT p.id,p.code,p.name,p.stock,p.price,m.holoo_erp_code FROM products p
                LEFT JOIN holoo_entity_mappings m ON m.local_id=p.id AND m.entity_type='product' ORDER BY p.id LIMIT 5000''')
            selection = resolve_selection(a.query, products)
            if not a.query.strip():
                selection = {'status':'matched','label':'کل کالاهای مجاز','items':products}
            if selection['status'] != 'matched':
                from assistant_inventory import catalog_groups, DISPLAY
                return {**metadata, **selection, 'catalog_groups':[DISPLAY.get(k,k) for k in catalog_groups(products)]}
            if role not in {'ceo','finance','sales_manager'}:
                return {**metadata,'products':[{k:r[k] for k in ('code','name','stock','price')} for r in selection['items'][:40]],'note':'فقط موجودی و قیمت جاری؛ گردش کل شرکت در دسترسی شما نیست.'}
            from field_intelligence import load_inventory, redact_inventory
            from assistant_inventory import limit_short_window_orders
            days=(today-begin).days+1
            return {**metadata, **inventory_answer(selection,redact_inventory(limit_short_window_orders(load_inventory(conn,days),days),user),role)}
        if a.section == 'sales':
            base = ' FROM sales s WHERE s.date>=:begin AND s.date<:end'+scope
            result = {'totals':rows(conn,'SELECT COALESCE(SUM(s.total_amount),0) AS net_sales_irr,COUNT(*) AS documents'+base,p)[0],
                      'daily':rows(conn,'SELECT s.date::date AS day,SUM(s.total_amount) AS net_sales_irr'+base+' GROUP BY s.date::date ORDER BY day DESC LIMIT 90',p),
                      'top_products':rows(conn,'''SELECT p.code,p.name,SUM(si.quantity) AS net_quantity,SUM(si.quantity*si.price) AS net_sales_irr
                          FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
                          WHERE s.date>=:begin AND s.date<:end'''+scope+' GROUP BY p.id,p.code,p.name ORDER BY net_sales_irr DESC LIMIT 15',p)}
            previous_begin=begin-(end-begin)
            previous=rows(conn,'SELECT COALESCE(SUM(s.total_amount),0) AS net_sales_irr,COUNT(*) AS documents'+base,{**p,'begin':previous_begin,'end':begin})[0]
            old=previous['net_sales_irr'];current=result['totals']['net_sales_irr']
            previous_covered=bool(coverage and coverage['from_date']<=previous_begin.isoformat() and covered)
            result['comparison']={'previous_from':previous_begin,'previous_to':begin-timedelta(days=1),'previous_net_sales_irr':old,
                                  'previous_period_covered_by_holoo':previous_covered,
                                  'growth_percent':(current-old)/old*100 if old>0 and previous_covered else None,
                                  'note':'دورهٔ بلافاصله قبل با تعداد روز برابر؛ لزوماً ماه تقویمی قبل نیست. رشد با مبنای صفر یا منفی نامعلوم است.'}
            return {**metadata, **result}
        if a.section == 'team':
            staff_scope = '' if manager else ' AND sp.id=:sp'
            people = rows(conn,"SELECT sp.id,sp.name,ARRAY(SELECT u.id FROM users u WHERE u.salesperson_id=sp.id AND u.is_active::text IN ('1','true','t') ORDER BY u.id) AS user_ids FROM salespersons sp WHERE replace(replace(sp.name,'ي','ی'),'ك','ک') ILIKE :q"+staff_scope+' ORDER BY sp.id LIMIT 25',p)
            if a.salesperson_id:
                people = [r for r in people if r['id']==a.salesperson_id]
            if not people or (a.query and len(people)>1):
                return {**metadata,'status':'not_found' if not people else 'ambiguous','candidates':people}
            result=[]
            for person in people:
                totals=rows(conn,'''SELECT SUM(total_amount) AS net_sales_irr,COUNT(*) AS documents FROM sales
                    WHERE salesperson_id=:sid AND date>=:begin AND date<:end''',{**p,'sid':person['id']})[0]
                targets=rows(conn,"SELECT id,title,target_amount,target_type,start_date,end_date,product_focus FROM targets WHERE salesperson_id=:sid AND status='active' ORDER BY id DESC LIMIT 10",{'sid':person['id']})
                result.append({**person,**totals,'targets':targets})
            return {**metadata,'people':result,'limited_to':25}
        if a.section == 'customers':
            customer_scope='' if manager else ''' AND (EXISTS(SELECT 1 FROM sales s WHERE s.customer_id=c.id AND s.salesperson_id=:sp)
                OR EXISTS(SELECT 1 FROM proforma_invoices pf WHERE pf.customer_id=c.id AND pf.salesperson_id=:sp))'''
            if not a.query:
                snapshot=conn.execute(text('SELECT id,snapshot_date FROM receivable_snapshots ORDER BY snapshot_date DESC,id DESC LIMIT 1')).mappings().first()
                if not snapshot:
                    return {**metadata,'status':'source_missing','message':'گزارش مطالبات ثبت‌شده موجود نیست؛ مانده صفر نتیجه نمی‌شود.'}
                debt_base=''' FROM receivable_balances rb LEFT JOIN customers c ON c.id=rb.customer_id WHERE rb.snapshot_id=:snap AND rb.balance>0'''+customer_scope
                debt_params={**p,'snap':snapshot['id']}
                summary=rows(conn,'SELECT COUNT(*) AS debtor_rows,COALESCE(SUM(rb.balance),0) AS receivable_irr'+debt_base,debt_params)[0]
                top=rows(conn,'SELECT c.id,COALESCE(c.name,rb.counterparty) AS name,rb.balance AS receivable_irr'+debt_base+' ORDER BY rb.balance DESC LIMIT 20',debt_params)
                return {**metadata,'receivable_snapshot_date':snapshot['snapshot_date'],'totals':summary,'top_debtors':top,'top_rows_limited_to':20,
                        'note':'ماندهٔ مثبت آخرین گزارش اشخاص است؛ معین کامل حساب یا وجه وصول‌شده نیست.'}
            candidates=rows(conn,'''SELECT c.id,c.name,c.code,c.city FROM customers c WHERE (replace(replace(c.name,'ي','ی'),'ك','ک') ILIKE :q OR c.code ILIKE :q)'''+customer_scope+' ORDER BY c.id LIMIT 20',p)
            if len(candidates)!=1:
                return {**metadata,'status':'ambiguous' if candidates else 'not_found','candidates':candidates,'limited_to':20}
            cid=candidates[0]['id']
            sales=rows(conn,'SELECT s.date,s.total_amount AS net_sales_irr,s.holoo_sanad FROM sales s WHERE s.customer_id=:cid AND s.date>=:begin AND s.date<:end'+scope+' ORDER BY s.date DESC,s.id DESC LIMIT 20',{**p,'cid':cid})
            totals=rows(conn,'SELECT COUNT(*) AS documents,COALESCE(SUM(s.total_amount),0) AS net_sales_irr FROM sales s WHERE s.customer_id=:cid AND s.date>=:begin AND s.date<:end'+scope,{**p,'cid':cid})[0]
            debt=rows(conn,'''SELECT rb.balance,rs.snapshot_date FROM receivable_balances rb JOIN receivable_snapshots rs ON rs.id=rb.snapshot_id
                WHERE rb.customer_id=:cid AND rb.snapshot_id=(SELECT id FROM receivable_snapshots ORDER BY snapshot_date DESC,id DESC LIMIT 1)''',{'cid':cid})
            return {**metadata,'customer':candidates[0],'totals':totals,'recent_sales_limited_to_20':sales,'latest_reported_receivable':debt,'note':'مطالبات گزارش اشخاص جای دفتر کامل معین و تراکنش وصول نیست.'}
        if a.section == 'tasks':
            task_scope='' if manager else ' AND assigned_to=:uid'
            return {**metadata,'items':rows(conn,"SELECT id,title,status,priority,due_date FROM tasks WHERE status NOT IN ('done','cancelled')"+task_scope+' ORDER BY due_date NULLS LAST,id LIMIT 30',{'uid':user.get('id') or -1}),'limited_to':30}
        if a.section == 'crm':
            crm_scope='' if manager else ' AND owner_user_id=:uid'
            return {**metadata,'items':rows(conn,'''SELECT id,customer_name,interaction_type,product_discussed,notes,status,next_followup_date,followup_time
                FROM customer_interactions WHERE customer_name ILIKE :q'''+crm_scope+' ORDER BY next_followup_date NULLS LAST,id DESC LIMIT 30',{**p,'uid':user['id']}),'limited_to':30,'note':'گزارش پیگیری ثبت‌شده است؛ متن یادداشت، اظهارات کاربر است و اثبات فروش یا وصول نیست.'}
        if a.section == 'daily_reports':
            report_scope='' if manager else ' AND dr.salesperson_id=:sp'
            return {**metadata,'items':rows(conn,'''SELECT dr.report_date,sp.name,dr.visits_count,dr.orders_count,dr.lost_orders_count,
                dr.reported_sales_amount,dr.loss_reasons,dr.demand_notes,dr.issues,dr.tomorrow_plan
                FROM daily_reports dr LEFT JOIN salespersons sp ON sp.id=dr.salesperson_id
                WHERE dr.report_date>=:begin AND dr.report_date<:end AND sp.name ILIKE :q'''+report_scope+' ORDER BY dr.report_date DESC,dr.id DESC LIMIT 30',p),'limited_to':30,'note':'فروش خوداظهاری گزارش روزانه است؛ با فاکتور قطعی هلو جمع نشود.'}
        if a.section == 'campaigns':
            if not manager:
                raise HTTPException(403,'تحلیل کمپین شرکت فقط با مدیر است.')
            return {**metadata,'items':rows(conn,'''SELECT id,title,description,starts_at,ends_at,target_amount,reward_type,reward_value,is_active
                FROM campaigns WHERE title ILIKE :q ORDER BY id DESC LIMIT 30''',p),'limited_to':30,'note':'قواعد کمپین‌اند؛ تحقق نیازمند تطبیق دامنهٔ کالا، فرد و بازهٔ هر کمپین است.'}
        if a.section == 'content':
            content_scope='' if manager else ' AND created_by=:uid'
            return {**metadata,'items':rows(conn,'''SELECT id,channel,title,scheduled_at,status FROM social_content_calendar
                WHERE title ILIKE :q'''+content_scope+' ORDER BY scheduled_at DESC,id DESC LIMIT 30',{**p,'uid':user['id']}),'limited_to':30,'publishing_enabled':False}
        if a.section == 'proformas':
            pf_scope='' if manager else ' AND p.salesperson_id=:sp'
            return {**metadata,'items':rows(conn,'''SELECT p.id,p.created_at,p.status,p.total_amount,c.name AS customer FROM proforma_invoices p
                LEFT JOIN customers c ON c.id=p.customer_id WHERE p.created_at>=:begin AND p.created_at<:end'''+pf_scope+' ORDER BY p.id DESC LIMIT 30',p),'limited_to':30}
    return {'status':'not_available'}


def execute_report_tool(name, args, user, *, message='', history=()):
    if not isinstance(args,dict) or not user.get('id') or not user.get('role'):
        return {'status':'access_denied'}
    try:
        if name == 'prepare_sales_targets':
            from assistant_intake import prepare_sales_targets
            return prepare_sales_targets(args, user, message, history)
        if name == 'open_target_template':
            from assistant_intake import blank_target_template
            return blank_target_template(args, user)
        if name == 'prepare_visit_coverage':
            from assistant_intake import prepare_visit_coverage
            return prepare_visit_coverage(args, user)
        if name == 'search_public_web':
            from agent_center import market_search
            return market_search(PublicSearch.model_validate(args).model_dump())
        if name == 'analyze_catalog_selection':
            from assistant_engine import lookup_catalog_analysis
            return lookup_catalog_analysis(CatalogSelection.model_validate(args).query, user, history)
        if name == 'specialist_tools':
            from agent_extensions import catalog
            return {'operations':catalog(user)}
        if name == 'read_specialist_analysis':
            from agent_extensions import SPECS,execute
            if set(args)-{'operation','payload'} or args.get('operation') not in SPECS or SPECS[args['operation']]['kind']!='read':return {'status':'invalid_arguments'}
            return execute(args['operation'],args.get('payload',{}),user)
        if name == 'prepare_agent_mission':
            from agent_center import Objective,plan_objective
            return plan_objective(Objective.model_validate(args),user)
        if name == 'read_agent_missions':
            from agent_center import list_missions
            return list_missions(user)
        if name == 'panel_operations':
            from assistant_commands import catalog
            if set(args)-{'module','operation'}:return {'status':'invalid_arguments'}
            return catalog(user,args.get('module'),args.get('operation'))
        if name == 'read_contract_people':
            from compensation import payroll_people
            return trim(payroll_people(user))
        if name == 'read_panel_module':
            from assistant_panel import read_panel
            return read_panel(args,user)
        if name == 'prepare_panel_operation':
            from assistant_operations import prepare
            return prepare(args,user)
        if name == 'prepare_contract_review':
            return prepare_contract_review(args,user)
        if name == 'prepare_target':
            return prepare_target(args,user)
        if name == 'read_business_report':
            return read_report(ReportArgs.model_validate(args),user)
        return {'status':'unknown_tool'}
    except ValidationError as exc:
        return {'status':'invalid_arguments','message':'ساختار ورودی را اصلاح کن؛ این خطا به معنی نبود دسترسی یا قابلیت نیست. برای عملیات، ساختار دقیق را از panel_operations با نام operation بگیر و دوباره پیشنهاد بساز.',
                'fields':[{'path':list(e['loc']),'type':e['type']} for e in exc.errors()][:15]}
    except HTTPException as exc:
        return {'status':'access_denied' if exc.status_code==403 else 'data_unavailable','message':str(exc.detail)}
    except Exception as exc:
        logger.warning('assistant report failed: %s %s',name,type(exc).__name__)
        return {'status':'source_error','message':'خواندن این گزارش موفق نبود؛ نتیجه نامعلوم است و نباید صفر یا موفق اعلام شود.'}
