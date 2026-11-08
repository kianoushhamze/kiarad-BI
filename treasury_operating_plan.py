"""Pure operating-budget scenarios; no account entries, network, or database access.

Amounts are integer IRR in the result.  The Holoo balance is kept separate from
manual accounts.  A calculated scenario is never evidence that incomplete or
stale sources cover all of the company's obligations.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import jdatetime

from treasury_finance import OPEN_STATUSES, PAYABLE_TYPES, RECEIVABLE_TYPES, money, month_days, month_of


def default_operating_plan():
    """User-confirmed total monthly operating envelope and source attestations."""
    return {
        "monthly_expense_irr": 3_000_000_000,
        "bank_balances_current": False,
        "receivable_checks_current": True,
        "payable_checks_current": False,
        "endorsed_checks_current": False,
        "checks_registry_complete": False,
        "source_note": "هزینهٔ ثابت و متغیر مجموعاً ماهی ۳۰۰ میلیون تومان طبق تأیید مدیر است. دریافتنی‌ها طبق اعلام مدیر به‌روزند؛ بانک، صندوق، پرداختنی و چک خرج‌شده نیازمند به‌روزرسانی در هلو هستند و فهرست کامل چک از رابط موجود دریافت نشده است.",
    }


def _number(value):
    if value is None or isinstance(value, bool):
        raise ValueError("مبلغ معتبر نیست.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("مبلغ معتبر نیست.") from exc
    if not result.is_finite():
        raise ValueError("مبلغ باید محدود باشد.")
    return result


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _evidence_day(value):
    """Interpret timestamp evidence in Iran; a date-only value is already local."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        return value
    else:
        raw = str(value)
        if len(raw) == 10:
            return date.fromisoformat(raw)
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    # Stored naive timestamps, if any, follow the application's Iran clock.
    return (moment.replace(tzinfo=ZoneInfo("Asia/Tehran")) if moment.tzinfo is None
            else moment.astimezone(ZoneInfo("Asia/Tehran"))).date()


def _balance(summary):
    """Return only an entirely validated Holoo bank/cash opening balance."""
    if not summary or summary.get("currency_verified") is not True:
        return None, "واحد پول یا برداشت ماندهٔ هلو تأیید نشده است."
    sources = {item.get("kind"): item for item in summary.get("sources", []) if isinstance(item, dict)}
    for kind in ("cash", "banks"):
        source = sources.get(kind)
        if not source or source.get("ok") is not True or source.get("complete") is not True:
            return None, "منبع ماندهٔ بانک و صندوق کامل نیست."
        if source.get("duplicate_or_missing_keys", 0) or source.get("valid_amounts") != source.get("count"):
            return None, "شناسه یا مبلغ بعضی مانده‌های هلو معتبر نیست."
    rows = summary.get("balances", [])
    if not rows:
        return None, "هیچ ماندهٔ بانک یا صندوقی برای مبنای نقد موجود نیست."
    seen, counts, total = set(), defaultdict(int), Decimal(0)
    try:
        for row in rows:
            kind, code = row.get("source"), str(row.get("code") or "").strip()
            key = (kind, code)
            if kind not in {"cash", "banks"} or not code or key in seen:
                return None, "ماندهٔ تکراری یا فاقد شناسهٔ معتبر در هلو وجود دارد."
            seen.add(key)
            counts[kind] += 1
            total += _number(row.get("balance"))
        if any(counts[kind] != sources[kind]["count"] for kind in ("cash", "banks")):
            return None, "تعداد مانده‌های معتبر با منبع هلو منطبق نیست."
    except (AttributeError, KeyError, TypeError, ValueError):
        return None, "مبلغ یا ساختار ماندهٔ هلو معتبر نیست."
    return total, None


