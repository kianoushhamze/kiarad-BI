"""Private treasury planning, source coverage and immutable monthly revisions."""
import json
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text

from db import engine
from iran_time import iran_today
from holoo_finance import latest_financial_snapshot, latest_financial_payload
from holoo_finance_jobs import financial_refresh_status, start_financial_refresh, start_automatic_refresh, stop_automatic_refresh
from treasury_operating_plan import default_operating_plan, operating_cash_plan
from purchase_profit import estimate_purchase_profit
from treasury import require_treasury_access
from treasury_finance import (
    collection_analysis, dec, growth_scenario,
    growth_targets, liquidity_projection, money, month_index, month_key, month_of,
    profit_statement,
)

router = APIRouter(prefix="/treasury/strategy", tags=["treasury"])


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)


class StrategySettings(StrictInput):
    expected_revision: int = Field(default=0, ge=0)
    baseline_month: str | None = None
    baseline_profit: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    monthly_growth_percent: Decimal = Field(default=20, ge=0, le=100)
    end_month: str
    source_note: str = Field(min_length=8, max_length=2000)

    @field_validator("baseline_month", "end_month")
    @classmethod
    def validate_month(cls, value):
        return month_key(value) if value else None

    @field_validator("source_note")
    @classmethod
    def validate_note(cls, value):
        if len(value.strip()) < 8:
            raise ValueError("منبع مبنا و دلیل تغییر هدف را بنویسید.")
        return value.strip()

    @model_validator(mode="after")
    def validate_window(self):
        if not self.end_month:
            raise ValueError("ماه پایان الزامی است.")
        if self.baseline_month:
            if not 0 <= month_index(self.end_month) - month_index(self.baseline_month) <= 24:
                raise ValueError("افق هدف حداکثر ۲۴ ماه است و نباید قبل از مبنا باشد.")
        elif self.baseline_profit is not None:
            raise ValueError("ماه سود مبنا را مشخص کنید.")
        return self


class MonthlyFinance(StrictInput):
    month: str
    kind: Literal["actual", "budget"]
    expected_revision: int = Field(default=0, ge=0)
    revenue: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    returns: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    discounts: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    cogs: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    variable_costs: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    fixed_costs: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    finance_costs: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    taxes: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    other_income: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    credit_sales: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    average_receivables: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    average_inventory: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    credit_purchases: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    average_payables: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    current_assets: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    current_liabilities: Decimal | None = Field(default=None, ge=0, le=10**16, decimal_places=0)
    source_note: str = Field(min_length=8, max_length=2000)
    coverage_confirmed: bool = False
    approve: bool = False

    @field_validator("month")
    @classmethod
    def validate_month(cls, value):
        return month_key(value)

    @field_validator("source_note")
    @classmethod
    def validate_source(cls, value):
        value = value.strip()
        if len(value) < 8:
            raise ValueError("منبع و دلیل اصلاح را بنویسید.")
        return value


class CashScenario(StrictInput):
    collection_percent: Decimal = Field(default=100, ge=0, le=100)
    collection_delay_days: int = Field(default=0, ge=0, le=90)
    extra_outflow: Decimal = Field(default=0, ge=0, le=10**16, decimal_places=0)
    include_recurring: bool = True


class ProfitScenario(StrictInput):
    month: str
    volume_change_percent: Decimal = Field(default=0, ge=-100, le=300)
    price_change_percent: Decimal = Field(default=0, ge=-100, le=300)
    unit_cost_change_percent: Decimal = Field(default=0, ge=-100, le=300)
    fixed_cost_change_percent: Decimal = Field(default=0, ge=-100, le=300)

    @field_validator("month")
    @classmethod
    def validate_month(cls, value):
        return month_key(value)


class ReconciliationPreview(StrictInput):
    account_id: int = Field(gt=0)
    statement_balance: Decimal = Field(ge=-(10**16), le=10**16, decimal_places=0)


