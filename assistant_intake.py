"""Structured handoffs from natural language to existing panel workflows."""
from collections import Counter, defaultdict
from datetime import timedelta
from math import ceil
from typing import Literal
from urllib.parse import urlencode
import re

import jdatetime
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from assistant_commands import authorize
from assistant_inventory import ALIASES, normalize
from assistant_money import DIGITS, explicit_money, listed_money, money_units, parse_money_phrase, quoted_shared_amount
from assistant_operations import prepare
from db import engine
from iran_time import iran_today
from monthly_visit_plans import MAX_STOPS_PER_DAY, month_window, options


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Target(Strict):
    title: str | None = Field(default=None, min_length=2, max_length=150)
    person: str | None = Field(default=None, min_length=2, max_length=100)
    salesperson_id: int | None = Field(default=None, gt=0)
    company: bool = False
    kind: Literal['sale', 'settlement'] = 'sale'
    amount_phrase: str = Field(min_length=3, max_length=100)
    reward_phrase: str | None = Field(default=None, min_length=3, max_length=100)
    product_focus: str | None = Field(default=None, max_length=150)


class Targets(Strict):
    month: str = Field(default='ماه جاری', description='نام ماه یا سال-ماه شمسی. اگر بازه ذکر نشده، پیش‌نمایش برای ماه جاری است.', max_length=24)
    person: str | None = Field(default=None, min_length=2, max_length=100, description='نام مشترک پرسنل برای تمام ردیف‌هایی که فرد جدا ندارند.')
    shared_unit: Literal['ریال', 'تومان'] | None = Field(default=None, description='واحد صریح مشترک در جمله، حتی اگر فقط انتهای فهرست آمده باشد.')
    rows: list[Target] = Field(min_length=1, max_length=30)


class BlankTargetRows(Strict):
    rows: int = Field(ge=1, le=500)


class CityCoverage(Strict):
    city: str = Field(min_length=2, max_length=100)
    scope: Literal['all_bases', 'selected_bases', 'trip']
    visits: int = Field(ge=1, le=4)
    base_names: list[str] = Field(default_factory=list, max_length=120)
    days: list[int] = Field(default_factory=list, max_length=31, description='روزهای شمسی ماه برنامه که کاربر برای این شهر تعیین کرده است.')


class VisitCoverage(Strict):
    person: str = Field(min_length=2, max_length=100)
    month: str = Field(default='ماه جاری', max_length=24)
    cities: list[CityCoverage] = Field(min_length=1, max_length=15)


MONTHS = {name: number for number, name in enumerate(
    'فروردین اردیبهشت خرداد تیر مرداد شهریور مهر آبان آذر دی بهمن اسفند'.split(), 1
)}


def jalali_month(value, today):
    current = jdatetime.date.fromgregorian(date=today)
    month = normalize(value).translate(DIGITS)
    if month in {'ماه جاری', 'این ماه'}:
        return f'{current.year:04d}-{current.month:02d}'
    if re.fullmatch(r'14\d{2}[-/](?:0?[1-9]|1[0-2])', month):
        year, number = re.split(r'[-/]', month)
        return f'{year}-{int(number):02d}'
    name = month.replace(' ', '').removesuffix('ماه').replace('اذر', 'آذر')
    if name in MONTHS:
        return f'{current.year:04d}-{MONTHS[name]:02d}'
    raise HTTPException(422, 'نام ماه یا سال و ماه شمسی را مشخص کنید.')


def find_people(people, name):
    if not name:
        return []
    wanted = normalize(name).split()
    if wanted and wanted[0] in {'خانم', 'آقا', 'اقا', 'آقای', 'اقای', 'جناب', 'دکتر', 'مهندس'}:
        wanted = wanted[1:]
    if not wanted:
        return []
    exact = [person for person in people if normalize(person['name']).split() == wanted]
    if exact:
        return exact
    matches = []
    for person in people:
        tokens = iter(normalize(person['name']).split())
        if all(any(token == word for token in tokens) for word in wanted):
            matches.append(person)
    return matches


