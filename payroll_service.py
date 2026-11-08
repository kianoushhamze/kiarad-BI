"""Versioned compensation rules, attributed source facts and immutable approvals."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException

from payroll_periods import current_payroll_month, payroll_period, period_is_approved


def ensure_payroll_schema(cur):
    statements = (
        """CREATE TABLE IF NOT EXISTS compensation_rule_versions(
            id BIGSERIAL PRIMARY KEY,salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
            effective_month VARCHAR(7) NOT NULL,effective_start DATE NOT NULL,
            rules_json JSONB NOT NULL,approved BOOLEAN NOT NULL DEFAULT FALSE,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'))""",
        """CREATE TABLE IF NOT EXISTS compensation_facts(
            id BIGSERIAL PRIMARY KEY,salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
            event_date DATE NOT NULL,event_key VARCHAR(180) NOT NULL UNIQUE,kind VARCHAR(30) NOT NULL,
            amount NUMERIC NOT NULL DEFAULT 0,quantity NUMERIC NOT NULL DEFAULT 0,
            product_id TEXT,brand TEXT,source_note TEXT NOT NULL,recorded_by INTEGER NOT NULL REFERENCES users(id),
            recorded_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'))""",
        """CREATE TABLE IF NOT EXISTS compensation_source_checks(
            salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),payroll_month VARCHAR(7) NOT NULL,
            source VARCHAR(30) NOT NULL,complete BOOLEAN NOT NULL,note TEXT NOT NULL,
            verified_by INTEGER NOT NULL REFERENCES users(id),
            verified_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
            PRIMARY KEY(salesperson_id,payroll_month,source))""",
        """CREATE TABLE IF NOT EXISTS payroll_approval_history(
            id BIGSERIAL PRIMARY KEY,salesperson_id INTEGER NOT NULL REFERENCES salespersons(id),
            payroll_month VARCHAR(7) NOT NULL,revision INTEGER NOT NULL,rule_version_id BIGINT,
            snapshot JSONB NOT NULL,additions NUMERIC NOT NULL,deductions NUMERIC NOT NULL,
            approved_total NUMERIC NOT NULL,note TEXT NOT NULL,approved_by INTEGER NOT NULL REFERENCES users(id),
            approved_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Tehran'),
            UNIQUE(salesperson_id,payroll_month,revision))""",
        "CREATE INDEX IF NOT EXISTS ix_compensation_rule_period ON compensation_rule_versions(salesperson_id,effective_start,id)",
        "CREATE INDEX IF NOT EXISTS ix_compensation_fact_period ON compensation_facts(salesperson_id,event_date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_compensation_workday ON compensation_facts(salesperson_id,event_date) WHERE kind='workday'",
    )
    for statement in statements:
        cur.execute(statement)


def period(month):
    try:
        return payroll_period(month)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="ماه حقوق معتبر نیست؛ نمونهٔ شمسی: ۱۴۰۵-۰۷")


def _money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal('1e18'):
            raise ValueError
        return number.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(status_code=422, detail="مبلغ باید عدد محدود و نامنفی باشد")


def normalized_rules(data):
    from payroll_engine import PayrollValidationError, normalize_rules
    try:
        return normalize_rules({**data, 'worked_days': None})
    except (PayrollValidationError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error))


def _rule(cur, salesperson_id, start, approved_only=False):
    cur.execute("SELECT to_regclass('compensation_rule_versions')")
    if not cur.fetchone()[0]:
        return None
    cur.execute("""SELECT id,effective_month,rules_json,approved,created_at
        FROM compensation_rule_versions WHERE salesperson_id=%s AND effective_start<=%s
    """ + (" AND approved=TRUE" if approved_only else "") +
        " ORDER BY effective_start DESC,id DESC LIMIT 1", (salesperson_id, start.date()))
    row = cur.fetchone()
    if not row:
        return None
    rules = row[2] if isinstance(row[2], dict) else json.loads(row[2])
    return {**rules, "rule_version": row[0], "effective_month": row[1], "rules_approved": row[3],
            "created_at": row[4], "configured": True, "currency": "IRR"}