class OperatingPlan(StrictInput):
    expected_revision: int = Field(default=0, ge=0)
    monthly_expense_irr: Decimal = Field(ge=0, le=10**16, decimal_places=0)
    balance_source: Literal["holoo", "excel"] = "holoo"
    bank_balances_current: bool = False
    receivable_checks_current: bool = False
    payable_checks_current: bool = False
    endorsed_checks_current: bool = False
    source_note: str = Field(min_length=8, max_length=2000)

    @field_validator("source_note")
    @classmethod
    def validate_note(cls, value):
        if len(value.strip()) < 8:
            raise ValueError("منبع بودجه و وضعیت اصلاح اطلاعات هلو را بنویسید.")
        return value.strip()


def ensure_schema(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS treasury_strategy_revisions (
        id BIGSERIAL PRIMARY KEY, scope VARCHAR(50) NOT NULL, revision INTEGER NOT NULL,
        payload JSONB NOT NULL, created_by INTEGER NOT NULL, approved_by INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(scope, revision))"""))
    if not conn.execute(text("SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass('financial_documents') AND attname='fixed_expense_id' AND NOT attisdropped")).first():
        conn.execute(text("ALTER TABLE financial_documents ADD COLUMN IF NOT EXISTS fixed_expense_id INTEGER"))


@router.on_event("startup")
def initialize_strategy_schema():
    with engine.begin() as conn:
    start_automatic_refresh()


@router.on_event("shutdown")
def stop_strategy_refresh():
    stop_automatic_refresh()


def _latest(conn, scope):
    return conn.execute(text("SELECT * FROM treasury_strategy_revisions WHERE scope=:scope ORDER BY revision DESC LIMIT 1"), {"scope": scope}).mappings().first()


def _save(conn, scope, expected, payload, user, approve=False):
    # Serialize per scope and reject lost updates from two browser sessions.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"), {"scope": "treasury-strategy:" + scope})
    previous = _latest(conn, scope)
    revision = previous["revision"] if previous else 0
    if revision != expected:
        raise HTTPException(409, "نسخهٔ جدیدتری ذخیره شده؛ اطلاعات را تازه کنید و دوباره بررسی کنید.")
    result = conn.execute(text("""INSERT INTO treasury_strategy_revisions(scope, revision, payload, created_by, approved_by)
        VALUES (:scope, :revision, CAST(:payload AS JSONB), :user, :approver) RETURNING *"""),
        {"scope": scope, "revision": revision + 1, "payload": json.dumps(payload, ensure_ascii=False),
         "user": user["id"], "approver": user["id"] if approve else None}).mappings().one()
    return serialize_report(result)


def serialize_report(row):
    item = dict(row)
    if item["scope"].startswith(("actual:", "budget:")):
        item["statement"] = profit_statement(item["payload"], item["payload"]["month"])
    return item


def _load_sources(conn):
    accounts = [dict(row) for row in conn.execute(text("SELECT * FROM cash_accounts WHERE is_active=1 ORDER BY id")).mappings()]
    documents = [dict(row) for row in conn.execute(text("SELECT * FROM financial_documents ORDER BY due_date, id")).mappings()]
    expenses = [dict(row) for row in conn.execute(text("SELECT * FROM fixed_expenses WHERE is_active=1 ORDER BY id")).mappings()]
    return accounts, documents, expenses


def _reports(conn):
    rows = conn.execute(text("""SELECT DISTINCT ON (scope) * FROM treasury_strategy_revisions
        WHERE scope LIKE 'actual:%' OR scope LIKE 'budget:%' ORDER BY scope, revision DESC""")).mappings().all()
    approved = conn.execute(text("""SELECT DISTINCT ON (scope) * FROM treasury_strategy_revisions
        WHERE scope LIKE 'actual:%' AND approved_by IS NOT NULL ORDER BY scope, revision DESC""")).mappings().all()
    return [serialize_report(row) for row in rows], {row["payload"]["month"]: serialize_report(row) for row in approved}


def default_settings(today):
    return {"baseline_month": None, "baseline_profit": None, "monthly_growth_percent": 20,
            "end_month": f"{month_of(today)[:4]}-12", "source_note": "هدف اعلام‌شدهٔ مدیر؛ ماه و سود مبنا هنوز تعیین نشده است."}


def action_list(projection, collections, reports, approved, targets):
    actions = []
    shortage = projection["scenarios"]["base"]["shortage"]
    if projection["cash_accounts_available"] and shortage:
        actions.append({"id": "cash-gap", "priority": "high", "title": "تأمین کسری وجه پیش از سررسید",
                        "amount": shortage, "reason": "کمترین ماندهٔ پیش‌بینی‌شده از ذخیرهٔ حساب‌ها کمتر است.", "href": "#treasury-cash"})
    overdue = sum(bucket["receivable"] for bucket in collections["aging"][1:])
    if overdue:
        actions.append({"id": "collect", "priority": "high", "title": "پیگیری مطالبات سررسیدگذشته",
                        "amount": overdue, "reason": "صف وصول بر اساس برگشت چک، روز تأخیر و مبلغ مرتب شده است.", "href": "#treasury-cash"})
    for report in reports:
        month = report["payload"]["month"]
        actual = approved.get(month)
        if report["scope"].startswith("budget:") and actual:
            budget_cost = sum(dec(report["payload"][field]) for field in ("variable_costs", "fixed_costs", "finance_costs"))
            actual_cost = sum(dec(actual["payload"][field]) for field in ("variable_costs", "fixed_costs", "finance_costs"))
            if actual_cost > budget_cost:
                actions.append({"id": f"budget-{month}", "priority": "medium", "title": f"بررسی اضافه‌هزینهٔ {month}",
                                "amount": money(actual_cost - budget_cost), "reason": "هزینهٔ عملیاتی و مالی واقعی از بودجهٔ همان ماه بیشتر است.", "href": "#treasury-profit"})
    for target in targets["rows"]:
        if target["gap"] is not None and target["gap"] > 0:
            actions.append({"id": f"growth-{target['month']}", "priority": "medium", "title": f"برنامهٔ جبران سود {target['month']}",
                            "amount": target["gap"], "reason": "سود تأییدشده از مسیر هدف کمتر است؛ حاشیهٔ سود، حجم و هزینه‌ها بررسی شوند.", "href": "#treasury-growth"})
    return actions


@router.get("/overview")
def strategy_overview(_: dict = Depends(require_treasury_access)):
    today = iran_today()
    with engine.begin() as conn:
        settings_row = _latest(conn, "settings")
        settings = settings_row["payload"] if settings_row else default_settings(today)
        reports, approved = _reports(conn)
        accounts, documents, expenses = _load_sources(conn)
        holoo_snapshot = latest_financial_snapshot(conn)
        holoo_payload = latest_financial_payload(conn, holoo_snapshot["id"]) if holoo_snapshot else None
        operating_row = _latest(conn, "operating-plan")
        operating_plan = operating_row["payload"] if operating_row else default_operating_plan()
        from treasury_excel import excel_balance_summary, excel_invoice_estimate
        excel_summary = excel_balance_summary(conn) if operating_plan.get("balance_source") == "excel" else None
        excel_estimate = excel_invoice_estimate(conn, operating_plan["monthly_expense_irr"])
        snapshot = conn.execute(text("SELECT id, snapshot_date, total_amount, row_count FROM receivable_snapshots ORDER BY snapshot_date DESC, id DESC LIMIT 1")).mappings().first()
        history = conn.execute(text("""SELECT id, scope, revision, created_by, approved_by, created_at,
            payload->>'source_note' AS source_note FROM treasury_strategy_revisions ORDER BY id DESC LIMIT 40""")).mappings().all()
    projection = liquidity_projection(accounts, documents, expenses, today)
    collections = collection_analysis(documents, today)
    targets = growth_targets(settings.get("baseline_month"), settings.get("baseline_profit"), settings["monthly_growth_percent"], settings["end_month"], approved)
    purchase_estimate = None
    if holoo_payload:
        # Verified against all four invoice families and the payment components;
        # the engine also reconciles every invoice, so refresh cannot silently drift.
        holoo_payload = {**holoo_payload, "invoice_amount_semantics": {
            kind: {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"}
            for kind in ("purchases", "sales", "purchase_returns", "sales_returns")}}
        purchase_estimate = estimate_purchase_profit(holoo_payload, monthly_expense_irr=operating_plan["monthly_expense_irr"])
    opening_summary = excel_summary if operating_plan.get("balance_source") == "excel" else holoo_snapshot
    operating_projection = operating_cash_plan(operating_plan, opening_summary, documents, today)
    operating_projection["opening_source"] = operating_plan.get("balance_source", "holoo")
    if operating_plan.get("balance_source") == "excel":
        for field in ("warnings", "methods"):
            operating_projection[field] = [message.replace("هلو", "گزارش اکسل") for message in operating_projection[field]]
        operating_projection["readiness"]["blockers"] = [message.replace("هلو", "گزارش اکسل") for message in operating_projection["readiness"]["blockers"]]
        for item in operating_projection["readiness"]["sources"]:
            item["label"] = item["label"].replace("هلو", "گزارش اکسل")
    coverage = [
        {"id": "balances", "label": "موجودی حساب‌ها", "available": bool(accounts), "detail": "ماندهٔ ثبت‌شدهٔ حساب‌ها؛ تطبیق بانکی خودکار هنوز متصل نیست."},
        {"id": "documents", "label": "سررسید اسناد و چک‌ها", "available": bool(documents), "detail": "فقط اسناد ثبت‌شده در خزانه؛ کامل‌بودن با دفتر هلو باید تطبیق داده شود."},
        {"id": "pnl", "label": "سود و زیان تأییدشده", "available": bool(approved), "detail": "گزارش ماهانهٔ دستی با منبع و تأیید مدیر؛ اتصال خودکار بهای کالا و هزینه‌ها هنوز انجام نشده است."},
        {"id": "baseline", "label": "مبنای هدف رشد", "available": targets["status"] == "ready", "detail": "هدف ۲۰ درصد به سود مثبت و ماه مبنای مشخص نیاز دارد."},
    ]
    warnings = []
    if collections["duplicate_references"]:
        warnings.append("شمارهٔ مرجع تکراری در اسناد باز دیده شد؛ قبل از تصمیم مالی تطبیق دهید. هیچ سندی خودکار حذف نشده است.")
    stale = sum(1 for row in accounts if row.get("updated_at") is None or (today - row["updated_at"].date()).days > 1)
    if stale:
        warnings.append(f"موجودی {stale} حساب بیش از یک روز قبل ثبت شده یا زمان ثبت مشخص نیست؛ مانده را با بانک تطبیق دهید.")
    if expenses:
        warnings.append("هزینهٔ ثابت بدون سند مرتبط به پیش‌بینی اضافه می‌شود؛ برای جلوگیری از دوباره‌شماری، سند پرداختنی را به هزینهٔ ثابت مرتبط کنید.")
    if any(doc["due_date"] < today and doc["status"] in {"open", "overdue"} for doc in documents):
        warnings.append("در پیش‌بینی، اسناد سررسیدگذشته در روز جاری قرار گرفته‌اند؛ این زمان‌بندی فرضی است و باید با وعدهٔ وصول تطبیق یابد.")
    return {"as_of": today, "current_month": month_of(today), "currency": "IRR", "settings": settings,
            "holoo_snapshot": holoo_snapshot,
            "operating_plan": operating_plan, "operating_plan_revision": operating_row["revision"] if operating_row else 0,
            "operating_projection": operating_projection, "purchase_estimate": purchase_estimate,
            "excel_estimate": excel_estimate,
            "holoo_refresh": financial_refresh_status(),
            "accounts": [{"id": row["id"], "name": row.get("name", "حساب"), "current_balance": money(row["current_balance"]), "updated_at": row.get("updated_at")} for row in accounts],
            "settings_revision": settings_row["revision"] if settings_row else 0,
            "reports": reports, "approved_actuals": list(approved.values()), "growth": targets,
            "projection": projection, "collections": collections, "coverage": coverage, "warnings": warnings,
            "snapshot": dict(snapshot) if snapshot else None, "history": [dict(row) for row in history],
            "actions": action_list(projection, collections, reports, approved, targets),
            "definitions": {
                "net_profit": "فروش ناخالص منهای برگشت و تخفیف و بهای کالا و هزینه‌های متغیر، ثابت، مالی و مالیات، به‌علاوهٔ سایر درآمدها.",
                "break_even": "هزینهٔ ثابت تقسیم بر حاشیهٔ مشارکت؛ هزینهٔ مالی و مالیات در نقطهٔ سربه‌سر عملیاتی منظور نشده‌اند.",
                "cash_cycle": "روزهای وصول مطالبات + روزهای نگهداری موجودی − روزهای پرداخت به تأمین‌کننده؛ از ماندهٔ متوسط همان ماه محاسبه می‌شود.",
                "forecast": "برآورد ۹۱ روز شامل امروز؛ دریافتنی‌ها با احتمال وصول، چک برگشتی دریافتنی با وصول صفر و پرداختنی‌ها با مبلغ کامل منظور می‌شوند. سناریوی بدون وصول هیچ دریافت جدیدی ندارد.",
                "growth": "سود مثبت ماه مبنا × (۱ + نرخ رشد ماهانه) به توان فاصلهٔ ماه‌ها؛ عقب‌ماندن از هدف، هدف ماه بعد را کاهش نمی‌دهد.",
            }, "method_sources": [
                {"title": "راهنمای بهبود جریان نقد", "url": "https://business.gov.au/finance/cash-flow/improve-your-cash-flow"},
                {"title": "تعریف نسبت‌های مالی", "url": "https://www.business.qld.gov.au/running-business/finance/improve-performance/ratios"},
                {"title": "مبنای بهای موجودی و شناسایی هزینهٔ فروش", "url": "https://www.ifrs.org/issued-standards/list-of-standards/ias-2-inventories/"},
            ]}


@router.post("/operating-plan")
def save_operating_plan(data: OperatingPlan, user: dict = Depends(require_treasury_access)):
    if user["role"] != "ceo":
        raise HTTPException(403, "تغییر بودجه و تأیید به‌روزبودن منابع فقط با مدیرعامل است.")
    payload = data.model_dump(mode="json", exclude={"expected_revision"})
    payload["checks_registry_complete"] = False
    payload["attested_at"] = iran_today().isoformat()
    with engine.begin() as conn:
        from treasury_excel import excel_balance_summary
        source = excel_balance_summary(conn) if data.balance_source == "excel" else latest_financial_snapshot(conn)
        if data.bank_balances_current and (not source or source["to_date"] != iran_today().isoformat() or not source["currency_verified"]
            or not all(any(s["kind"] == kind and s["ok"] and s["complete"] and s["total_irr"] is not None for s in source["sources"]) for kind in ("banks", "cash"))):
            raise HTTPException(422, "ابتدا ماندهٔ بانک و صندوق اصلاح‌شده را امروز از هلو دریافت کنید، سپس به‌روزبودن را تأیید کنید.")
        payload["source_snapshot_id"] = source["id"] if source else None
        return _save(conn, "operating-plan", data.expected_revision, payload, user, True)


@router.get("/holoo-refresh")
def get_financial_refresh(_: dict = Depends(require_treasury_access)):
    return financial_refresh_status()


@router.post("/holoo-refresh", status_code=202)
def request_financial_refresh(_: dict = Depends(require_treasury_access)):
    return start_financial_refresh()


@router.post("/settings")
def save_strategy_settings(data: StrategySettings, user: dict = Depends(require_treasury_access)):
    if user["role"] != "ceo":
        raise HTTPException(403, "تغییر هدف رشد فقط با مدیرعامل است.")
    payload = data.model_dump(mode="json", exclude={"expected_revision"})
    if data.baseline_month and month_index(data.baseline_month) >= month_index(month_of(iran_today())):
        raise HTTPException(422, "برای مبنای واقعی، یک ماه کامل‌شده انتخاب کنید.")
    with engine.begin() as conn:
        if data.baseline_month and data.baseline_profit is None:
            row = conn.execute(text("""SELECT * FROM treasury_strategy_revisions WHERE scope=:scope AND approved_by IS NOT NULL
                ORDER BY revision DESC LIMIT 1"""), {"scope": f"actual:{data.baseline_month}"}).mappings().first()
            if not row:
                raise HTTPException(422, "سود مبنا را وارد کنید یا ابتدا گزارش واقعی آن ماه را تأیید کنید.")
            payload["baseline_profit"] = profit_statement(row["payload"], data.baseline_month)["net_profit"]
            payload["baseline_report_revision"] = row["revision"]
        return _save(conn, "settings", data.expected_revision, payload, user, True)


@router.post("/monthly")
def save_monthly_finance(data: MonthlyFinance, user: dict = Depends(require_treasury_access)):
    if data.approve and user["role"] != "ceo":
        raise HTTPException(403, "تأیید نهایی گزارش فقط با مدیرعامل است.")
    if data.approve and (not data.coverage_confirmed or data.kind != "actual"):
        raise HTTPException(422, "تأیید واقعی فقط پس از اعلام کامل‌بودن منابع ممکن است.")
    if data.approve and month_index(data.month) >= month_index(month_of(iran_today())):
        raise HTTPException(422, "ماه جاری یا آینده هنوز برای تأیید نهایی کامل نشده است.")
    payload = data.model_dump(mode="json", exclude={"expected_revision", "approve"})
    with engine.begin() as conn:
        return _save(conn, f"{data.kind}:{data.month}", data.expected_revision, payload, user, data.approve)


@router.post("/cash-scenario")
def cash_scenario(data: CashScenario, _: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        accounts, documents, expenses = _load_sources(conn)
    return {"preview_only": True, "saved": False, "projection": liquidity_projection(accounts, documents, expenses, iran_today(), data.model_dump())}


@router.post("/profit-scenario")
def profit_scenario(data: ProfitScenario, _: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        report = conn.execute(text("""SELECT * FROM treasury_strategy_revisions WHERE scope=:scope AND approved_by IS NOT NULL
            ORDER BY revision DESC LIMIT 1"""), {"scope": f"actual:{data.month}"}).mappings().first()
        settings_row = _latest(conn, "settings")
    if not report:
        raise HTTPException(422, "سناریوی سود به گزارش واقعی و تأییدشدهٔ ماه مبنا نیاز دارد.")
    settings = settings_row["payload"] if settings_row else default_settings(iran_today())
    targets = growth_targets(settings.get("baseline_month"), settings.get("baseline_profit"), settings["monthly_growth_percent"], settings["end_month"], {})
    target = next((row["target"] for row in targets["rows"] if month_index(row["month"]) == month_index(data.month) + 1), None)
    return {"preview_only": True, "saved": False, "source_revision": report["revision"],
            "result": growth_scenario(report["payload"], data.model_dump(), target)}


@router.post("/reconciliation-preview")
def reconciliation_preview(data: ReconciliationPreview, _: dict = Depends(require_treasury_access)):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, current_balance, updated_at FROM cash_accounts WHERE id=:id AND is_active=1"), {"id": data.account_id}).mappings().first()
    if not row:
        raise HTTPException(404, "حساب فعال پیدا نشد.")
    return {"preview_only": True, "saved": False, "account_id": row["id"],
            "recorded_balance": money(row["current_balance"]), "statement_balance": money(data.statement_balance),
            "difference": money(data.statement_balance - dec(row["current_balance"])),
            "recorded_at": row["updated_at"], "matched": data.statement_balance == dec(row["current_balance"])}
