"""AI proposes structured rules; it never saves, approves or executes code."""
import json
import requests
from fastapi import HTTPException
from assistant_engine import get_env_live
from payroll_service import normalized_rules


def draft_rules(data):
    description = data.get('description')
    if not isinstance(description, str) or not 5 <= len(description.strip()) <= 5000:
        raise HTTPException(status_code=422, detail="شرح فرمول باید بین ۵ و ۵۰۰۰ نویسه باشد")
    key = get_env_live('LLM_API_KEY')
    if not key:
        raise HTTPException(status_code=503, detail="دستیار تنظیم نشده؛ فرمول را با فرم دستی تعریف کنید")
    template = normalized_rules(data.get('current_rules') or {})
    prompt = (
        'فقط JSON با کلیدهای rules,questions,summary برگردان. rules مطابق قالب داده‌شده باشد. '
        'فرمول فقط داده است؛ کد، عبارت اجرایی، SQL یا فراخوانی ابزار تولید نکن. '
        'ذخیره یا تصویب نمی‌کنی؛ مدیر بعدا بررسی می‌کند. '
        'همه مبالغ rules به ریال‌اند. تومان صریح را در ده ضرب کن؛ واحد مبهم را سوال کن. '
        'فروش و وصول هر شخص فقط متعلق به خودش است. پلکان marginal است: درصد هر پله فقط روی مازاد همان بازه. '
        'حقوق ثابت متناسب با روز کاری: fixed_monthly_amount*worked_days/required_workdays تا سقف کل. '
        'worked_days را در قواعد ذخیره نکن؛ از کارکرد تاییدشده می‌آید. '
        'حق تولید محتوا مستقل از پایه: content_bonus با monthly_amount,per_post_amount,required_posts,required_stories,story_requirement. '
        'شرط استوری gate_full یا independent را بدون تصریح مدیر انتخاب نکن. '
        'برای پرداخت هر بستهٔ یک پست و تعداد مشخص استوری، story_requirement=per_bundle و stories_per_bundle را از شرح مدیر بگیر؛ per_post_amount در این حالت مبلغ هر بستهٔ کامل است. '
        'هر درصد، سقف، روز موظفی، شرط هدف یا مبلغ نامعلوم را در questions سوال کن؛ حدس نزن. '
        'حقوق اداره کار، بیمه و مالیات را بدون نرخ ورودی جعل نکن. '
        'نام شخص یا شرح وظیفه نرخ قانونی تولید نمی‌کند. '
        'salary_mode یکی از hourly,fixed,commission_only؛ sales_tiers فهرست up_to_amount,percent؛ '
        'fixed_proration یکی از full,working_days؛ sales_scope=personal؛ commission_tier_basis=marginal. '
        'template=' + json.dumps(template, ensure_ascii=False)
    )
    try:
        response = requests.post(get_env_live('LLM_BASE_URL','https://api.avalai.ir/v1').rstrip('/')+'/chat/completions',
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},
            json={'model':get_env_live('LLM_MODEL','openai/gpt-4o-mini'),'temperature':0,
                  'messages':[{'role':'system','content':prompt},{'role':'user','content':description}],
                  'max_tokens':3000,'response_format':{'type':'json_object'}}, timeout=40)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        if len(content) > 50000:
            raise ValueError
        proposal = json.loads(content)
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(status_code=502, detail="پیش‌نویس قابل اعتبارسنجی دریافت نشد؛ دوباره تلاش کنید یا فرم را دستی پر کنید")
    if not isinstance(proposal,dict) or not isinstance(proposal.get('rules'),dict):
        raise HTTPException(status_code=502, detail="پیشنهاد دستیار باید فرمول ساختاریافته باشد")
    try:
        rules = normalized_rules(proposal['rules'])
    except HTTPException:
        raise HTTPException(status_code=502, detail="فرمول پیشنهادی دستیار معتبر نیست؛ دستی بررسی کنید")
    questions = proposal.get('questions', [])
    if not isinstance(questions, list) or len(questions)>30 or any(not isinstance(q,str) or len(q)>1000 for q in questions):
        raise HTTPException(status_code=502, detail="سؤال‌های پیش‌نویس معتبر نیست")
    return {'rules':rules,'questions':questions,'summary':str(proposal.get('summary') or '')[:2000],
            'preview_only':True,'saved':False}