def get_contract(cur, salesperson_id, month=None):
    _, start, _, _ = period(month or current_payroll_month())
    version = _rule(cur, salesperson_id, start)
    if version:
        return {**version, "salesperson_id": salesperson_id}
    cur.execute("""SELECT id,hourly_rate,min_monthly_hours,settlement_commission_percent,
        daily_mission_allowance,per_km_rate FROM salesperson_contracts WHERE salesperson_id=%s""", (salesperson_id,))
    row = cur.fetchone()
    if not row:
        return {"configured": False, "rules_approved": False, "salesperson_id": salesperson_id, "currency": "IRR"}
    result = dict(zip(("id", "hourly_rate", "min_monthly_hours", "settlement_commission_percent",
                       "daily_mission_allowance", "per_km_rate"), row))
    cur.execute("""SELECT target_type,item_identifier,item_title,target_amount,target_quantity,commission_percent
        FROM salesperson_targets WHERE contract_id=%s""", (row[0],))
    result["targets"] = [dict(zip(("target_type", "item_identifier", "item_title", "target_amount",
                                   "target_quantity", "commission_percent"), target)) for target in cur.fetchall()]
    return {**result, "configured": True, "rules_approved": False, "salesperson_id": salesperson_id, "currency": "IRR"}


def save_contract(cur, salesperson_id, data, user):
    month, start, _, _ = period(data.get('effective_month') or current_payroll_month())
    rules = normalized_rules(data)
    if data.get('currency', 'IRR') != 'IRR':
        raise HTTPException(status_code=422, detail="مبلغ‌های ذخیره‌شده باید ریال باشند؛ تومان را در فرم تبدیل کنید")
    questions = data.get('unresolved_questions', [])
    if not isinstance(questions, list) or any(not isinstance(item,str) or len(item)>1000 for item in questions) or len(questions)>30:
        raise HTTPException(status_code=422, detail="فهرست ابهام‌های قرارداد معتبر نیست")
    rules['unresolved_questions'] = questions
    rules['decision_note'] = str(data.get('decision_note') or '')[:2000]
    approved = data.get('rules_approved', False)
    if type(approved) is not bool:
        raise HTTPException(status_code=422, detail="وضعیت تصویب قواعد معتبر نیست")
    if approved and data.get('unresolved_questions'):
        raise HTTPException(status_code=422, detail="ابتدا ابهام‌های فرمول پیشنهادی را مشخص کنید")
    if approved:
        from payroll_engine import calculate_payroll
        probe = calculate_payroll(rules,0,0,facts=[],source_complete={
            key:True for key in ('sales','collections','mileage','content','workdays','company_sales','rewards')})
        missing = [item for item in probe['blockers'] if item['code'] != 'content_story_target_pending']
        if missing:
            raise HTTPException(status_code=422, detail='؛ '.join(item['message'] for item in missing))
    cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (salesperson_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="پرسنل پیدا نشد")
    if 'expected_rule_version' in data:
        current = _rule(cur, salesperson_id, start)
        if (current or {}).get('rule_version') != data['expected_rule_version']:
            raise HTTPException(status_code=409, detail="قرارداد پس از پیش‌نمایش تغییر کرده؛ پیشنهاد تازه بسازید")
    if period_is_approved(cur, salesperson_id, start):
        raise HTTPException(status_code=409, detail="حقوق این دوره تصویب شده؛ قواعد دورهٔ بسته تغییر نمی‌کند")
    cur.execute("""INSERT INTO compensation_rule_versions(salesperson_id,effective_month,effective_start,
        rules_json,approved,created_by) VALUES(%s,%s,%s,%s::jsonb,%s,%s) RETURNING id""",
        (salesperson_id, month, start.date(), json.dumps(rules, ensure_ascii=False), approved, user['id']))
    return {"status": "success", "rule_version": cur.fetchone()[0], "effective_month": month,
            "rules_approved": approved, "rules": rules}


