"""Deterministic internal payroll calculations; no I/O or statutory defaults.

Rules must be approved separately by the caller. A non-empty ``blockers`` list
means the result is a preview and must not be approved. Amounts are in the
contract currency (currently rials). Mileage facts use ``quantity`` in km.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import math


class PayrollValidationError(ValueError):
    """Invalid input; API callers should translate this to HTTP 422."""


ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")
MAX_VALUE = Decimal("1000000000000000000")
KINDS = {"sale", "return", "collection", "collection_reversal", "mileage", "workday", "content_post", "content_story", "reward"}


def _number(value, field, *, maximum=MAX_VALUE, signed=False):
    if isinstance(value, bool) or value is None:
        raise PayrollValidationError(f"مقدار {field} باید عدد معتبر باشد")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PayrollValidationError(f"مقدار {field} باید عدد معتبر باشد") from None
    if not result.is_finite() or abs(result) > maximum or (not signed and result < ZERO):
        raise PayrollValidationError(f"مقدار {field} خارج از محدودهٔ معتبر است")
    return result


def _identifier(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float, Decimal)):
        number = _number(value, "شناسه", signed=True)
        return format(number.normalize(), "f")
    return value.strip() if isinstance(value, str) else ""


def _choice(value, choices, field):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or value not in choices:
        raise PayrollValidationError(f"گزینهٔ {field} معتبر نیست")
    return value


def _float(value, quantum=None):
    if quantum is not None:
        value = value.quantize(quantum, rounding=ROUND_HALF_UP)
    result = float(value)
    if not math.isfinite(result):
        raise PayrollValidationError("نتیجهٔ محاسبه خارج از محدودهٔ معتبر است")
    return result


def normalize_rules(data):
    """Validate settings, preserving missing policy choices as explicit nulls.

    Missing choices become calculation blockers, allowing a draft contract to
    be saved without inventing its policy. Invalid numeric values always fail.
    A zero monthly-hours value disables the overtime threshold; it is not a
    guaranteed minimum payment or a shortfall deduction.
    """
    if not isinstance(data, dict):
        raise PayrollValidationError("قواعد قرارداد باید یک شیء معتبر باشند")
    result = {}
    if not isinstance(data.get('bonus_note',''),str) or len(data.get('bonus_note',''))>1000:
        raise PayrollValidationError("شرح سیاست پاداش باید حداکثر ۱۰۰۰ نویسه باشد")
    result['bonus_note'] = data.get('bonus_note','').strip()
    result["salary_mode"] = _choice(
        data.get("salary_mode", "hourly"), {"hourly", "fixed", "commission_only"}, "نوع حقوق")
    if result["salary_mode"] is None:
        raise PayrollValidationError("نوع حقوق باید مشخص باشد")
    result["fixed_monthly_amount"] = _float(_number(data.get("fixed_monthly_amount", 0), "حقوق ثابت ماهانه"))
    result["fixed_proration"] = _choice(
        data.get("fixed_proration"), {"full", "working_days"}, "نحوهٔ تسهیم حقوق ثابت")
    for key in ("worked_days", "required_workdays"):
        value = data.get(key)
        result[key] = None if value is None else _float(_number(value, key, maximum=Decimal("31")))
    result["sales_scope"] = _choice(data.get("sales_scope"), {"personal", "company"}, "دامنهٔ فروش")
    result["commission_tier_basis"] = _choice(
        data.get("commission_tier_basis"), {"marginal", "attained"}, "مبنای پلکان پورسانت")
    for key in ("hourly_rate", "min_monthly_hours", "settlement_commission_percent",
                "daily_mission_allowance", "per_km_rate"):
        maximum = HUNDRED if key == "settlement_commission_percent" else MAX_VALUE
        if key == "min_monthly_hours":
            maximum = Decimal("744")
        result[key] = _float(_number(data.get(key, 0), key, maximum=maximum))
    multiplier = data.get("overtime_multiplier")
    result["overtime_multiplier"] = (
        None if multiplier in (None, "") else
        _float(_number(multiplier, "ضریب اضافه‌کار", maximum=HUNDRED))
    )
    result["commission_overlap"] = _choice(
        data.get("commission_overlap"), {"highest", "sum"}, "همپوشانی پورسانت")
    tiers = data.get("sales_tiers", [])
    if not isinstance(tiers, list) or len(tiers) > 100:
        raise PayrollValidationError("فهرست پله‌های پورسانت معتبر نیست")
    result["sales_tiers"] = []
    previous = ZERO
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise PayrollValidationError("هر پله باید یک شیء معتبر باشد")
        if "up_to_amount" not in tier:
            raise PayrollValidationError("سقف هر پله باید مشخص باشد؛ پلهٔ بدون سقف مقدار خالی دارد")
        cap = tier["up_to_amount"]
        cap = None if cap is None else _number(cap, "سقف پله")
        if cap is None:
            if index != len(tiers) - 1:
                raise PayrollValidationError("پلهٔ بدون سقف فقط می‌تواند آخرین پله باشد")
        elif cap <= previous:
            raise PayrollValidationError("سقف پله‌ها باید مثبت و صعودی باشد")
        else:
            previous = cap
        result["sales_tiers"].append({
            "up_to_amount": None if cap is None else _float(cap),
            "percent": _float(_number(tier.get("percent"), "درصد پله", maximum=HUNDRED)),
        })
    targets = data.get("targets", [])
    if not isinstance(targets, list) or len(targets) > 200:
        raise PayrollValidationError("فهرست هدف‌ها معتبر نیست یا بیش از حد مجاز است")
    result["targets"] = []
    for target in targets:
        if not isinstance(target, dict):
            raise PayrollValidationError("هر هدف باید یک شیء معتبر باشد")
        target_type = target.get("target_type", "brand")
        if not isinstance(target_type, str) or target_type not in {"brand", "product"}:
            raise PayrollValidationError("نوع هدف باید برند یا کالا باشد")
        quantity = _number(target.get("target_quantity", 0), "تعداد هدف")
        if quantity != quantity.to_integral_value():
            raise PayrollValidationError("تعداد هدف باید عدد صحیح باشد")
        identifier = _identifier(target.get("item_identifier"))
        if len(identifier) > 200:
            raise PayrollValidationError("شناسهٔ هدف بیش از حد مجاز است")
        result["targets"].append({
            "target_type": target_type,
            "item_identifier": identifier,
            "item_title": str(target.get("item_title") or "").strip()[:200],
            "target_amount": _float(_number(target.get("target_amount", 0), "مبلغ هدف")),
            "target_quantity": int(quantity),
            "commission_percent": _float(_number(
                target.get("commission_percent", 0), "درصد هدف", maximum=HUNDRED)),
            "target_gate": _choice(target.get("target_gate"), {"all", "any"}, "شرط هدف"),
            "commission_basis": _choice(
                target.get("commission_basis"), {"whole", "excess"}, "مبنای پورسانت"),
        })
    content = data.get("content_bonus")
    result["content_bonus"] = None
    if content:
        if not isinstance(content, dict):
            raise PayrollValidationError("قاعدهٔ حق محتوا معتبر نیست")
        bonus = {}
        for key in ("monthly_amount", "per_post_amount", "required_posts", "required_stories"):
            number = _number(content.get(key, 0), key)
            if key in {"required_posts", "required_stories"} and number != number.to_integral_value():
                raise PayrollValidationError("تعداد خروجی محتوا باید صحیح باشد")
            bonus[key] = _float(number)
        bonus["story_requirement"] = _choice(content.get("story_requirement"), {"gate_full", "independent", "per_bundle"}, "شرط استوری")
        if bonus["story_requirement"] == "per_bundle":
            stories = _number(content.get("stories_per_bundle"), "تعداد استوری هر بسته")
            if stories <= 0 or stories != stories.to_integral_value():
                raise PayrollValidationError("تعداد استوری هر بسته باید عدد صحیح مثبت باشد")
            bonus["stories_per_bundle"] = int(stories)
        result["content_bonus"] = bonus
    return result


def calculate_payroll(rules, worked_hours, verified_visit_days, facts=None, source_complete=None):
    """Calculate a reproducible preview and the reasons it cannot be approved.

    Return/reversal amounts may arrive signed or unsigned: their kind supplies
    the sign exactly once. An event key is unique across this person's period.
    Source completeness must explicitly be true for every active variable fee.
    Target thresholds gate on net period amounts/quantities; ``excess`` means
    money above the monetary threshold, with quantity acting only as a gate.
    Overlap is resolved per product/brand bucket, not per entire contract.
    """
    normalized = normalize_rules(rules)
    hours = _number(worked_hours, "ساعت کارکرد", maximum=Decimal("1000000"))
    days = _number(verified_visit_days, "روز بازدید", maximum=Decimal("31"))
    if days != days.to_integral_value():
        raise PayrollValidationError("روز بازدید باید عدد صحیح باشد")
    if facts is None:
        facts = []
    if not isinstance(facts, list) or len(facts) > 100000:
        raise PayrollValidationError("فهرست اسناد محاسبه معتبر نیست")
    if source_complete is None:
        source_complete = {}
    if not isinstance(source_complete, dict):
        raise PayrollValidationError("وضعیت کامل‌بودن منابع معتبر نیست")
    blockers = []

    def block(code, message, **context):
        item = {"code": code, "message": message, **context}
        if item not in blockers:
            blockers.append(item)

    rate = Decimal(str(normalized["hourly_rate"]))
    threshold = Decimal(str(normalized["min_monthly_hours"]))
    daily_rate = Decimal(str(normalized["daily_mission_allowance"]))
    collection_rate = Decimal(str(normalized["settlement_commission_percent"]))
    km_rate = Decimal(str(normalized["per_km_rate"]))
    salary_mode = normalized["salary_mode"]
    regular = (min(hours, threshold) if threshold > ZERO else hours) if salary_mode != "commission_only" else ZERO
    overtime = max(ZERO, hours - threshold) if threshold > ZERO and salary_mode != "commission_only" else ZERO
    shortfall = max(ZERO, threshold - hours) if salary_mode != "commission_only" else ZERO
    multiplier = normalized["overtime_multiplier"]
    if overtime and multiplier is None:
        block("overtime_policy_missing", "ضریب مصوب برای ساعت اضافه مشخص نشده است")
    if overtime and salary_mode == "fixed" and rate <= ZERO:
        block("overtime_hourly_rate_missing", "نرخ ساعتی مصوب برای اضافه‌کار حقوق ثابت مشخص نشده است")

    active_targets = [t for t in normalized["targets"] if t["commission_percent"] > 0]
    active_tiers = any(tier["percent"] > 0 for tier in normalized["sales_tiers"])
    active_sales = bool(active_targets) or active_tiers
    required_sources = {"sales": active_sales, "collections": collection_rate > ZERO,
                        "mileage": km_rate > ZERO}
    if active_sales and normalized["sales_scope"] is None:
        block("sales_scope_missing", "مبنای فروش شخصی یا شرکت مشخص نشده است")
    if active_sales and normalized["sales_scope"] == "company":
        required_sources["company_sales"] = True
    if active_tiers and normalized["commission_tier_basis"] is None:
        block("commission_tier_policy_missing", "مبنای محاسبهٔ پلکانی باید صریحاً تعیین شود")
    for source, required in required_sources.items():
        if required and source_complete.get(source) is not True:
            block(f"{source}_source_incomplete", "منبع کامل و تأییدشدهٔ محاسبه دریافت نشده است",
                  source=source)

    seen = set()
    buckets = defaultdict(lambda: {"amount": ZERO, "quantity": ZERO})
    collections, kilometers, fact_workdays, content_posts, content_stories, rewards = ZERO, ZERO, ZERO, ZERO, ZERO, ZERO
    accepted_events = 0
    for fact in facts:
        if not isinstance(fact, dict):
            raise PayrollValidationError("هر سند محاسبه باید یک شیء معتبر باشد")
        event_key = _identifier(fact.get("event_key"))
        if not event_key or len(event_key) > 300:
            raise PayrollValidationError("هر سند باید کلید یکتای معتبر داشته باشد")
        if event_key in seen:
            block("duplicate_event", "سند تکراری در محاسبه وجود دارد", event_key=event_key)
            continue
        seen.add(event_key)
        kind = fact.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise PayrollValidationError("نوع سند محاسبه معتبر نیست")
        reversal = kind in {"return", "collection_reversal"}
        amount = _number(fact.get("amount", 0), "مبلغ سند", signed=reversal)
        quantity = _number(fact.get("quantity", 1 if kind == "workday" else 0), "تعداد یا مسافت سند", signed=reversal)
        if reversal:
            amount, quantity = -abs(amount), -abs(quantity)
        accepted_events += 1
        if kind in {"sale", "return"}:
            key = (_identifier(fact.get("product_id")), _identifier(fact.get("brand")))
            buckets[key]["amount"] += amount
            buckets[key]["quantity"] += quantity
        elif kind in {"collection", "collection_reversal"}:
            collections += amount
        elif kind == "mileage":
            kilometers += quantity
        elif kind == "reward":
            rewards += amount
        elif kind in {"content_post", "content_story"}:
            if quantity != quantity.to_integral_value():
                raise PayrollValidationError("تعداد محتوای تأییدشده باید صحیح باشد")
            if kind == "content_post":
                content_posts += quantity
            else:
                content_stories += quantity
        else:
            if quantity > 1:
                raise PayrollValidationError("هر سند روز کاری حداکثر یک روز را ثبت می‌کند")
            fact_workdays += quantity

    with localcontext() as context:
        context.prec = 50
        worked_days = Decimal(str(normalized["worked_days"])) if normalized["worked_days"] is not None else fact_workdays
        if worked_days > 31:
            raise PayrollValidationError("جمع روزهای کاری از محدودهٔ ماه بیشتر است")
        fixed_pay = ZERO
        if salary_mode == "fixed":
            fixed_amount = Decimal(str(normalized["fixed_monthly_amount"]))
            if normalized["fixed_proration"] == "full":
                fixed_pay = fixed_amount
            elif normalized["fixed_proration"] == "working_days":
                required_workdays = normalized["required_workdays"]
                if required_workdays is None or required_workdays <= 0:
                    block("required_workdays_missing", "روزهای موظفی مصوب حقوق ثابت مشخص نشده است")
                elif normalized["worked_days"] is None and source_complete.get("workdays") is not True:
                    block("workdays_source_incomplete", "منبع کامل روزهای کارکرد برای حقوق ثابت دریافت نشده است")
                else:
                    fixed_pay = fixed_amount * min(Decimal("1"), worked_days / Decimal(str(required_workdays)))
            else:
                block("fixed_proration_missing", "نحوهٔ پرداخت کامل یا متناسب با روزهای کاری مشخص نشده است")
        base_pay = regular * rate if salary_mode == "hourly" else fixed_pay
        overtime_pay = overtime * rate * Decimal(str(multiplier)) if multiplier is not None else ZERO
        allowance = days * daily_rate
        if collections < ZERO and collection_rate > ZERO:
            block("negative_net_collections", "وصول خالص منفی به قاعدهٔ مصوب رسیدگی نیاز دارد")
        collection_commission = max(ZERO, collections) * collection_rate / HUNDRED
        mileage_allowance = kilometers * km_rate
        contributions = defaultdict(list)
        details = []
        tier_details = []
        if active_tiers and normalized["commission_tier_basis"] is not None:
            amount = sum((value["amount"] for value in buckets.values()), ZERO)
            if any(value["amount"] < ZERO or value["quantity"] < ZERO for value in buckets.values()):
                block("negative_net_sales", "فروش یا تعداد خالص منفی به قاعدهٔ مصوب رسیدگی نیاز دارد")
            elif amount > ZERO:
                lower, tier_commission, covered = ZERO, ZERO, False
                for tier in normalized["sales_tiers"]:
                    cap = None if tier["up_to_amount"] is None else Decimal(str(tier["up_to_amount"]))
                    percent = Decimal(str(tier["percent"]))
                    if normalized["commission_tier_basis"] == "marginal":
                        portion = max(ZERO, min(amount, cap) - lower) if cap is not None else max(ZERO, amount - lower)
                        earned = portion * percent / HUNDRED
                        tier_commission += earned
                        tier_details.append({"from_amount": _float(lower), "up_to_amount": None if cap is None else _float(cap),
                                             "applied_amount": _float(portion, CENT), "percent": _float(percent),
                                             "commission": _float(earned, CENT)})
                    elif cap is None or amount <= cap:
                        tier_commission = amount * percent / HUNDRED
                        tier_details.append({"from_amount": _float(lower), "up_to_amount": None if cap is None else _float(cap),
                                             "applied_amount": _float(amount, CENT), "percent": _float(percent),
                                             "commission": _float(tier_commission, CENT)})
                    if cap is None or amount <= cap:
                        covered = True
                        break
                    lower = cap
                if not covered:
                    block("commission_tier_coverage_missing", "درصد مصوب برای فروش بیشتر از آخرین سقف مشخص نشده است")
                if tier_commission > ZERO:
                    for key, value in buckets.items():
                        if value["amount"] > ZERO:
                            contributions[key].append(("sales_tiers", tier_commission * value["amount"] / amount))
        for index, target in enumerate(normalized["targets"]):
            if target["commission_percent"] <= 0:
                continue
            identifier = target["item_identifier"]
            if not identifier:
                block("target_identifier_missing", "شناسهٔ ثابت هدف مشخص نشده است", target_index=index)
                continue
            gate, basis = target["target_gate"], target["commission_basis"]
            if gate is None or basis is None:
                block("target_policy_missing", "شرط و مبنای مصوب پورسانت هدف مشخص نشده است",
                      target_index=index)
                continue
            position = 0 if target["target_type"] == "product" else 1
            matched = {key: value for key, value in buckets.items() if key[position] == identifier}
            amount = sum((v["amount"] for v in matched.values()), ZERO)
            quantity = sum((v["quantity"] for v in matched.values()), ZERO)
            if any(v["amount"] < ZERO or v["quantity"] < ZERO for v in matched.values()):
                block("negative_net_sales", "فروش یا تعداد خالص منفی به قاعدهٔ مصوب رسیدگی نیاز دارد",
                      target_index=index)
                continue
            target_amount = Decimal(str(target["target_amount"]))
            target_quantity = Decimal(str(target["target_quantity"]))
            conditions = []
            if target_amount > ZERO:
                conditions.append(amount >= target_amount)
            if target_quantity > ZERO:
                conditions.append(quantity >= target_quantity)
            reached = not conditions or (all(conditions) if gate == "all" else any(conditions))
            if basis == "excess" and target_amount <= ZERO and target_quantity > ZERO:
                block("quantity_excess_policy_missing", "مبنای ریالی مازاد هدف تعدادی مشخص نشده است",
                      target_index=index)
                continue
            eligible_amount = (amount if basis == "whole" else max(ZERO, amount - target_amount)) if reached else ZERO
            commission = eligible_amount * Decimal(str(target["commission_percent"])) / HUNDRED
            details.append({"target_index": index, "target_reached": reached,
                            "net_amount": _float(amount, CENT), "net_quantity": _float(quantity),
                            "eligible_amount": _float(eligible_amount, CENT),
                            "commission_before_overlap": _float(commission, CENT)})
            if commission > ZERO and amount > ZERO:
                for key, value in matched.items():
                    if value["amount"] > ZERO:
                        contributions[key].append((index, commission * value["amount"] / amount))
        sales_commission = ZERO
        for key, candidates in sorted(contributions.items()):
            if len(candidates) > 1 and normalized["commission_overlap"] is None:
                block("commission_overlap_policy_missing", "برای اهداف همپوشان، روش مصوب جمع یا بیشترین مشخص نشده است",
                      target_indices=[item[0] for item in candidates])
                continue
            if normalized["commission_overlap"] == "sum":
                sales_commission += sum((amount for _, amount in candidates), ZERO)
            else:
                sales_commission += max(amount for _, amount in candidates)
        content_pay = ZERO
        if rewards > ZERO and source_complete.get('rewards') is not True:
            block('rewards_source_incomplete','مبلغ و دلیل پاداش ماه باید توسط مدیر تطبیق و تأیید شود')
        content_rule = normalized.get("content_bonus")
        if content_rule and (content_rule["monthly_amount"] > 0 or content_rule["per_post_amount"] > 0):
            if source_complete.get("content") is not True:
                block("content_source_incomplete", "تولید، ویرایش و انتشار محتوا باید توسط مدیر تأیید شود")
            if content_rule["required_stories"] > 0 and content_rule["story_requirement"] is None:
                block("content_story_policy_missing", "شرط استوری برای پرداخت حق پست مشخص نشده است")
            paid_units = content_posts
            if content_rule["story_requirement"] == "per_bundle":
                paid_units = min(content_posts // 1, content_stories // Decimal(content_rule["stories_per_bundle"]))
            content_pay = paid_units * Decimal(str(content_rule["per_post_amount"]))
            if content_rule["monthly_amount"] > 0:
                content_pay = min(content_pay, Decimal(str(content_rule["monthly_amount"])))
            if content_rule["required_posts"] > 0:
                content_pay = min(content_pay, Decimal(str(content_rule["required_posts"])) * Decimal(str(content_rule["per_post_amount"])))
            if content_rule["story_requirement"] == "gate_full" and content_stories < content_rule["required_stories"]:
                block("content_story_target_pending", "شرط تعداد استوری برای پرداخت حق محتوا هنوز محقق نشده است")
        # Round components once before summing so the displayed statement adds up.
        amounts = {"base_pay": base_pay, "overtime_pay": overtime_pay,
                   "verified_visit_allowance": allowance, "sales_commission": sales_commission,
                   "collection_commission": collection_commission, "mileage_allowance": mileage_allowance,
                   "content_pay": content_pay, "reward_pay": rewards}
        amounts = {name: value.quantize(CENT, rounding=ROUND_HALF_UP) for name, value in amounts.items()}
        result = {name: _float(value) for name, value in amounts.items()}
        result.update({
            "worked_hours": _float(hours), "verified_visit_days": int(days),
            "hourly_rate": _float(rate), "daily_mission_allowance": _float(daily_rate),
            "regular_hours": _float(regular), "overtime_hours": _float(overtime),
            "shortfall_hours": _float(shortfall),
            "salary_mode": salary_mode, "fixed_pay": _float(fixed_pay, CENT),
            "worked_days": _float(worked_days), "required_workdays": normalized["required_workdays"],
            "provisional_total": _float(sum(amounts.values(), ZERO)),
            "blockers": blockers, "can_approve": not blockers,
            "commission_details": details, "tier_details": tier_details, "source_complete": {
                source: source_complete.get(source) is True for source in required_sources},
            "source_event_count": accepted_events,
            "net_collected_amount": _float(collections, CENT), "approved_kilometers": _float(kilometers),
            "content_posts": _float(content_posts), "content_stories": _float(content_stories),
        })
    return result