def _matching_target_person(target, people, message):
    matches = find_people(people, target.person) if target.person else people
    if target.salesperson_id is not None:
        # An ID picked by the model cannot resolve ambiguous people.
        explicit_id = re.fullmatch(r'(?:شناسه\s*[:：]?\s*)?(\d+)', message.translate(DIGITS).strip())
        if explicit_id and int(explicit_id[1]) == target.salesperson_id:
            return [person for person in matches if person['id'] == target.salesperson_id]
    return matches if target.person else []


def _explicit_brand(value):
    value = normalize(value)
    return next((brand for brand, spellings in ALIASES.items()
                 if value in {normalize(label) for label in (brand, *spellings)}), None)


def _mentions_target(context, target):
    if target.title:
        return normalize(target.title) in context
    if target.product_focus:
        aliases = ALIASES.get(_explicit_brand(target.product_focus), ())
        return any(normalize(label) in context for label in (target.product_focus, *aliases))
    return bool(target.person and normalize(target.person) in context) or target.company


def prepare_sales_targets(args, user, message, history):
    authorize('enter_targets', user)
    request = Targets.model_validate(args)
    month = jalali_month(request.month, iran_today())
    start, end = month_window(month)
    end -= timedelta(days=1)
    # Clarifications can supply amounts or an ID without repeating the title.
    previous = next((turn['content'] for turn in reversed(history) if turn.get('role') == 'user'), '')
    current = normalize(message)
    previous_normalized = normalize(previous)
    targets = [row if row.person or row.company or not request.person else row.model_copy(update={'person': request.person}) for row in request.rows]
    targets = [
        row.model_copy(update={'title': None})
        if row.title and not any(normalize(row.title) in context for context in (current, previous_normalized))
        else row
        for row in targets
    ]
    previous_context = any(not _mentions_target(current, row) for row in targets)
    if previous_context and (len(targets) != 1 or not _mentions_target(previous_normalized, targets[0])):
        return {'status': 'needs_information', 'message': 'فقط تارگت همین درخواست را بیاور. اگر کاربر عنوان نداده، فیلد عنوان را خالی بگذار.'}
    amount_source = message if explicit_money(message) else (previous if previous_context else message)
    amounts = explicit_money(amount_source)
    units = money_units(amount_source)
    shared_unit = next(iter(units)) if len(units) == 1 else None
    stated_amounts = Counter(listed_money(amount_source, shared_unit))
    proposed_amounts = Counter()
    reward_requested = any(word in normalize(amount_source) for word in ('پاداش', 'پورسانت', 'جایزه'))
    with engine.connect() as conn:
        people = [dict(row) for row in conn.execute(text('SELECT id, name FROM salespersons ORDER BY name')).mappings()]
    rows = []
    for target in targets:
        if target.company and (target.person or target.salesperson_id):
            return {'status': 'needs_information', 'message': 'تارگت برای پرسنل است یا کل شرکت؟'}
        person = None
        if not target.company:
            matches = _matching_target_person(target, people, message)
            if len(matches) != 1:
                return {'status': 'needs_information', 'message': 'نام کامل فرد موردنظر همین تارگت را مشخص کنید.',
                        'candidates': [item['name'] for item in matches[:8]]}
            person = matches[0]
        phrases = (target.amount_phrase, target.reward_phrase if reward_requested else None)
        try:
            parsed = [parse_money_phrase(phrase, shared_unit) if phrase else None for phrase in phrases]
        except ValueError as exc:
            return {'status': 'needs_information', 'message': str(exc)}
        if any(value is not None and value not in amounts and not (shared_unit and quoted_shared_amount(amount_source, phrase))
               for value, phrase in zip(parsed, phrases)):
            return {'status': 'needs_information', 'message': 'مبلغ همین تارگت را عیناً از متن کاربر و همراه واحد بردار.',
                    'explicit_amounts_irr': [str(value) for value in amounts]}
        target_amount, reward = parsed
        proposed_amounts.update(value for value in parsed if value is not None)
        if target_amount <= 0 or target_amount > 10**15 or (reward is not None and not 0 <= reward < 10**13):
            return {'status': 'needs_information', 'message': 'مبلغ هدف باید مثبت باشد و هدف و پاداش در محدودهٔ مجاز فرم باشند.'}
        title_brand = _explicit_brand(normalize(target.title).removeprefix('تارگت ').removeprefix('هدف '))
        focus_brand = _explicit_brand(target.product_focus)
        if title_brand and focus_brand and title_brand != focus_brand:
            return {'status': 'needs_information', 'message': 'برند در عنوان و کالای هدف متفاوت است. کدام برند برای این تارگت درست است؟'}
        label = 'تسویه' if target.kind == 'settlement' else 'فروش'
        row = {'title': target.title or (f'تارگت {label} {target.product_focus}' if target.product_focus else f'تارگت {label}'),
               'target_amount': format(target_amount, 'f'),
               'start_date': start.isoformat(), 'end_date': end.isoformat()}
        if target.kind == 'settlement':
            row['target_type'] = 'تسویه'
        if person:
            row['salesperson_id'] = person['id']
        if reward is not None:
            row['bonus_reward'] = format(reward, 'f')
        if target.product_focus:
            row['product_focus'] = target.product_focus
        rows.append(row)

    if len(stated_amounts) and sum(stated_amounts.values()) > 1 and stated_amounts != proposed_amounts:
        return {'status': 'retry_target_rows',
                'message': ('همهٔ مبلغ‌های همین درخواست را به ردیف‌های مربوط اختصاص بده. '
                            'مبلغ فروش یا تسویه، مبلغ هدف است. پاداش فقط اگر صریحاً گفته شده باشد. '
                            'عنوان اختیاری است و مبلغ یا واحدِ داده‌شده را دوباره نپرس.')}
    result = prepare({'operation': 'enter_targets', 'payload': {'body': {'unit': 'IRR', 'rows': rows}}}, user)
    if result.get('status') == 'operation_preview' and len(rows) == 1:
        row = rows[0]
        person_label = person['name'] if person else 'کل شرکت'
        amount = format(target_amount, ',f')
        result['message'] = f'پیشنهاد «{row["title"]}» برای {person_label} با مبلغ هدف {amount} ریال آمادهٔ بررسی است.'
        if reward is not None:
            result['message'] += f' پاداش {format(reward, ",f")} ریال است.'
        result['message'] += f' دورهٔ شمسی {month} است و ثبت پس از تأیید در پنل انجام می‌شود.'
    elif result.get('status') == 'operation_preview':
        result['message'] = f'{len(rows)} تارگت برای دورهٔ شمسی {month} آمادهٔ بررسی است. ردیف‌ها با هم پس از تأیید در پنل ثبت می‌شوند.'
    return result