def calculate_period(cur, salesperson_id, month):
    from payroll_engine import calculate_payroll
    month, start, end, calendar = period(month)
    version = _rule(cur, salesperson_id, start, approved_only=True)
    rules = version or normalized_rules({})
    cur.execute("""SELECT COALESCE(SUM(EXTRACT(EPOCH FROM
        (LEAST(end_time,%s)-GREATEST(start_time,%s)))/3600),0)
        FROM attendance_sessions WHERE salesperson_id=%s AND is_active=FALSE AND end_time IS NOT NULL
        AND end_time>start_time AND start_time<%s AND end_time>%s""", (end, start, salesperson_id, end, start))
    hours = cur.fetchone()[0] or 0
    cur.execute("""SELECT COUNT(*) FROM attendance_sessions WHERE salesperson_id=%s
        AND (is_active=TRUE OR end_time IS NULL) AND start_time<%s""", (salesperson_id, end))
    open_sessions = cur.fetchone()[0]
    cur.execute("""SELECT COUNT(DISTINCT checked_in_at::date) FROM base_checkins
        WHERE salesperson_id=%s AND status='verified' AND checked_in_at>=%s AND checked_in_at<%s""",
        (salesperson_id, start, end))
    days = cur.fetchone()[0]
    cur.execute("""SELECT event_key,kind,amount,quantity,product_id,brand FROM compensation_facts
        WHERE salesperson_id=%s AND event_date>=%s AND event_date<%s ORDER BY event_date,event_key""",
        (salesperson_id, start.date(), end.date()))
    facts = [dict(zip(('event_key','kind','amount','quantity','product_id','brand'), row)) for row in cur.fetchall()]
    cur.execute("SELECT source,complete FROM compensation_source_checks WHERE salesperson_id=%s AND payroll_month=%s",
                (salesperson_id, month))
    complete = dict(cur.fetchall())
    automatically_filled = ['closed_attendance_hours','verified_visit_days','attributed_source_documents']
    # Default workday draft comes from closed shifts. Explicit manager corrections
    # replace this draft and retain their own source-attestation workflow.
    if rules.get('salary_mode') == 'fixed' and rules.get('fixed_proration') == 'working_days' and not any(f['kind']=='workday' for f in facts):
        cur.execute("""SELECT DISTINCT start_time::date FROM attendance_sessions
            WHERE salesperson_id=%s AND is_active=FALSE AND end_time>start_time
              AND start_time>=%s AND start_time<%s ORDER BY start_time::date""", (salesperson_id,start,end))
        dates = [row[0] for row in cur.fetchall()]
        facts.extend({'event_key':'attendance-day:'+day.isoformat(),'kind':'workday','amount':0,'quantity':1,
                      'product_id':'','brand':''} for day in dates)
        if dates and not open_sessions and 'workdays' not in complete:
            complete['workdays'] = True
        automatically_filled.append('closed_shift_workdays')
    calculation = calculate_payroll(rules, hours, days, facts=facts, source_complete=complete)
    blockers = list(calculation.get('blockers', []))
    if version is None:
        blockers.append({'code': 'rules_not_approved', 'message': 'برای این ماه فرمول مصوب وجود ندارد'})
    if open_sessions:
        blockers.append({'code': 'open_attendance', 'message': 'شیفت بازِ مؤثر بر این دوره باید بسته شود'})
    return {**calculation, 'blockers': blockers, 'can_approve': not blockers, 'rules': rules,
            'rule_version': version.get('rule_version') if version else None,
            'source_event_keys': [row['event_key'] for row in facts], 'source_complete': complete,
            'automatically_filled': automatically_filled,
            'month': month, 'calendar': calendar, 'period_start': start.isoformat()+'+03:30',
            'period_end': end.isoformat()+'+03:30', 'currency': 'IRR'}


