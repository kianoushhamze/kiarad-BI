"""Pure, conservative purchase-cost estimates; never approved accounting profit.

All public amounts are integer IRR. Missing or ambiguous source evidence remains
unknown. This module neither accesses the database nor calls Holoo.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import jdatetime


D = Decimal
KINDS = ("purchases", "sales", "purchase_returns", "sales_returns")
TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class EvidenceError(ValueError):
    """Evidence is missing, contradictory, or ambiguous."""


def _number(value, default=None):
    if value is None or value == "":
        if default is not None:
            return D(default)
        raise EvidenceError("مبلغ یا تعداد لازم موجود نیست.")
    if isinstance(value, bool):
        raise EvidenceError("مقدار منطقی، مبلغ یا تعداد معتبر نیست.")
    try:
        result = D(str(value).translate(TRANSLATION).replace(",", "").replace("٬", ""))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EvidenceError("مبلغ یا تعداد معتبر نیست.") from exc
    if not result.is_finite():
        raise EvidenceError("مبلغ یا تعداد محدود نیست.")
    return result


def _money(value):
    return int(value.quantize(D(1), rounding=ROUND_HALF_UP))


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    normalized = str(value or "").translate(TRANSLATION).strip().replace("/", "-")
    pieces = normalized[:10].split("-")
    if len(pieces) != 3:
        raise EvidenceError("تاریخ سند معتبر نیست.")
    try:
        year, month, day = map(int, pieces)
        if 1200 <= year <= 1600:
            return jdatetime.date(year, month, day).togregorian()
        return date(year, month, day)
    except (ValueError, TypeError) as exc:
        raise EvidenceError("تاریخ سند معتبر نیست.") from exc


def _month(day):
    return jdatetime.date.fromgregorian(date=day).strftime("%Y-%m")


def _month_bounds(month):
    year, number = map(int, month.split("-"))
    begin = jdatetime.date(year, number, 1).togregorian()
    finish = jdatetime.date(year + (number == 12), 1 if number == 12 else number + 1, 1).togregorian()
    return begin, finish


def _months(start, end):
    current = _month(start)
    while True:
        begin, finish = _month_bounds(current)
        if begin > end:
            return
        yield current, begin, finish
        current = _month(finish)


def _key(row, names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise EvidenceError("شناسهٔ پایدار سند یا کالا موجود نیست.")


def _close(left, right, factor, rounding_rials=1):
    # One rial rounding tolerance, independent of the source currency.
    return abs(left - right) * factor <= rounding_rials


def _normalize_invoice(row, factor, semantics=None):
    """Reconcile one invoice without subtracting equivalent discounts twice.

    Default header semantics are final payable, including explicitly reported
    tax amounts. A caller may supply verified ``header_sum_price`` semantics
    ``before_header_discount`` or ``before_all_discounts``. Unsupported or
    ambiguous combinations are rejected instead of inferred from totals.
    """
    semantics = semantics or {}
    details = row.get("Detail")
    if not isinstance(details, list) or not details:
        raise EvidenceError("ردیف‌های کامل فاکتور موجود نیست.")
    items = []
    for detail in details:
        if not isinstance(detail, dict):
            raise EvidenceError("ساختار ردیف فاکتور معتبر نیست.")
        product = _key(detail, ("ProductErpCode", "ProductCode"))
        quantity = _number(detail.get("Few"))
        price = _number(detail.get("Price"))
        if quantity <= 0 or price < 0:
            raise EvidenceError("تعداد باید مثبت و قیمت نامنفی باشد.")
        gross = quantity * price
        amount_discount = _number(detail.get("Discount"), 0)
        percent = _number(detail.get("PersentDiscount"), 0)
        if amount_discount < 0 or not 0 <= percent <= 100:
            raise EvidenceError("تخفیف ردیف معتبر نیست.")
        percent_discount = gross * percent / 100
        if amount_discount and percent and not _close(amount_discount, percent_discount, factor):
            raise EvidenceError("تخفیف مبلغی و درصدی ردیف با هم منطبق نیستند.")
        discount = amount_discount if amount_discount else percent_discount
        if discount > gross:
            raise EvidenceError("تخفیف ردیف از مبلغ ناخالص بیشتر است.")
        net = gross - discount
        if detail.get("SumPrice") is not None:
            shown = _number(detail["SumPrice"])
            if not (_close(shown, gross, factor) or _close(shown, net, factor)):
                raise EvidenceError("مبلغ ردیف با تعداد، قیمت و تخفیف تطبیق ندارد.")
        items.append({"product": product, "quantity": quantity, "net": net,
                      "gross": gross, "discount": discount})
    gross = sum((item["gross"] for item in items), D(0))
    line_discount = sum((item["discount"] for item in items), D(0))
    subtotal = gross - line_discount
    header_discount = _number(row.get("SumDiscount"), 0)
    levy, scot = _number(row.get("SumLevy"), 0), _number(row.get("SumScot"), 0)
    if min(levy, scot) < 0:
        raise EvidenceError("مالیات و عوارض باید نامنفی باشند.")
    tax = levy + scot
    shown = _number(row.get("SumPrice"))
    if min(header_discount, tax, shown) < 0:
        raise EvidenceError("مبلغ سربرگ منفی است.")
    if tax and semantics.get("tax_fields", "amounts") != "amounts":
        raise EvidenceError("معنای مبلغ مالیات و عوارض تأیید نشده است.")
    tolerance = max(D(1), D(len(items)) / 2)
    scope = semantics.get("header_discount_scope", "reconcile_only")
    extra_candidates = set()
    if scope in {"additional", "reconcile_only"}:
        extra_candidates.add(header_discount)
    if scope in {"includes_line_discounts", "reconcile_only"}:
        if header_discount >= line_discount:
            extra_candidates.add(header_discount - line_discount)
        elif _close(header_discount, line_discount, factor, tolerance):
            extra_candidates.add(D(0))
    mode = semantics.get("header_sum_price", "final_payable")
    payment_keys = ("SumNaghd", "SumCard", "SumNesiyeh", "SumCheck")
    payments = None
    if all(key in row and row[key] is not None for key in payment_keys):
        parts = [_number(row[key]) for key in payment_keys]
        if min(parts) < 0:
            raise EvidenceError("جزء پرداخت منفی است.")
        payments = sum(parts, D(0))
    accepted = []
    for extra in extra_candidates:
        if extra > subtotal:
            continue
        net = subtotal - extra
        expected = net + tax if mode == "final_payable" else subtotal + tax if mode == "before_header_discount" else gross + tax if mode == "before_all_discounts" else gross if mode == "gross_before_discount_tax" else None
        if expected is None or not _close(expected, shown, factor, tolerance):
            continue
        # A reconciled gross header controls rounding; do not fabricate 2.2 rial
        # of stock value when independently rounded detail sums differ.
        if mode == "gross_before_discount_tax":
            net = shown - header_discount if scope == "includes_line_discounts" else shown - line_discount - extra
        if net < 0 or (payments is not None and not _close(payments, net + tax, factor, tolerance)):
            continue
        accepted.append((net, extra))
    unique = {(net, extra) for net, extra in accepted}
    if len(unique) != 1:
        raise EvidenceError("مدل مبلغ کل و تخفیف سربرگ یکتا تطبیق ندارد.")
    net_total, extra = unique.pop()
    if extra and not subtotal:
        raise EvidenceError("تخصیص تخفیف کل بدون مبنای مثبت ممکن نیست.")
    for item in items:
        item["net"] = (net_total * item["net"] / subtotal if subtotal else D(0)) * factor
    return items, net_total * factor, {
        "gross": shown * factor if mode == "gross_before_discount_tax" else gross * factor,
        "discount": ((shown if mode == "gross_before_discount_tax" else gross) - net_total) * factor,
        "tax": tax * factor, "payment_reconciled": payments is not None,
        "purchase_tax_recoverability": semantics.get("purchase_tax_recoverability", "unknown")}


def _time(row):
    value = row.get("Time") or row.get("time")
    if not value:
        text = str(row.get("Date", ""))
        value = text[11:] if len(text) > 11 and text[10] in " T" else None
    if not value:
        return None
    try:
        return datetime.strptime(str(value).translate(TRANSLATION)[:8], "%H:%M:%S").time()
    except ValueError:
        return None


def estimate_purchase_profit(payload, monthly_expense_irr=3000000000, detail_from=None):
    """Estimate monthly profit from reconciled invoices and prior known stock.

    Opening inventory and its historical value are always unknown here. Output
    therefore never represents approved profit or attainment of growth targets.
    Monthly operating expense is one combined budget assumption, prorated over
    the extraction interval; it is not added again as payroll or variable cost.
    """
    result = {"status": "blocked", "method": "moving_weighted_average_known_purchases",
              "currency": "IRR", "opening_inventory_known": False,
              "approved_profit": False, "growth_attainment_available": False,
              "months": [], "blockers": [], "coverage": {},
              "limitations": ["موجودی و ارزش ابتدای دوره نامشخص است؛ این خروجی فقط برآورد است.",
                              "بهای کالا فقط از خریدهای معتبر پیش از فروش محاسبه می‌شود؛ خرید ماه جای بهای فروش‌رفته نیست.",
                              "هزینهٔ ماهانه، فرض بودجهٔ مجموع هزینه‌هاست؛ عملکرد واقعی یا تقسیم هزینهٔ ثابت و متغیر نیست."]}
    result["limitations"].append("برآورد پس از بودجه، تأیید سود حسابداری نیست؛ پوشش هزینهٔ مالی، مالیات دوره و سایر درآمدها در بودجه باید جداگانه تأیید شود.")
    try:
        expense = _number(monthly_expense_irr)
        factor = _number(payload.get("currency_factor"))
        start, end = _day(payload.get("from_date")), _day(payload.get("to_date"))
        if expense < 0 or factor not in (1, 10) or end < start or (end - start).days > 1100:
            raise EvidenceError("واحد پول، هزینه یا بازهٔ استخراج معتبر نیست.")
    except (EvidenceError, TypeError, AttributeError) as exc:
        result["blockers"].append({"code": "invalid_context", "reason": str(exc)})
        return result

    result["monthly_expense_irr"] = _money(expense)
    product_start = _day(detail_from) if detail_from else start
    product_totals = defaultdict(lambda: {"revenue": D(0), "cogs": D(0), "lines": 0, "costed": 0, "tax_unknown": False})
    result["from_date"], result["to_date"] = start.isoformat(), end.isoformat()
    monthly = {}
    for month, begin, finish in _months(start, end):
        days = (finish - begin).days
        covered = (min(end + timedelta(days=1), finish) - max(start, begin)).days
        monthly[month] = {"month": month, "days_in_month": days, "covered_days": covered,
                          "partial_month": covered != days,
                          "budget_full_month_expense_irr": _money(expense),
                          "budget_expense_for_period_irr": _money(expense * covered / days),
                          "sales_invoices": 0, "sales_return_invoices": 0,
                          "sales_lines": 0, "costed_sales_lines": 0,
                          "purchase_invoices": 0, "purchase_return_invoices": 0,
                          "purchase_gross_irr": None, "purchase_discount_irr": None,
                          "purchase_net_irr": None, "purchase_return_net_irr": None,
                          "sales_gross_irr": None, "sales_discount_irr": None,
                          "sales_return_net_irr": None,
                          "net_sales_irr": None, "known_net_sales_irr": 0,
                          "estimated_cogs_irr": None, "known_cogs_irr": 0,
                          "estimated_gross_profit_irr": None, "estimated_net_profit_irr": None,
                          "estimated_gross_profit_before_unverified_purchase_tax_irr": None,
                          "estimated_profit_before_unverified_purchase_tax_irr": None,
                          "purchase_tax_policy_verified_for_costed_sales": None,
                          "net_profit_irr": None, "coverage_complete": False,
                          "blockers": [], "_sales": D(0), "_cogs": D(0),
                          "_revenue_bad": False, "_cost_bad": False, "_purchase_bad": False,
                          "_tax_bad": False, "_metrics": defaultdict(lambda: D(0))}

    def issue(code, reason, event=None, product=None, global_scope=False):
        entry = {"code": code, "reason": reason}
        if event:
            entry.update(kind=event["kind"], invoice_ref=event["key"], month=event["month"])
        if product:
            entry["product"] = product
        result["blockers"].append(entry)
        targets = monthly.values() if global_scope or event is None else [monthly[event["month"]]]
        for month in targets:
            if code not in month["blockers"]:
                month["blockers"].append(code)

    sources = payload.get("sources") or {}
    if not isinstance(sources, dict):
        sources = {}
    amount_semantics = payload.get("invoice_amount_semantics") or {}
    if not isinstance(amount_semantics, dict):
        amount_semantics = {}
        issue("invalid_amount_semantics", "ساختار قواعد مبلغ فاکتور معتبر نیست.", global_scope=True)
    source_complete = True
    complete_by_kind = {}
    events = []
    for kind in KINDS:
        source = sources.get(kind, {})
        if not isinstance(source, dict):
            source = {}
        complete_by_kind[kind] = bool(source.get("ok") and source.get("complete") and isinstance(source.get("rows"), list))
        if not complete_by_kind[kind]:
            source_complete = False
            issue("incomplete_source", "منبع خرید، فروش یا برگشت کامل و موفق نیست.", global_scope=True)
        seen = set()
        for row in source.get("rows", []) if isinstance(source.get("rows"), list) else []:
            try:
                if not isinstance(row, dict):
                    raise EvidenceError("ساختار فاکتور معتبر نیست.")
                day = _day(row.get("Date"))
                if not start <= day <= end:
                    raise EvidenceError("تاریخ سند خارج از بازهٔ اعلام‌شده است.")
                key = _key(row, ("ErpCode", "SanadCode", "Code", "FCode"))
                if key in seen:
                    raise EvidenceError("شناسهٔ تکراری فاکتور وجود دارد.")
                seen.add(key)
            except EvidenceError as exc:
                source_complete = False
                complete_by_kind[kind] = False
                issue("invalid_invoice_identity", str(exc), global_scope=True)
                continue
            event = {"kind": kind, "key": key, "day": day, "month": _month(day),
                     "time": _time(row), "row": row}
            try:
                semantics = amount_semantics.get(kind, {})
                if not isinstance(semantics, dict):
                    raise EvidenceError("قواعد مبلغ این نوع فاکتور معتبر نیست.")
                event["items"], event["net"], event["metrics"] = _normalize_invoice(row, factor, semantics)
            except EvidenceError as exc:
                event["items"], event["net"] = None, None
                issue("invoice_amount_ambiguous", str(exc), event)
            events.append(event)

    pools = defaultdict(lambda: {"quantity": D(0), "value": D(0), "tainted": False, "tax_unverified": False})
    history = defaultdict(list)
    unidentified_stock_event = False
    by_day = defaultdict(list)
    for event in events:
        by_day[event["day"]].append(event)

    def apply_purchase(event):
        nonlocal unidentified_stock_event
        month = monthly[event["month"]]
        returned = event["kind"] == "purchase_returns"
        month["purchase_return_invoices" if returned else "purchase_invoices"] += 1
        if event["items"] is None:
            month["_purchase_bad"] = True
            # An invalid purchase can alter every matching product's average.
            details = event["row"].get("Detail")
            if not isinstance(details, list) or not details:
                unidentified_stock_event = True
            for detail in details if isinstance(details, list) else []:
                if isinstance(detail, dict):
                    try:
                        pools[_key(detail, ("ProductErpCode", "ProductCode"))]["tainted"] = True
                    except EvidenceError:
                        unidentified_stock_event = True
                else:
                    unidentified_stock_event = True
            return
        if returned:
            month["_metrics"]["purchase_return_net_irr"] += event["net"]
        else:
            month["_metrics"]["purchase_gross_irr"] += event["metrics"]["gross"]
            month["_metrics"]["purchase_discount_irr"] += event["metrics"]["discount"]
            month["_metrics"]["purchase_net_irr"] += event["net"]
        unverified_tax = bool(event["metrics"]["tax"] and event["metrics"]["purchase_tax_recoverability"] not in {"recoverable", "nonrecoverable"})
        grouped = defaultdict(lambda: {"quantity": D(0), "value": D(0)})
        for item in event["items"]:
            grouped[item["product"]]["quantity"] += item["quantity"]
            value = item["net"]
            if event["metrics"]["purchase_tax_recoverability"] == "nonrecoverable" and event["net"] > 0:
                value += event["metrics"]["tax"] * item["net"] / event["net"]
            grouped[item["product"]]["value"] += value
        if event["kind"] == "purchases" and len(grouped) > 1 and any(item["value"] == 0 for item in grouped.values()) and any(item["value"] > 0 for item in grouped.values()):
            for product in grouped:
                pools[product]["tainted"] = True
            issue("mixed_product_offer_allocation_unknown", "افر کالای متفاوت به مبنای تخصیص مصوب نیاز دارد؛ بهای هدیه صفر فرض نشد.", event)
            return
        for product, item in grouped.items():
            pool = pools[product]
            pool["tax_unverified"] = unverified_tax if pool["quantity"] == 0 and pool["value"] == 0 and not pool["tainted"] else pool["tax_unverified"] or unverified_tax
            if event["kind"] == "purchases":
                pool["quantity"] += item["quantity"]
                pool["value"] += item["value"]
            elif item["quantity"] > pool["quantity"] or item["value"] > pool["value"]:
                pool["tainted"] = True
                issue("purchase_return_unknown_cost", "برگشت خرید از موجودی و بهای شناخته‌شده بیشتر است.", event, product)
            else:
                pool["quantity"] -= item["quantity"]
                pool["value"] -= item["value"]
                if pool["quantity"] == 0 and pool["value"] != 0:
                    pool["tainted"] = True
                    issue("purchase_return_value_mismatch", "پس از برگشت، تعداد صفر و ارزش غیرصفر است.", event, product)

    def apply_sale(event):
        nonlocal unidentified_stock_event
        month = monthly[event["month"]]
        is_return = event["kind"] == "sales_returns"
        month["sales_return_invoices" if is_return else "sales_invoices"] += 1
        if event["items"] is None:
            month["_revenue_bad"], month["_cost_bad"] = True, True
            details = event["row"].get("Detail")
            if not isinstance(details, list) or not details:
                unidentified_stock_event = True
            for detail in details if isinstance(details, list) else []:
                if isinstance(detail, dict):
                    try:
                        pools[_key(detail, ("ProductErpCode", "ProductCode"))]["tainted"] = True
                    except EvidenceError:
                        unidentified_stock_event = True
                else:
                    unidentified_stock_event = True
            return
        month["_sales"] += event["net"] * (-1 if is_return else 1)
        if is_return:
            month["_metrics"]["sales_return_net_irr"] += event["net"]
        else:
            month["_metrics"]["sales_gross_irr"] += event["metrics"]["gross"]
            month["_metrics"]["sales_discount_irr"] += event["metrics"]["discount"]
        for item in event["items"]:
            month["sales_lines"] += 1
            product, quantity = item["product"], item["quantity"]
            tracked = event["day"] >= product_start
            if tracked:
                product_totals[product]["revenue"] += item["net"] * (-1 if is_return else 1)
                product_totals[product]["lines"] += 1
            pool = pools[product]
            if is_return:
                original = event["row"].get("OriginalInvoiceErpCode") or event["row"].get("ReferenceErpCode")
                candidates = [entry for entry in history[product] if entry["remaining"] > 0 and (not original or entry["invoice"] == str(original))]
                rates = {entry["rate"] for entry in candidates}
                available = sum((entry["remaining"] for entry in candidates), D(0))
                if len(rates) != 1 or available < quantity:
                    month["_cost_bad"] = True
                    pool["tainted"] = True
                    issue("sales_return_unknown_original_cost", "بهای فروش اصلیِ کالای برگشتی یکتا و کافی نیست.", event, product)
                    continue
                rate = rates.pop()
                if any(entry["tax_unverified"] for entry in candidates):
                    month["_tax_bad"] = True
                    issue("purchase_tax_policy_unknown", "قابلیت بازیافت مالیات خریدِ بهای مرجع مشخص نیست.", event, product)
                remaining = quantity
                for entry in candidates:
                    take = min(remaining, entry["remaining"])
                    entry["remaining"] -= take
                    remaining -= take
                    if not remaining:
                        break
                cost = rate * quantity
                pool["quantity"] += quantity
                pool["value"] += cost
                pool["tax_unverified"] = pool["tax_unverified"] or any(entry["tax_unverified"] for entry in candidates)
                month["_cogs"] -= cost
            elif unidentified_stock_event or pool["tainted"] or pool["quantity"] < quantity or pool["quantity"] <= 0:
                month["_cost_bad"] = True
                pool["tainted"] = True
                issue("missing_prior_purchase_cost", "خرید معتبر و تعداد کافی پیش از فروش موجود نیست؛ بهای صفر فرض نشد.", event, product)
                continue
            else:
                rate = pool["value"] / pool["quantity"]
                cost = rate * quantity
                pool["quantity"] -= quantity
                pool["value"] -= cost
                month["_cogs"] += cost
                history[product].append({"invoice": event["key"], "rate": rate, "remaining": quantity, "tax_unverified": pool["tax_unverified"]})
                if pool["tax_unverified"]:
                    month["_tax_bad"] = True
                    issue("purchase_tax_policy_unknown", "قابلیت بازیافت مالیات خریدِ بهای مرجع مشخص نیست.", event, product)
            month["costed_sales_lines"] += 1
            if tracked:
                product_totals[product]["costed"] += 1
                product_totals[product]["cogs"] += cost * (-1 if is_return else 1)
                product_totals[product]["tax_unknown"] |= pool["tax_unverified"]

    for day in sorted(by_day):
        daily = by_day[day]
        # Explicit times are usable only when every event that day has one.
        # Otherwise sales precede today's purchases, preventing look-ahead.
        if all(event["time"] is not None for event in daily):
            # Ties still process sales first: equal timestamps do not prove order.
            daily.sort(key=lambda event: (event["time"], event["kind"] in {"purchases", "purchase_returns"}, event["key"]))
        else:
            daily.sort(key=lambda event: (event["kind"] in {"purchases", "purchase_returns"}, event["key"]))
        for event in daily:
            (apply_purchase if event["kind"] in {"purchases", "purchase_returns"} else apply_sale)(event)

    complete_months = 0
    for month in monthly.values():
        month["known_net_sales_irr"] = _money(month.pop("_sales"))
        month["known_cogs_irr"] = _money(month.pop("_cogs"))
        revenue_ok = not month.pop("_revenue_bad") and complete_by_kind.get("sales", False) and complete_by_kind.get("sales_returns", False)
        cost_ok = not month.pop("_cost_bad") and source_complete
        purchase_ok = not month.pop("_purchase_bad") and complete_by_kind.get("purchases", False) and complete_by_kind.get("purchase_returns", False)
        tax_ok = not month.pop("_tax_bad")
        month["purchase_tax_policy_verified_for_costed_sales"] = tax_ok
        metrics = month.pop("_metrics")
        for key in ("purchase_gross_irr", "purchase_discount_irr", "purchase_net_irr", "purchase_return_net_irr"):
            if purchase_ok:
                month[key] = _money(metrics[key])
        for key in ("sales_gross_irr", "sales_discount_irr", "sales_return_net_irr"):
            if revenue_ok:
                month[key] = _money(metrics[key])
        if revenue_ok:
            month["net_sales_irr"] = month["known_net_sales_irr"]
        if cost_ok:
            month["estimated_cogs_irr"] = month["known_cogs_irr"]
        month["coverage_complete"] = revenue_ok and cost_ok and tax_ok
        if revenue_ok and cost_ok:
            gross = month["net_sales_irr"] - month["estimated_cogs_irr"]
            month["estimated_gross_profit_before_unverified_purchase_tax_irr"] = gross
            month["estimated_profit_before_unverified_purchase_tax_irr"] = gross - month["budget_expense_for_period_irr"]
        if month["coverage_complete"]:
            month["estimated_gross_profit_irr"] = month["estimated_gross_profit_before_unverified_purchase_tax_irr"]
            month["estimated_net_profit_irr"] = month["estimated_profit_before_unverified_purchase_tax_irr"]
            complete_months += 1
        result["months"].append(month)
    result["coverage"] = {"all_sources_complete": source_complete, "months": len(monthly),
                          "fully_costed_months": complete_months,
                          "sales_lines": sum(month["sales_lines"] for month in monthly.values()),
                          "costed_sales_lines": sum(month["costed_sales_lines"] for month in monthly.values())}
    result["status"] = "estimated" if complete_months == len(monthly) and source_complete else "partial" if events else "blocked"
    revenue_complete = complete_by_kind.get("sales") and complete_by_kind.get("sales_returns") and all(e["items"] is not None for e in events if e["kind"] in {"sales", "sales_returns"})
    result["products"] = []
    for code, value in product_totals.items():
        cost_complete = bool(source_complete and revenue_complete and value["lines"] == value["costed"] and not unidentified_stock_event)
        tax_verified = not value["tax_unknown"]
        result["products"].append({"product_erp_code": code, "sales_lines": value["lines"], "costed_sales_lines": value["costed"],
            "net_sales_irr": _money(value["revenue"]) if revenue_complete else None,
            "estimated_cogs_irr": _money(value["cogs"]) if cost_complete else None,
            "estimated_gross_profit_irr": _money(value["revenue"]-value["cogs"]) if cost_complete and tax_verified else None,
            "cost_complete": cost_complete, "purchase_tax_verified": tax_verified, "approved": False})
    result["product_from_date"] = product_start.isoformat()
    return result
