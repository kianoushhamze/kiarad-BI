"""Deterministic financial planning. Amounts are IRR; projections are not cash entries."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import jdatetime

D = Decimal
OPEN_STATUSES = {"open", "overdue", "bounced"}
RECEIVABLE_TYPES = {"receivable", "receivable_check"}
PAYABLE_TYPES = {"payable", "payable_check"}
MONEY_FIELDS = (
    "revenue", "returns", "discounts", "cogs", "variable_costs", "fixed_costs",
    "finance_costs", "taxes", "other_income",
)
OPTIONAL_FIELDS = (
    "credit_sales", "average_receivables", "average_inventory", "credit_purchases",
    "average_payables", "current_assets", "current_liabilities",
)


def dec(value):
    result = D(str(0 if value is None else value))
    if not result.is_finite():
        raise ValueError("مبلغ باید عدد محدود باشد.")
    return result


def money(value):
    return int(dec(value).quantize(D("1"), rounding=ROUND_HALF_UP))


def ratio(numerator, denominator, multiplier=100):
    return float((dec(numerator) / dec(denominator) * dec(multiplier)).quantize(D("0.01"))) if dec(denominator) > 0 else None


def month_key(value):
    normalized = str(value).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")).replace("/", "-")
    pieces = normalized.split("-")
    if len(pieces) != 2 or len(pieces[0]) != 4 or not all(part.isdigit() for part in pieces):
        raise ValueError("ماه شمسی را مانند ۱۴۰۵-۰۷ وارد کنید.")
    year, month = map(int, pieces)
    if not 1200 <= year <= 1600 or not 1 <= month <= 12:
        raise ValueError("ماه شمسی معتبر نیست.")
    return f"{year:04d}-{month:02d}"


def month_index(value):
    year, month = map(int, month_key(value).split("-"))
    return year * 12 + month - 1


def month_from_index(index):
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_of(day):
    return jdatetime.date.fromgregorian(date=day).strftime("%Y-%m")


def month_days(month):
    year, number = map(int, month_key(month).split("-"))
    return 31 if number <= 6 else 30 if number <= 11 or jdatetime.date(year, 1, 1).isleap() else 29


def recurring_dates(start, end, due_day):
    for index in range(month_index(month_of(start)), month_index(month_of(end)) + 1):
        year, number = map(int, month_from_index(index).split("-"))
        day = jdatetime.date(year, number, min(int(due_day), month_days(f"{year}-{number}"))).togregorian()
        if start <= day <= end:
            yield day


def profit_statement(values, month):
    v = {field: dec(values[field]) for field in MONEY_FIELDS}
    net_sales = v["revenue"] - v["returns"] - v["discounts"]
    gross_profit = net_sales - v["cogs"]
    contribution = gross_profit - v["variable_costs"]
    operating = contribution - v["fixed_costs"]
    net = operating + v["other_income"] - v["finance_costs"] - v["taxes"]
    break_even = v["fixed_costs"] * net_sales / contribution if contribution > 0 and net_sales > 0 else None
    result = {
        "net_sales": money(net_sales), "gross_profit": money(gross_profit),
        "contribution": money(contribution), "operating_profit": money(operating), "net_profit": money(net),
        "gross_margin_percent": ratio(gross_profit, net_sales),
        "net_margin_percent": ratio(net, net_sales),
        "contribution_margin_percent": ratio(contribution, net_sales),
        "break_even_sales": money(break_even) if break_even is not None else None,
        "days_in_month": month_days(month),
    }
    n = result["days_in_month"]
    optional = {key: None if values.get(key) is None else dec(values[key]) for key in OPTIONAL_FIELDS}
    result["dso"] = ratio(optional["average_receivables"], optional["credit_sales"], n) if optional["average_receivables"] is not None and optional["credit_sales"] is not None else None
    result["dio"] = ratio(optional["average_inventory"], v["cogs"], n) if optional["average_inventory"] is not None else None
    result["dpo"] = ratio(optional["average_payables"], optional["credit_purchases"], n) if optional["average_payables"] is not None and optional["credit_purchases"] is not None else None
    result["cash_conversion_days"] = round(result["dso"] + result["dio"] - result["dpo"], 2) if all(result[key] is not None for key in ("dso", "dio", "dpo")) else None
    result["current_ratio"] = ratio(optional["current_assets"], optional["current_liabilities"], 1) if optional["current_assets"] is not None and optional["current_liabilities"] is not None else None
    return result


def growth_targets(baseline_month, baseline_profit, growth_percent, end_month, actuals):
    if not baseline_month or baseline_profit is None:
        return {"status": "baseline_missing", "rows": []}
    start, end = month_index(baseline_month), month_index(end_month)
    if not 0 <= end - start <= 24:
        raise ValueError("افق هدف باید از ماه مبنا تا حداکثر ۲۴ ماه بعد باشد.")
    if dec(baseline_profit) <= 0:
        return {"status": "positive_baseline_required", "rows": []}
    rows = []
    for index in range(start, end + 1):
        month = month_from_index(index)
        target = money(dec(baseline_profit) * (1 + dec(growth_percent) / 100) ** (index - start))
        actual = actuals.get(month)
        value = actual["statement"]["net_profit"] if actual and actual.get("approved_by") else None
        rows.append({"month": month, "target": target, "actual": value,
                     "gap": money(target - value) if value is not None else None,
                     "attainment_percent": ratio(value, target) if value is not None else None})
    return {"status": "ready", "rows": rows}


def growth_scenario(values, assumptions, target_profit=None):
    """Sensitivity holds units/cost mix constant except explicit inputs. Never writes a sale."""
    base = profit_statement(values, assumptions["month"])
    sales = dec(base["net_sales"])
    volume = 1 + dec(assumptions.get("volume_change_percent", 0)) / 100
    price = 1 + dec(assumptions.get("price_change_percent", 0)) / 100
    unit_cost = 1 + dec(assumptions.get("unit_cost_change_percent", 0)) / 100
    fixed_factor = 1 + dec(assumptions.get("fixed_cost_change_percent", 0)) / 100
    net_sales = sales * volume * price
    cogs = dec(values["cogs"]) * volume * unit_cost
    variable = dec(values["variable_costs"]) * volume * price
    fixed = dec(values["fixed_costs"]) * fixed_factor
    profit = net_sales - cogs - variable - fixed - dec(values["finance_costs"]) - dec(values["taxes"]) + dec(values["other_income"])
    cm = dec(base["contribution"]) / sales if sales > 0 else D(0)
    required_sales = ((dec(target_profit) + dec(values["fixed_costs"]) + dec(values["finance_costs"]) + dec(values["taxes"]) - dec(values["other_income"])) / cm) if target_profit is not None and cm > 0 else None
    return {"net_sales": money(net_sales), "net_profit": money(profit),
            "profit_change": money(profit - base["net_profit"]), "net_margin_percent": ratio(profit, net_sales),
            "required_sales_at_current_margin": max(0, money(required_sales)) if required_sales is not None else None,
            "target_profit": target_profit,
            "assumptions": "سناریوی فرضی با ترکیب کالای ثابت؛ هزینهٔ متغیر متناسب با فروش، بهای کالا متناسب با حجم و قیمت خرید، و مالیات و هزینهٔ مالی ثابت است."}


def document_direction(doc):
    if doc["document_type"] in RECEIVABLE_TYPES:
        return "receivable"
    if doc["document_type"] in PAYABLE_TYPES:
        return "payable"
    return None


def collection_analysis(documents, today):
    buckets = [{"id": key, "label": label, "receivable": 0, "payable": 0, "count": 0} for key, label in (
        ("current", "سررسید نرسیده"), ("overdue_1_7", "۱ تا ۷ روز گذشته"),
        ("overdue_8_30", "۸ تا ۳۰ روز گذشته"), ("overdue_31_60", "۳۱ تا ۶۰ روز گذشته"),
        ("overdue_61_90", "۶۱ تا ۹۰ روز گذشته"), ("overdue_90_plus", "بیش از ۹۰ روز گذشته"))]
    grouped = {}
    queue = []
    duplicates = defaultdict(list)
    for doc in documents:
        direction = document_direction(doc)
        if direction is None or doc["status"] not in OPEN_STATUSES:
            continue
        amount, due = money(doc["amount"]), doc["due_date"]
        age = max(0, (today - due).days)
        index = 0 if age == 0 else 1 if age <= 7 else 2 if age <= 30 else 3 if age <= 60 else 4 if age <= 90 else 5
        buckets[index][direction] += amount
        buckets[index]["count"] += 1
        if doc.get("reference_number"):
            duplicates[(direction, str(doc["reference_number"]).strip())].append(doc["id"])
        if direction == "receivable":
            # Never merge distinct customers merely because display names match.
            key = f"customer:{doc['customer_id']}" if doc.get("customer_id") else f"name:{doc['counterparty']}"
            entry = grouped.setdefault(key, {"counterparty": doc["counterparty"], "customer_id": doc.get("customer_id"), "balance": 0, "overdue": 0})
            entry["balance"] += amount
            entry["overdue"] += amount if age else 0
        queue.append({"id": doc["id"], "counterparty": doc["counterparty"], "direction": direction,
                      "amount": amount, "due_date": due, "overdue_days": age, "status": doc["status"],
                      "customer_id": doc.get("customer_id"), "bounced": doc["status"] == "bounced"})
    ranked = sorted(grouped.values(), key=lambda item: item["balance"], reverse=True)
    total = sum(entry["balance"] for entry in ranked)
    for entry in ranked:
        entry["share_percent"] = ratio(entry["balance"], total)
    queue.sort(key=lambda item: (not item["bounced"], -item["overdue_days"], item["due_date"], -item["amount"], item["id"]))
    return {"aging": buckets, "queue": queue, "concentration": ranked,
            "top_five_share_percent": ratio(sum(entry["balance"] for entry in ranked[:5]), total),
            "duplicate_references": [ids for ids in duplicates.values() if len(ids) > 1]}


def liquidity_projection(accounts, documents, expenses, today, assumptions=None):
    settings = assumptions or {}
    days = 91
    end = today + timedelta(days=days - 1)
    opening = sum((dec(row["current_balance"]) for row in accounts), D(0))
    reserve = sum((dec(row["minimum_reserve"]) for row in accounts), D(0))
    inflow_factor = dec(settings.get("collection_percent", 100)) / 100
    delay = int(settings.get("collection_delay_days", 0))
    extra = dec(settings.get("extra_outflow", 0))
    events = defaultdict(list)
    covered = defaultdict(lambda: D(0))
    for doc in documents:
        if document_direction(doc) == "payable" and doc.get("fixed_expense_id") and doc["status"] != "cancelled":
            covered[(doc["fixed_expense_id"], month_of(doc["due_date"]))] += dec(doc["amount"])
        if doc["status"] not in OPEN_STATUSES or not document_direction(doc):
            continue
        incoming = document_direction(doc) == "receivable"
        effective = max(doc["due_date"], today)
        probability = max(D(0), min(D(1), dec(doc.get("collection_probability", 1)))) if incoming else D(1)
        if incoming and doc["status"] == "bounced":
            probability = D(0)
        amount = dec(doc["amount"])
        if effective <= end:
            events[effective].append(("base", amount * probability if incoming else -amount))
            events[effective].append(("no_inflows", D(0) if incoming else -amount))
        scenario_day = effective + timedelta(days=delay) if incoming else effective
        if scenario_day <= end:
            events[scenario_day].append(("scenario", amount * probability * inflow_factor if incoming else -amount))
    for expense in expenses:
        for day in recurring_dates(today, end, expense["due_day"]):
            amount = max(D(0), dec(expense["amount"]) - covered[(expense["id"], month_of(day))])
            for key in ("base", "no_inflows", "scenario"):
                if key != "scenario" or settings.get("include_recurring", True):
                    events[day].append((key, -amount))
    if extra:
        events[today].append(("scenario", -extra))
    balances = {key: opening for key in ("base", "no_inflows", "scenario")}
    weeks, first_shortage = [], {key: today if opening < reserve else None for key in balances}
    minimum = balances.copy()
    totals = {key: {"inflow": D(0), "outflow": D(0)} for key in balances}
    for offset in range(days):
        day = today + timedelta(days=offset)
        for key, amount in events[day]:
            balances[key] += amount
            totals[key]["inflow" if amount >= 0 else "outflow"] += abs(amount)
        for key, value in balances.items():
            minimum[key] = min(minimum[key], value)
            if value < reserve and first_shortage[key] is None:
                first_shortage[key] = day
        if offset % 7 == 0:
            weeks.append({"start": day, "end": min(day + timedelta(days=6), end)})
        weeks[-1].update({key: money(value) for key, value in balances.items()})
        for key in balances:
            weeks[-1][f"{key}_minimum"] = min(weeks[-1].get(f"{key}_minimum", money(balances[key])), money(balances[key]))
    summaries = {key: {"closing": money(value), "minimum": money(minimum[key]),
                       "shortage": max(0, money(reserve - minimum[key])), "first_shortage": first_shortage[key],
                       "inflow": money(totals[key]["inflow"]), "outflow": money(totals[key]["outflow"])} for key, value in balances.items()}
    return {"start": today, "end": end, "weeks": weeks, "opening": money(opening),
            "reserve": money(reserve), "scenarios": summaries, "cash_accounts_available": bool(accounts)}
