"""Typed specialist tool registry; no free URLs, SQL or permission changes."""
from uuid import UUID
from db import engine
from sqlalchemy import text
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field

class Input(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Tracking(Input):
    user_id:int=Field(gt=0)
    from_day:str|None=None
    to_day:str|None=None
class ProgrammeId(Input):programme_id:UUID
class OutboundApproval(Input):
    message_id:UUID
    expected_digest:str=Field(pattern='^[0-9a-f]{64}$')
class CoursePublication(Input):
    programme_id:UUID
    expected_digest:str=Field(pattern='^[0-9a-f]{64}$')
    user_ids:list[int]=Field(min_length=1,max_length=50)
    due_date:str
class ObligationTask(Input):
    review_id:UUID
    obligation_index:int=Field(ge=0,le=29)
    assigned_to:int=Field(gt=0)
    due_date:str
    expected_source_digest:str=Field(pattern='^[0-9a-f]{64}$')

SPECS={
    'team_signals':{'label':'پیشرفت زمانی هدف و پوشش ویزیت از فروش و ثبت تأییدشده؛ بدون نتیجه انضباطی','kind':'read','access':'ceo','module':'assistant'},
    'target_scenarios':{'label':'سناریوی تارگت از فروش سالانهٔ شخص و محصول، قیمت، ظرفیت و تورم مستند','kind':'read','access':'ceo','module':'assistant'},
    'tracking_analytics':{'label':'تحلیل زمان مشاهده‌شده، توقف، مسیر و فاصله‌های بی‌دادهٔ GPS','kind':'read','access':'scoped','module':'map'},
    'contract_review':{'label':'تحلیل قرارداد با تطبیق نقل قول و تعهد؛ بدون تصمیم حقوقی یا امضا','kind':'read','access':'ceo','module':'assistant'},
    'contract_obligation_task':{'label':'ساخت وظیفهٔ پیگیری تعهد قرارداد با موعد تأییدشدهٔ مدیر','kind':'protected','access':'ceo','module':'assistant'},
    'training_generate':{'label':'ساخت پیش‌نویس درس و آزمون از منبع سازمانی؛ بدون انتشار','kind':'draft','access':'ceo','module':'assistant'},
    'training_publish':{'label':'انتشار محتوای بازبینی‌شده و تخصیص اتمیک وظایف آموزش به افراد مشخص','kind':'protected','access':'ceo','module':'assistant'},
    'training_progress':{'label':'گزارش واقعی تخصیص، تلاش، امتیاز و بررسی مدیر در یک دوره','kind':'read','access':'ceo','module':'assistant'},
    'training_my_courses':{'label':'دوره‌ها و نتیجه‌های آموزشی تخصیص‌داده‌شده به خود کاربر','kind':'read','access':'self','module':None},
    'prospect_discover':{'label':'دریافت و نسخه‌بندی لید عمومی کرمان؛ بدون ایجاد مشتری یا ارسال پیام','kind':'draft','access':'ceo','module':'assistant'},
    'outbound_preview':{'label':'پیش‌نویس پیام دقیق برای راه تماس و رضایت ثبت‌شده؛ بدون ارسال','kind':'draft','access':'ceo','module':'assistant'},
    'outbound_approve':{'label':'تصویب متن و گیرندهٔ دقیق پیام برای ورود به صف متصل؛ نیازمند تأیید گام','kind':'protected','access':'ceo','module':'assistant'},
}

def models():
    from specialist_workflows import TargetScenario,ContractReview,MonitorRequest
    from training_workflows import Generate
    from prospect_pipeline import Discovery
    from outbound_messages import Message
    return {'team_signals':MonitorRequest,'target_scenarios':TargetScenario,'tracking_analytics':Tracking,'contract_review':ContractReview,'contract_obligation_task':ObligationTask,'training_generate':Generate,'training_publish':CoursePublication,'training_progress':ProgrammeId,'training_my_courses':Input,'prospect_discover':Discovery,'outbound_preview':Message,'outbound_approve':OutboundApproval}


def catalog(user):
    from operations import role_has_module_permission
    result=[]
    for name,s in SPECS.items():
        if s['access']=='ceo' and user.get('role')!='ceo':continue
        if s['module'] and not role_has_module_permission(user.get('role',''),s['module'],'can_read'):continue
        schema=models()[name].model_json_schema()
        # Creation keys come from stable mission step UUIDs, never invented by the model.
        schema.get('properties',{}).pop('submission_key',None)
        if 'required' in schema:schema['required']=[p for p in schema['required'] if p!='submission_key']
        result.append({'operation':name,**s,'input_schema':schema,'payload_shape':'flat object; IDs must be real or declared earlier receipts'})
    return result


def execute(name,payload,user,step_id=None):
    from operations import role_has_module_permission
    if name not in SPECS:raise HTTPException(422,'ابزار تخصصی شناخته‌شده نیست.')
    spec=SPECS[name]
    if spec['access']=='ceo':
        from agent_center import ceo
        ceo(user)
        with engine.connect() as c:active=c.execute(text("SELECT id,username,full_name,role,salesperson_id,password_version FROM users WHERE id=:id AND is_active::text IN ('1','true','t')"),{'id':user['id']}).mappings().first()
        if not active or active['role']!='ceo':raise HTTPException(403,'اختیار مدیر تغییر کرده است.')
        user=dict(active)
    if spec['module'] and not role_has_module_permission(user.get('role',''),spec['module'],'can_read'):raise HTTPException(403,'مجوز خواندن حوزهٔ ابزار فعال نیست.')
    values=dict(payload)
    if name in {'training_generate','prospect_discover','outbound_preview'}:
        if step_id is None:raise HTTPException(422,'ساخت پیش‌نویس فقط در گام دارای شناسهٔ پایدار انجام می‌شود.')
        values['submission_key']=str(step_id)
    try:data=models()[name].model_validate(values)
    except Exception:raise HTTPException(422,'ورودی ابزار تخصصی با ساختار معتبر و شناسه‌های واقعی تطبیق ندارد.') from None
    if name=='team_signals':
        from specialist_workflows import team_signals
        return team_signals(data,user)
    if name=='target_scenarios':
        from specialist_workflows import targets
        return targets(data,user)
    if name=='tracking_analytics':
        from datetime import date
        from tracking_analytics import analytics
        try:first=date.fromisoformat(data.from_day) if data.from_day else None;last=date.fromisoformat(data.to_day) if data.to_day else None
        except ValueError:raise HTTPException(422,'تاریخ تحلیل معتبر نیست.') from None
        return analytics(data.user_id,first,last,user)
    if name=='contract_review':
        from specialist_workflows import contract_review
        return contract_review(data,user)
    if name=='contract_obligation_task':
        from specialist_workflows import obligation_task,Obligation
        return obligation_task(data.review_id,Obligation(confirm=True,**data.model_dump(exclude={'review_id'})),user)
    if name=='training_generate':
        from training_workflows import generate
        return generate(data,user)
    if name=='training_publish':
        from training_workflows import publish,Publish
        return publish(data.programme_id,Publish(confirm=True,**data.model_dump(exclude={'programme_id'})),user)
    if name=='training_progress':
        from training_workflows import progress
        return progress(data.programme_id,user)
    if name=='training_my_courses':
        from training_workflows import listing
        return listing(user)
    if name=='prospect_discover':
        from prospect_pipeline import run_discovery
        return run_discovery(data,user)
    if name=='outbound_preview':
        from outbound_messages import preview
        return preview(data,user)
    if name=='outbound_approve':
        from outbound_messages import approve,Approve
        return approve(data.message_id,Approve(confirm=True,expected_digest=data.expected_digest),user)
    raise HTTPException(422,'اجرا برای این ابزار پیاده‌سازی نشده است.')