def summary(cur, salesperson_id, month):
    month, _, _, _ = period(month)
    cur.execute("""SELECT id,revision,snapshot,additions,deductions,approved_total,note,approved_at,approved_by
        FROM payroll_approval_history WHERE salesperson_id=%s AND payroll_month=%s ORDER BY revision DESC LIMIT 1""",
        (salesperson_id, month))
    row = cur.fetchone()
    if row:
        snapshot = row[2] if isinstance(row[2], dict) else json.loads(row[2])
        approval = dict(zip(('id','revision','snapshot','additions','deductions','approved_total','note','approved_at','approved_by'), row))
        approval.pop('snapshot')
        return {**snapshot, 'salesperson_id': salesperson_id, 'approval': approval, 'provisional': False,
                'note': 'نسخهٔ ثابتِ کارکرد تأییدشده؛ این رکورد اثبات پرداخت بانکی نیست.'}
    return {**calculate_period(cur, salesperson_id, month), 'salesperson_id': salesperson_id,
            'approval': None, 'provisional': True,
            'note': 'جمع بر اساس قواعد و مبنای تأییدشدهٔ این دوره است؛ بیمه و مالیات بدون مصوبه محاسبه نمی‌شوند.'}


def approve(cur, salesperson_id, month, data, user):
    month, _, _, _ = period(month)
    additions, deductions = _money(data.get('additions', 0)), _money(data.get('deductions', 0))
    note = str(data.get('note') or '').strip()
    if len(note) > 2000:
        raise HTTPException(status_code=422, detail="یادداشت بیش از حد طولانی است")
    cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (salesperson_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="پرسنل پیدا نشد")
    cur.execute("SELECT COALESCE(MAX(revision),0) FROM payroll_approval_history WHERE salesperson_id=%s AND payroll_month=%s",
                (salesperson_id, month))
    revision = int(cur.fetchone()[0]) + 1
    if (revision > 1 or additions or deductions) and len(note) < 5:
        raise HTTPException(status_code=422, detail="علت بازبینی، افزوده یا کسورات را بنویسید")
    calculation = calculate_period(cur, salesperson_id, month)
    if calculation['blockers']:
        raise HTTPException(status_code=409, detail={'message': 'مبنای حقوق کامل نیست', 'blockers': calculation['blockers']})
    total = _money(Decimal(str(calculation['provisional_total'])) + additions - deductions)
    snapshot = json.dumps(calculation, ensure_ascii=False, default=str)
    cur.execute("""INSERT INTO payroll_approval_history(salesperson_id,payroll_month,revision,rule_version_id,
        snapshot,additions,deductions,approved_total,note,approved_by)
        VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s) RETURNING id,approved_at""",
        (salesperson_id, month, revision, calculation['rule_version'], snapshot, additions, deductions, total, note, user['id']))
    approval_id, approved_at = cur.fetchone()
    # Preserve the existing period lock consumed by check-ins and attendance.
    cur.execute("""INSERT INTO payroll_approvals(salesperson_id,payroll_month,worked_hours,verified_visit_days,
        base_pay,visit_allowance,additions,deductions,approved_total,note,status,approved_by,approved_at)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',%s,NOW() AT TIME ZONE 'Asia/Tehran')
        ON CONFLICT(salesperson_id,payroll_month) DO UPDATE SET worked_hours=EXCLUDED.worked_hours,
        verified_visit_days=EXCLUDED.verified_visit_days,base_pay=EXCLUDED.base_pay,visit_allowance=EXCLUDED.visit_allowance,
        additions=EXCLUDED.additions,deductions=EXCLUDED.deductions,approved_total=EXCLUDED.approved_total,
        note=EXCLUDED.note,approved_by=EXCLUDED.approved_by,approved_at=EXCLUDED.approved_at,status='approved'""",
        (salesperson_id, month, calculation['worked_hours'], calculation['verified_visit_days'],
         calculation['base_pay'], calculation['verified_visit_allowance'], additions, deductions, total, note, user['id']))
    return {'status': 'approved', 'id': approval_id, 'revision': revision, 'approved_total': float(total), 'approved_at': approved_at}