def blank_target_template(args, user):
    authorize('enter_targets', user)
    count = BlankTargetRows.model_validate(args).rows
    return {'status': 'form_ready', 'review_href': '/data-entry?' + urlencode({'entity': 'targets', 'rows': count}),
            'message': f'فرم ورود دستی با {count} ردیف خالی آماده است. پس از تکمیل، پیش‌نمایش و ثبت را از همان فرم انجام دهید.'}


def _city_name(city):
    return normalize(city).removeprefix('شهرستان ').removeprefix('شهر ')


def prepare_visit_coverage(args, user):
    authorize('monthly_plan_create', user)
    request = VisitCoverage.model_validate(args)
    today = iran_today()
    month = jalali_month(request.month, today)
    start, end = month_window(month)
    choices = options(user=user)
    people = [dict(person, name=person['full_name']) for person in choices['users']]
    matches = find_people(people, request.person)
    if len(matches) != 1:
        return {'status': 'needs_information', 'message': 'نام پرسنل فعال را دقیق‌تر مشخص کنید.',
                'candidates': [item['name'] for item in matches[:8]]}

    catalog = defaultdict(list)
    for base in choices['bases']:
        catalog[_city_name(base['city'])].append(base)
    coverage = []
    stops = []
    used = defaultdict(int)
    reserved_days = {day for wanted in request.cities for day in wanted.days}
    suggested_days = [
        day for day in range(1, (end - start).days + 1)
        if day not in reserved_days
        and (candidate := start + timedelta(days=day - 1)) >= today
        and candidate.weekday() != 4
    ]
    seen_cities = set()
    issues = []
    for wanted in request.cities:
        city = _city_name(wanted.city)
        if city in seen_cities:
            raise HTTPException(422, 'هر شهر یا شهرستان را یک بار با تعداد نوبت مشخص وارد کنید.')
        seen_cities.add(city)
        available = catalog.get(city, [])
        item = {'city': wanted.city, 'registered_bases': len(available), 'requested_visits': wanted.visits,
                'scope': wanted.scope}
        coverage.append(item)
        if not available:
            issues.append(f'برای «{wanted.city}» پایگاهی در فهرست پیدا نشد؛ نام شهر را بررسی کنید.')
            continue
        selected = available
        if wanted.scope == 'selected_bases' or wanted.base_names:
            if not wanted.base_names:
                issues.append(f'در «{wanted.city}» کدام پایگاه‌ها را می‌خواهید؟ اگر همه‌اند، همان را بگویید.')
                continue
            names = {normalize(name) for name in wanted.base_names}
            selected = [base for base in available if normalize(base['name']) in names]
            if len(selected) != len(names) or {normalize(base['name']) for base in selected} != names:
                issues.append(f'نام یک یا چند پایگاه در «{wanted.city}» یکتا یا موجود نیست.')
                continue
        per_cycle = ceil(len(selected) / MAX_STOPS_PER_DAY)
        if wanted.scope == 'trip' and per_cycle > 1:
            issues.append(f'«{wanted.city}» برای یک سفر بیش از {MAX_STOPS_PER_DAY} پایگاه دارد؛ پایگاه‌های اولویت‌دار را مشخص کنید.')
            continue
        needed_days = per_cycle * wanted.visits
        item.update(required_stops=len(selected) * wanted.visits, minimum_days=needed_days)
        days = sorted(set(wanted.days))
        if not days:
            days = suggested_days[:needed_days]
            del suggested_days[:needed_days]
        valid = all(1 <= day <= (end - start).days and start + timedelta(days=day - 1) >= today for day in days)
        if len(days) < needed_days or not valid:
            issues.append(f'برای «{wanted.city}» دست‌کم {needed_days} روز با ظرفیت فرم لازم است. روزهای کاریِ باقی‌ماندهٔ همین ماه را مشخص کنید.')
            continue
        item['days'] = days[:needed_days]
        for cycle in range(wanted.visits):
            for index, base in enumerate(selected):
                day = days[cycle * per_cycle + index // MAX_STOPS_PER_DAY]
                used[day] += 1
                stops.append({'visit_date': (start + timedelta(days=day - 1)).isoformat(),
                              'base_source': base['source'], 'base_id': base['id'],
                              'stop_order': used[day], 'objective': 'ویزیت و ثبت نتیجه'})

    if any(count > MAX_STOPS_PER_DAY for count in used.values()):
        issues.append('روزهای مشترک شهرها از ظرفیت ۱۲ توقف بیشتر می‌شوند. روزها را جدا کنید.')
    if len(stops) > 600:
        issues.append('تعداد توقف‌ها از سقف ۶۰۰ توقف یک برنامه بیشتر است.')
    if issues:
        return {'status': 'visit_coverage_review', 'person': matches[0]['name'], 'month': month,
                'coverage': coverage, 'questions': issues, 'saved': False}
    result = prepare({'operation': 'monthly_plan_create', 'payload': {'body': {
        'user_id': matches[0]['id'], 'month': month, 'stops': stops,
        'note': 'روزهای صریح از درخواست و روزهای دیگر از تقویم پیشنهادی انتخاب شدند. روزها و ترتیب سفر را بازبینی کنید.',
    }}}, user)
    if result.get('status') == 'operation_preview':
        details = '، '.join(
            f'{item["city"]}: {item["requested_visits"]} نوبت، {item["required_stops"]} توقف'
            for item in coverage
        )
        result['message'] = (
            f'برنامهٔ {matches[0]["name"]} برای {month} آمادهٔ بررسی است. {details}. '
            'روزها و پایگاه‌های پیشنهادی را بررسی کنید. تأیید شما برنامه را به‌صورت پیش‌نویس ثبت می‌کند.'
        )
        result['coverage'] = coverage
    return result