def operating_cash_plan(plan, holoo_summary, documents, today):
    """Build a 91-day illustrative cash scenario without guessing future sales.

    The full monthly expense envelope is reduced only by non-cancelled payable
    documents explicitly linked to a fixed expense in that Jalali month.  Closed
    linked documents also consume the envelope, but are never paid a second time.
    The residual envelope is spread over calendar days of the whole month; this
    is a scheduling assumption, not an assertion about the actual payment date.
    """
    policy = {**default_operating_plan(), **(plan or {})}
    monthly_budget = _number(policy["monthly_expense_irr"])
    if monthly_budget < 0 or monthly_budget != monthly_budget.to_integral_value():
        raise ValueError("بودجهٔ ماهانه باید ریال صحیح و نامنفی باشد.")
    policy["monthly_expense_irr"] = money(monthly_budget)
    today = _day(today)
    end = today + timedelta(days=90)
    opening, balance_warning = _balance(holoo_summary)
    covered = defaultdict(lambda: Decimal(0))
    events = defaultdict(lambda: {"receipts": Decimal(0), "payables": Decimal(0)})
    counts = {"input_documents": 0, "invalid_documents": 0, "duplicate_documents": 0,
              "unclassified_documents": 0, "unlinked_open_payables": 0,
              "missing_document_identifiers": 0, "invalid_expense_links": 0,
              "assumed_collection_probability": 0, "bounced_receivables": 0,
              "included_open_documents": 0}
    seen_ids, seen_references = set(), set()
    allowed_statuses = OPEN_STATUSES | {"settled", "cleared", "cancelled"}
    for doc in documents or []:
        counts["input_documents"] += 1
        try:
            kind = doc.get("document_type")
            if kind not in RECEIVABLE_TYPES | PAYABLE_TYPES:
                counts["unclassified_documents"] += 1
                continue
            status = doc.get("status")
            if status not in allowed_statuses:
                raise ValueError("وضعیت نامشخص")
            if status == "cancelled":
                continue
            amount, due = _number(doc.get("amount")), _day(doc.get("due_date"))
            if amount < 0:
                raise ValueError("مبلغ منفی")
            ident = doc.get("id")
            incoming = kind in RECEIVABLE_TYPES
            reference = str(doc.get("reference_number") or "").strip()
            reference_key = ("receivable" if incoming else "payable", reference)
            if (ident is not None and ident in seen_ids) or (reference and reference_key in seen_references):
                counts["duplicate_documents"] += 1
                continue
            if ident is not None:
                seen_ids.add(ident)
            if reference:
                seen_references.add(reference_key)
            if ident is None and not reference:
                counts["missing_document_identifiers"] += 1
            link = doc.get("fixed_expense_id")
            linked = isinstance(link, int) and not isinstance(link, bool) and link > 0
            if link is not None and not linked:
                counts["invalid_expense_links"] += 1
            if not incoming and linked:
                covered[month_of(due)] += amount
            if status not in OPEN_STATUSES:
                continue
            effective = max(due, today)
            if effective > end:
                continue
            if incoming:
                if status == "bounced":
                    probability = Decimal(0)
                    counts["bounced_receivables"] += 1
                else:
                    if "collection_probability" not in doc:
                        counts["assumed_collection_probability"] += 1
                    probability = _number(doc.get("collection_probability", 1))
                    if not 0 <= probability <= 1:
                        raise ValueError("احتمال نامعتبر")
                events[effective]["receipts"] += amount * probability
            else:
                events[effective]["payables"] += amount
                if not linked:
                    counts["unlinked_open_payables"] += 1
            counts["included_open_documents"] += 1
        except (AttributeError, TypeError, ValueError, InvalidOperation):
            counts["invalid_documents"] += 1

    flag_definitions = (
        ("bank_balances_current", "ماندهٔ بانک و صندوق", "بانک و صندوق در هلو نیازمند به‌روزرسانی است."),
        ("receivable_checks_current", "چک‌های دریافتنی", "به‌روز بودن چک‌های دریافتنی تأیید نشده است."),
        ("payable_checks_current", "چک‌های پرداختنی", "چک‌های پرداختنی در هلو نیازمند به‌روزرسانی است."),
        ("endorsed_checks_current", "چک‌های خرج‌شده", "چک‌های خرج‌شده به تأمین‌کننده در هلو نیازمند به‌روزرسانی است."),
        ("checks_registry_complete", "پوشش فهرست چک", "فهرست کامل چک‌های دارای سررسید و وضعیت از منبع معتبر تأیید نشده است."),
    )
    warnings = [warning for key, _, warning in flag_definitions if policy.get(key) is not True]
    readiness_sources = [{"key": key, "label": label, "ready": policy.get(key) is True,
                          "evidence": "اعلام مدیر" if key != "checks_registry_complete" else "نیازمند تطبیق فهرست کامل"}
                         for key, label, _ in flag_definitions]
    summary = holoo_summary or {}
    source_date = next((summary.get(key) for key in ("captured_at", "finished_at", "to_date") if summary.get(key) is not None), None)
    try:
        snapshot_current = source_date is not None and _evidence_day(source_date) == today
    except (TypeError, ValueError):
        snapshot_current = False
    readiness_sources.append({"key": "source_snapshot_current", "label": "زمان دریافت ماندهٔ هلو",
                              "ready": snapshot_current, "evidence": "زمان برداشت به وقت تهران"})
    if not snapshot_current:
        warnings.append("برداشت ماندهٔ هلو مربوط به امروز به وقت تهران نیست یا زمان معتبر ندارد؛ تازه‌سازی لازم است.")
    if policy.get("attested_at") is not None:
        try:
            attestation_current = _evidence_day(policy["attested_at"]) == today
        except (TypeError, ValueError):
            attestation_current = False
        readiness_sources.append({"key": "attestation_current", "label": "زمان تأیید تازگی منابع",
                                  "ready": attestation_current, "evidence": "تأیید مدیر به وقت تهران"})
        if not attestation_current:
            warnings.append("تأیید تازگی منابع مربوط به امروز نیست؛ پس از به‌روزرسانی هلو دوباره تأیید شود.")
    if policy.get("source_snapshot_id") is not None:
        snapshot_linked = str(policy["source_snapshot_id"]) == str(summary.get("id"))
        readiness_sources.append({"key": "source_snapshot_linked", "label": "پیوند تأیید با برداشت مانده",
                                  "ready": snapshot_linked, "evidence": "شناسهٔ برداشت تأییدشده"})
        if not snapshot_linked:
            warnings.append("تأیید مانده به این برداشت هلو پیوند ندارد؛ برداشت تازه باید تطبیق و تأیید شود.")
    if balance_warning:
        warnings.append(balance_warning)
    blockers = list(warnings)
    for key, message in (
        ("invalid_documents", "سند با مبلغ، تاریخ، وضعیت یا احتمال نامعتبر از سناریو کنار گذاشته شد."),
        ("duplicate_documents", "سند یا شمارهٔ مرجع تکراری از سناریو کنار گذاشته شد؛ تطبیق لازم است."),
        ("unclassified_documents", "سند با جهت نامشخص وجود دارد؛ چک خرج‌شده از روی حدس تبدیل به پرداخت نمی‌شود."),
        ("missing_document_identifiers", "بعضی اسناد شناسه یا شمارهٔ مرجع ندارند؛ نبود رکورد تکراری قابل تأیید نیست."),
        ("invalid_expense_links", "پیوند هزینهٔ بعضی اسناد معتبر نیست و از بودجهٔ هزینه کسر نشده است."),
        ("unlinked_open_payables", "پرداختنی فاقد پیوند هزینه در مبلغ کامل لحاظ شد؛ ممکن است خرید باشد و خودکار از بودجهٔ هزینه کم نمی‌شود."),
        ("assumed_collection_probability", "برای بعضی دریافتنی‌ها احتمال وصول ثبت نشده و فرض سناریو صد درصد است."),
    ):
        if counts[key]:
            warnings.append(message)
            if key != "unlinked_open_payables":
                blockers.append(message)
    warnings.extend([
        "سناریو فقط تعهدها و دریافتنی‌های ثبت‌شده را می‌بیند؛ فروش آینده و صدور چک جدید پیش‌بینی نشده است.",
        "ماندهٔ هلو مستقل از حساب‌های دستی است؛ این دو با هم جمع نمی‌شوند.",
        "بودجهٔ ماهانه مجموع هزینهٔ ثابت و متغیر است؛ حقوق و هزینهٔ ثابت دوباره به آن اضافه نمی‌شود.",
        "زمان‌بندی هزینهٔ باقیمانده، یکنواخت بر روزهای تقویمی ماه شمسی است؛ زمان واقعی پرداخت می‌تواند متفاوت باشد.",
        "پوشش تعهدهای ثبت‌شده در سناریو، تأیید سلامت مالی کل شرکت یا امکان تضمین‌شدهٔ پرداخت همهٔ هزینه‌های آینده نیست.",
    ])
    source_complete = (opening is not None and all(item["ready"] for item in readiness_sources)
                       and not any(counts[key] for key in ("invalid_documents", "duplicate_documents", "unclassified_documents", "assumed_collection_probability", "missing_document_identifiers", "invalid_expense_links")))
    months, daily = {}, []
    balance, minimum = opening, opening
    first_shortage = today.isoformat() if opening is not None and opening < 0 else None
    totals = {"period_expense_budget_irr": 0, "linked_expense_coverage_irr": 0,
              "operating_envelope_outflow_irr": 0, "payable_outflow_irr": 0, "expected_receipts_irr": 0}
    for offset in range(91):
        day = today + timedelta(days=offset)
        month = month_of(day)
        number = jdatetime.date.fromgregorian(date=day).day
        divisor = month_days(month)
        residual_budget = max(Decimal(0), monthly_budget - covered[month])
        # Cumulative rounding preserves exactly one envelope per complete month.
        day_budget = money(monthly_budget * number / divisor) - money(monthly_budget * (number - 1) / divisor)
        operating = money(residual_budget * number / divisor) - money(residual_budget * (number - 1) / divisor)
        receipts, payables = money(events[day]["receipts"]), money(events[day]["payables"])
        row = months.setdefault(month, {"month": month, "days_in_horizon": 0, "days_in_month": divisor,
            "full_month_expense_budget_irr": money(monthly_budget), "full_month_linked_expenses_irr": money(covered[month]),
            "period_expense_budget_irr": 0, "linked_expense_coverage_irr": 0,
            "operating_envelope_outflow_irr": 0, "payable_outflow_irr": 0,
            "expected_receipts_irr": 0, "opening_balance_irr": money(balance) if balance is not None else None,
            "minimum_balance_irr": money(balance) if balance is not None else None})
        if balance is not None:
            balance += receipts - payables - operating
            minimum = min(minimum, balance)
            row["minimum_balance_irr"] = min(row["minimum_balance_irr"], money(balance))
            if balance < 0 and first_shortage is None:
                first_shortage = day.isoformat()
        row["days_in_horizon"] += 1
        amounts = {"period_expense_budget_irr": day_budget, "linked_expense_coverage_irr": day_budget - operating,
                   "operating_envelope_outflow_irr": operating, "payable_outflow_irr": payables, "expected_receipts_irr": receipts}
        for key, value in amounts.items():
            row[key] += value
            totals[key] += value
        row["closing_balance_irr"] = money(balance) if balance is not None else None
        row["required_extra_collections_irr"] = max(0, -row["minimum_balance_irr"]) if balance is not None else None
        row["net_flow_irr"] = row["expected_receipts_irr"] - row["payable_outflow_irr"] - row["operating_envelope_outflow_irr"]
        daily.append({"date": day.isoformat(), "month": month, **amounts,
                      "projected_balance_irr": money(balance) if balance is not None else None})
    totals.update(closing_balance_irr=money(balance) if balance is not None else None,
                  minimum_balance_irr=money(minimum) if minimum is not None else None,
                  required_extra_collections_irr=max(0, -money(minimum)) if minimum is not None else None,
                  first_shortage=first_shortage)
    return {"plan": policy, "start": today.isoformat(), "end": end.isoformat(), "days": 91,
            "projection_status": "source_complete_scenario" if source_complete else "illustrative_incomplete_sources",
            "estimated": True, "health_confirmed": False,
            "scenario_obligations_covered": bool(source_complete and minimum >= 0),
            "opening_balance_irr": money(opening) if opening is not None else None,
            "opening_source": "holoo_only", "months": list(months.values()), "daily": daily, "totals": totals,
            "readiness": {"complete": source_complete, "sources": readiness_sources, "balance_known": opening is not None,
                          "blockers": blockers},
            "coverage": counts, "warnings": warnings,
            "methods": ["واحد محاسبه ریال است؛ گرد کردن با روش نیم به بالا و توزیع تجمعی روزانه انجام می‌شود.",
                        "دریافتنی باز در احتمال وصول ضرب می‌شود و وصول چک برگشتی صفر است؛ پرداختنی باز یا برگشتی به مبلغ کامل منظور می‌شود.",
                        "تعهد عقب‌افتاده در اولین روز سناریو قرار می‌گیرد؛ سند تسویه، وصول یا لغوشده دوباره پرداخت یا دریافت نمی‌شود.",
                        "اسناد پرداختنی با پیوند صریح هزینه از پوشش همان ماه کم می‌شوند، حتی اگر تسویه شده باشند؛ فقط اسناد باز دوباره در تعهد نقد ظاهر می‌شوند.",
                        "مبالغ وصول لازم صرفاً کسری بیشترین ماندهٔ منفی در سناریو هستند و هدف فروش یا وعدهٔ وصول نیستند."]}