def record_fact(cur, salesperson_id, data, user, *, allow_zero_workday=False):
    try:
        event_date = date.fromisoformat(str(data.get('event_date', '')))
    except ValueError:
        raise HTTPException(status_code=422, detail="تاریخ سند معتبر نیست")
    key, kind = str(data.get('event_key') or '').strip(), str(data.get('kind') or '')
    note = str(data.get('source_note') or '').strip()
    if not 3 <= len(key) <= 180 or len(note) < 8 or len(note) > 2000:
        raise HTTPException(status_code=422, detail="شناسهٔ یکتای سند و توضیح منبع معتبر لازم است")
    if kind not in {'sale','return','collection','collection_reversal','mileage','workday','content_post','content_story','reward'}:
        raise HTTPException(status_code=422, detail="نوع مبنای محاسبه معتبر نیست")
    amount, quantity = _money(data.get('amount', 0)), _money(data.get('quantity', 0))
    if kind == 'workday' and not (0 <= quantity <= 1 if allow_zero_workday else 0 < quantity <= 1):
        raise HTTPException(status_code=422, detail="هر سند کارکرد باید بین صفر و یک روز باشد")
    if kind in {'content_post','content_story'}:
        if quantity <= 0 or quantity != quantity.to_integral_value():
            raise HTTPException(status_code=422, detail="تعداد محتوای تأییدشده باید صحیح و مثبت باشد")
        required = ('produced','edited','published') if kind == 'content_post' else ('published',)
        if any(data.get(key) is not True for key in required):
            raise HTTPException(status_code=422, detail="تولید، ویرایش و انتشار پست یا انتشار استوری باید تأیید شود")
    cur.execute("SELECT id FROM salespersons WHERE id=%s FOR UPDATE", (salesperson_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=404, detail="پرسنل پیدا نشد")
    from datetime import datetime, time
    if period_is_approved(cur, salesperson_id, datetime.combine(event_date, time.min)):
        raise HTTPException(status_code=409, detail="مبنای دورهٔ تصویب‌شده تغییر نمی‌کند")
    cur.execute("SELECT id FROM compensation_facts WHERE event_key=%s", (key,))
    if cur.fetchone():
        raise HTTPException(status_code=409, detail="این سند قبلاً ثبت شده است")
    if kind == 'workday':
        cur.execute("SELECT id FROM compensation_facts WHERE salesperson_id=%s AND event_date=%s AND kind='workday'", (salesperson_id,event_date))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="کارکرد این روز قبلاً ثبت شده است")
    cur.execute("""INSERT INTO compensation_facts(salesperson_id,event_date,event_key,kind,amount,quantity,
        product_id,brand,source_note,recorded_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (salesperson_id,event_date,key,kind,amount,quantity,str(data.get('product_id') or ''),
         str(data.get('brand') or ''),note,user['id']))
    fact_id = cur.fetchone()[0]
    source = {'sale':'sales','return':'sales','collection':'collections','collection_reversal':'collections',
              'workday':'workdays','content_post':'content','content_story':'content','mileage':'mileage','reward':'rewards'}[kind]
    import jdatetime
    persian = jdatetime.date.fromgregorian(date=event_date)
    cur.execute("""UPDATE compensation_source_checks SET complete=FALSE
        WHERE salesperson_id=%s AND source=%s AND payroll_month IN (%s,%s)""",
        (salesperson_id,source,f'{persian.year:04d}-{persian.month:02d}',event_date.strftime('%Y-%m')))
    return {'id': fact_id, 'status': 'recorded'}
