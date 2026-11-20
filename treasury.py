from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from io import BytesIO
import posixpath
import re
from typing import Optional
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from iran_time import iran_today
from operations import current_user, role_has_module_permission
from treasury_finance import OPEN_STATUSES, PAYABLE_TYPES, RECEIVABLE_TYPES, month_of, recurring_dates


router = APIRouter(prefix="/treasury", tags=["treasury"])
TREASURY_ROLES = {"ceo", "finance"}
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def require_treasury_access(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in TREASURY_ROLES:
        raise HTTPException(status_code=403, detail="Treasury access required")
    return user


def require_debtors_access(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in TREASURY_ROLES and not role_has_module_permission(user["role"], "debtors", "can_read"):
        raise HTTPException(status_code=403, detail="Debtor report access required")
    return user


def require_ceo_approval(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "ceo":
        raise HTTPException(status_code=403, detail="CEO approval required")
    return user


class TreasuryInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class CashAccountCreate(TreasuryInput):
    name: str = Field(min_length=2, max_length=150)
    account_type: str
    current_balance: float = 0
    minimum_reserve: float = Field(default=0, ge=0)


class FinancialDocumentCreate(TreasuryInput):
    document_type: str
    counterparty: str = Field(min_length=2, max_length=200)
    amount: float = Field(gt=0)
    due_date: date
    collection_probability: float = Field(default=1, ge=0, le=1)
    reference_number: Optional[str] = None
    customer_id: Optional[int] = None
    notes: Optional[str] = None
    fixed_expense_id: Optional[int] = Field(default=None, gt=0)


class FixedExpenseCreate(TreasuryInput):
    title: str = Field(min_length=2, max_length=200)
    amount: float = Field(gt=0)
    due_day: int = Field(ge=1, le=31)
    notes: Optional[str] = None


class DocumentStatusUpdate(BaseModel):
    status: str


class AccountBalanceUpdate(TreasuryInput):
    current_balance: float
    minimum_reserve: Optional[float] = Field(default=None, ge=0)


class FixedExpenseUpdate(TreasuryInput):
    amount: Optional[float] = Field(default=None, gt=0)
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    is_active: Optional[bool] = None


class LiquidityActionExecute(TreasuryInput):
    action_type: str
    title: str = Field(min_length=3, max_length=200)
    target_amount: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)
    customer_id: Optional[int] = None


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("ي", "ی").replace("ك", "ک")).strip()


def parse_jalali_date(value: str) -> tuple[Optional[str], Optional[date]]:
    normalized = normalize_text(value).translate(PERSIAN_DIGITS)
    match = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", normalized)
    if not match:
        return None, None
    text_value = "/".join(match.groups())
    try:
        jy, jm, jd = map(int, match.groups())
        import jdatetime
        jdatetime.date(jy, jm, jd)
        jy += 1595
        days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
        days += (jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186
        gy = 400 * (days // 146097)
        days %= 146097
        if days > 36524:
            days -= 1
            gy += 100 * (days // 36524)
            days %= 36524
            if days >= 365:
                days += 1
        gy += 4 * (days // 1461)
        days %= 1461
        if days > 365:
            gy += (days - 1) // 365
            days = (days - 1) % 365
        gd = days + 1
        leap = gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)
        month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        gm = 1
        while gm <= 12 and gd > month_days[gm]:
            gd -= month_days[gm]
            gm += 1
        return text_value, date(gy, gm, gd)
    except (ValueError, IndexError):
        return text_value, None


def xlsx_column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        return 0
    result = 0
    for letter in letters.group(0):
        result = result * 26 + ord(letter) - 64
    return result


def read_xlsx_cells(contents: bytes, sheet_name: str | None = None):
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    try:
        with ZipFile(BytesIO(contents)) as archive:
            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            relation_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relations = {
                item.attrib["Id"]: item.attrib["Target"]
                for item in relation_root.findall(f"{{{package_rel_ns}}}Relationship")
            }
            sheet_nodes = workbook_root.findall(f"{{{main_ns}}}sheets/{{{main_ns}}}sheet")
            first_sheet = next((node for node in sheet_nodes if node.attrib.get("name") == sheet_name), None) if sheet_name else next(iter(sheet_nodes), None)
            if first_sheet is None:
                raise ValueError("فایل هیچ شیتی ندارد.")
            relation_id = first_sheet.attrib.get(f"{{{rel_ns}}}id")
            target = relations.get(relation_id or "")
            if not target:
                raise ValueError("مسیر شیت اصلی پیدا نشد.")
            sheet_path = target.lstrip("/") if target.startswith("/xl/") else posixpath.normpath(posixpath.join("xl", target))

            shared_strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in shared_root.findall(f"{{{main_ns}}}si"):
                    shared_strings.append("".join(node.text or "" for node in item.iter(f"{{{main_ns}}}t")))

            sheet_root = ET.fromstring(archive.read(sheet_path))
            rows = {}
            max_column = 0
            for row_node in sheet_root.findall(f".//{{{main_ns}}}sheetData/{{{main_ns}}}row"):
                row_number = int(row_node.attrib.get("r", "0") or 0)
                values = {}
                for cell in row_node.findall(f"{{{main_ns}}}c"):
                    reference = cell.attrib.get("r", "")
                    column = xlsx_column_number(reference)
                    if not column:
                        continue
                    max_column = max(max_column, column)
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find(f"{{{main_ns}}}v")
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(f"{{{main_ns}}}t"))
                    elif value_node is None or value_node.text is None:
                        value = None
                    elif cell_type == "s":
                        index = int(value_node.text)
                        value = shared_strings[index] if 0 <= index < len(shared_strings) else ""
                    elif cell_type in {"str", "e"}:
                        value = value_node.text
                    elif cell_type == "b":
                        value = value_node.text == "1"
                    else:
                        numeric = Decimal(value_node.text)
                        if not numeric.is_finite():
                            raise ValueError("عدد نامحدود در فایل پذیرفته نیست.")
                        value = int(numeric) if numeric == numeric.to_integral_value() else numeric
                    values[column] = value
                rows[row_number] = values
    except (BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"ساختار فایل Excel معتبر نیست: {exc}")
    return rows, max(rows, default=0), max_column


def parse_debtors_workbook(contents: bytes):
    rows_by_number, max_row, max_column = read_xlsx_cells(contents)
    get_value = lambda row, column: rows_by_number.get(row, {}).get(column)
    header_row = None
    name_column = None
    balance_column = None
    share_column = None
    for row_number in range(1, min(max_row, 40) + 1):
        headings = {normalize_text(get_value(row_number, column)): column for column in range(1, min(max_column, 30) + 1)}
        if "سرفصل" in headings and "مانده" in headings:
            header_row = row_number
            name_column = headings["سرفصل"]
            balance_column = headings["مانده"]
            share_column = headings.get("درصد از کل")
            break
    if not header_row or not name_column or not balance_column:
        raise HTTPException(status_code=422, detail="ستون‌های «سرفصل» و «مانده» در فایل پیدا نشد.")

    period_dates = []
    for row_number in range(1, header_row):
        for column in range(1, max_column + 1):
            raw = normalize_text(get_value(row_number, column)).translate(PERSIAN_DIGITS)
            period_dates.extend(re.findall(r"\d{4}/\d{1,2}/\d{1,2}", raw))
    report_from_text = period_dates[0] if period_dates else None
    report_to_text = period_dates[1] if len(period_dates) > 1 else report_from_text
    _, snapshot_date = parse_jalali_date(report_to_text or "")

    rows = []
    warnings = []
    seen = {}
    for row_number in range(header_row + 1, max_row + 1):
        counterparty = normalize_text(get_value(row_number, name_column))
        if not counterparty:
            continue
        if counterparty in {"جمع", "مجموع"}:
            break
        normalized_counterparty = normalize_text(counterparty)
        raw_balance = get_value(row_number, balance_column)
        try:
            balance = float(str(raw_balance).replace(",", "").translate(PERSIAN_DIGITS))
        except (TypeError, ValueError):
            warnings.append(f"ردیف {row_number}: مانده معتبر نیست.")
            continue
        if balance <= 0:
            warnings.append(f"ردیف {row_number}: مانده صفر یا منفی نادیده گرفته شد.")
            continue
        raw_share = get_value(row_number, share_column) if share_column else None
        try:
            share = float(str(raw_share).replace("%", "").replace(",", ".").translate(PERSIAN_DIGITS)) if raw_share not in (None, "") else None
        except (TypeError, ValueError):
            share = None
            warnings.append(f"ردیف {row_number}: درصد نامعتبر بود و خالی ثبت شد.")
        if normalized_counterparty in seen:
            existing = rows[seen[normalized_counterparty]]
            existing["balance"] += balance
            existing["share_percent"] = (
                (existing["share_percent"] or 0) + (share or 0)
                if existing["share_percent"] is not None or share is not None else None
            )
            warnings.append(f"ردیف {row_number}: مانده نام تکراری «{counterparty}» تجمیع شد.")
            continue
        rows.append({
            "counterparty": counterparty,
            "normalized_counterparty": normalized_counterparty,
            "balance": balance,
            "share_percent": share,
        })
        seen[normalized_counterparty] = len(rows) - 1
    if not rows:
        raise HTTPException(status_code=422, detail="هیچ ردیف بدهکاری معتبر در فایل پیدا نشد.")
    return {
        "rows": rows,
        "report_from_text": report_from_text,
        "report_to_text": report_to_text,
        "snapshot_date": snapshot_date or iran_today(),
        "warnings": warnings,
    }


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_cash_account(data: CashAccountCreate, _: dict = Depends(require_treasury_access)):
    if data.account_type not in {"bank", "cash", "other"}:
        raise HTTPException(status_code=422, detail="Invalid account type")
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO cash_accounts
                    (name, account_type, current_balance, minimum_reserve, is_active, updated_at)
                VALUES (:name, :account_type, :current_balance, :minimum_reserve, 1, NOW())
                RETURNING *
            """),
            data.model_dump(),
        ).mappings().first()
    return dict(row)


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def create_financial_document(
    data: FinancialDocumentCreate, _: dict = Depends(require_treasury_access)
):
    if data.document_type not in {"receivable", "payable"}:
        raise HTTPException(status_code=422, detail="Invalid document type")
    values = data.model_dump()
    with engine.begin() as conn:
        if data.fixed_expense_id is not None:
            if data.document_type != "payable" or not conn.execute(text("SELECT id FROM fixed_expenses WHERE id=:id AND is_active=1"), {"id": data.fixed_expense_id}).first():
                raise HTTPException(status_code=422, detail="هزینهٔ مرتبط باید فعال و سند از نوع پرداختنی باشد.")
        row = conn.execute(
            text("""
                INSERT INTO financial_documents
                    (document_type, counterparty, amount, due_date, status,
                     collection_probability, reference_number, customer_id, notes, fixed_expense_id, created_at)
                VALUES
                    (:document_type, :counterparty, :amount, :due_date, 'open',
                     :collection_probability, :reference_number, :customer_id, :notes, :fixed_expense_id, NOW())
                RETURNING *
            """),
            values,
        ).mappings().first()
    return dict(row)


@router.post("/fixed-expenses", status_code=status.HTTP_201_CREATED)
def create_fixed_expense(data: FixedExpenseCreate, _: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO fixed_expenses (title, amount, due_day, is_active, notes, created_at)
                VALUES (:title, :amount, :due_day, 1, :notes, NOW())
                RETURNING *
            """),
            data.model_dump(),
        ).mappings().first()
    return dict(row)


@router.post("/import/debtors", status_code=status.HTTP_201_CREATED)
async def import_debtors_excel(
    request: Request,
    x_file_name: Optional[str] = Header(default=None, alias="X-File-Name"),
    user: dict = Depends(require_treasury_access),
):
    filename = unquote(x_file_name or "debtors.xlsx")
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="فقط فایل xlsx پذیرفته می‌شود.")
    contents = await request.body()
    if not contents:
        raise HTTPException(status_code=422, detail="فایل خالی است.")
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="حجم فایل نباید بیشتر از ۱۰ مگابایت باشد.")
    file_hash = hashlib.sha256(contents).hexdigest()
    parsed = parse_debtors_workbook(contents)
    with engine.begin() as conn:
        duplicate = conn.execute(
            text("SELECT id FROM receivable_snapshots WHERE import_hash=:hash"),
            {"hash": file_hash},
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="این فایل قبلاً وارد شده است.")
        customer_rows = conn.execute(text("SELECT id, name FROM customers")).mappings().all()
        customer_map = {normalize_text(row["name"]): row["id"] for row in customer_rows}
        total_amount = sum(row["balance"] for row in parsed["rows"])
        snapshot = conn.execute(text("""
            INSERT INTO receivable_snapshots
                (source_file, import_hash, report_from_text, report_to_text,
                 snapshot_date, total_amount, row_count, imported_by, created_at)
            VALUES
                (:source_file, :import_hash, :report_from_text, :report_to_text,
                 :snapshot_date, :total_amount, :row_count, :imported_by, NOW())
            RETURNING id
        """), {
            "source_file": filename,
            "import_hash": file_hash,
            "report_from_text": parsed["report_from_text"],
            "report_to_text": parsed["report_to_text"],
            "snapshot_date": parsed["snapshot_date"],
            "total_amount": total_amount,
            "row_count": len(parsed["rows"]),
            "imported_by": user["id"],
        }).mappings().first()
        matched_count = 0
        for row in parsed["rows"]:
            customer_id = customer_map.get(row["normalized_counterparty"])
            matched_count += int(customer_id is not None)
            conn.execute(text("""
                INSERT INTO receivable_balances
                    (snapshot_id, counterparty, normalized_counterparty, balance,
                     share_percent, customer_id, created_at)
                VALUES
                    (:snapshot_id, :counterparty, :normalized_counterparty, :balance,
                     :share_percent, :customer_id, NOW())
            """), {"snapshot_id": snapshot["id"], "customer_id": customer_id, **row})
    return {
        "snapshot_id": snapshot["id"],
        "source_file": filename,
        "row_count": len(parsed["rows"]),
        "total_amount": total_amount,
        "matched_customers": matched_count,
        "unmatched_customers": len(parsed["rows"]) - matched_count,
        "report_from": parsed["report_from_text"],
        "report_to": parsed["report_to_text"],
        "warnings": parsed["warnings"],
    }


@router.get("/overview")
def treasury_overview(_: dict = Depends(require_treasury_access)):
    with engine.connect() as conn:
        accounts = conn.execute(text("""
            SELECT * FROM cash_accounts WHERE is_active=1 ORDER BY id
        """)).mappings().all()
        documents = conn.execute(text("""
            SELECT fd.*, c.name AS customer_name
            FROM financial_documents fd
            LEFT JOIN customers c ON c.id=fd.customer_id
            ORDER BY (fd.status='open') DESC, fd.due_date, fd.id DESC
        """)).mappings().all()
        expenses = conn.execute(text("""
            SELECT * FROM fixed_expenses WHERE is_active=1 ORDER BY due_day, id
        """)).mappings().all()
        latest_snapshot = conn.execute(text("""
            SELECT * FROM receivable_snapshots
            ORDER BY snapshot_date DESC, id DESC LIMIT 1
        """)).mappings().first()
        debtor_rows = []
        if latest_snapshot:
            debtor_rows = conn.execute(text("""
                SELECT id, counterparty, balance, share_percent, customer_id
                FROM receivable_balances
                WHERE snapshot_id=:snapshot_id
                ORDER BY balance DESC, id LIMIT 20
            """), {"snapshot_id": latest_snapshot["id"]}).mappings().all()
    open_receivables = sum(float(x["amount"] or 0) for x in documents if x["document_type"] in RECEIVABLE_TYPES and x["status"] in OPEN_STATUSES)
    open_payables = sum(float(x["amount"] or 0) for x in documents if x["document_type"] in PAYABLE_TYPES and x["status"] in OPEN_STATUSES)
    return {
        "summary": {
            "cash_balance": sum(float(x["current_balance"] or 0) for x in accounts),
            "minimum_reserve": sum(float(x["minimum_reserve"] or 0) for x in accounts),
            "open_receivables": open_receivables,
            "open_payables": open_payables,
        },
        "accounts": [dict(x) for x in accounts],
        "documents": [dict(x) for x in documents],
        "fixed_expenses": [dict(x) for x in expenses],
        "debtor_snapshot": ({
            **dict(latest_snapshot),
            "top_debtors": [dict(x) for x in debtor_rows],
        } if latest_snapshot else None),
    }


@router.get("/debtors")
def debtors_report(_: dict = Depends(require_debtors_access)):
    """Read-only debtor report, separated from cash, payable and expense data."""
    with engine.connect() as conn:
        snapshot = conn.execute(text("""
            SELECT id, report_from_text, report_to_text, snapshot_date,
                   total_amount, row_count, created_at
            FROM receivable_snapshots
            ORDER BY snapshot_date DESC, id DESC LIMIT 1
        """)).mappings().first()
        if not snapshot:
            return {"snapshot": None, "debtors": []}
        rows = conn.execute(text("""
            SELECT counterparty, balance, share_percent, customer_id
            FROM receivable_balances
            WHERE snapshot_id=:snapshot_id
            ORDER BY balance DESC, id LIMIT 100
        """), {"snapshot_id": snapshot["id"]}).mappings().all()
    return {"snapshot": dict(snapshot), "debtors": [dict(row) for row in rows]}


@router.delete("/import/debtors/{snapshot_id}")
def delete_debtors_snapshot(snapshot_id: int, _: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT id FROM receivable_snapshots WHERE id=:id"), {"id": snapshot_id}
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="گزارش بدهکاران پیدا نشد.")
        conn.execute(text("DELETE FROM receivable_balances WHERE snapshot_id=:id"), {"id": snapshot_id})
        conn.execute(text("DELETE FROM receivable_snapshots WHERE id=:id"), {"id": snapshot_id})
    return {"status": "deleted", "snapshot_id": snapshot_id}


@router.patch("/documents/{document_id}/status")
def update_document_status(
    document_id: int,
    data: DocumentStatusUpdate,
    _: dict = Depends(require_treasury_access),
):
    if data.status not in {"open", "settled", "cancelled", "overdue"}:
        raise HTTPException(status_code=422, detail="Invalid document status")
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE financial_documents SET status=:status
            WHERE id=:id RETURNING *
        """), {"id": document_id, "status": data.status}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)


@router.patch("/accounts/{account_id}")
def update_account_balance(
    account_id: int,
    data: AccountBalanceUpdate,
    _: dict = Depends(require_treasury_access),
):
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE cash_accounts
            SET current_balance=:current_balance,
                minimum_reserve=COALESCE(:minimum_reserve, minimum_reserve),
                updated_at=NOW()
            WHERE id=:id AND is_active=1 RETURNING *
        """), {"id": account_id, **data.model_dump()}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return dict(row)


@router.delete("/accounts/{account_id}")
def deactivate_cash_account(
    account_id: int,
    _: dict = Depends(require_treasury_access),
):
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE cash_accounts SET is_active=0, updated_at=NOW()
            WHERE id=:id AND is_active=1 RETURNING id
        """), {"id": account_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "deactivated", "account_id": account_id}


@router.patch("/fixed-expenses/{expense_id}")
def update_fixed_expense(
    expense_id: int,
    data: FixedExpenseUpdate,
    _: dict = Depends(require_treasury_access),
):
    values = data.model_dump()
    values["is_active"] = int(values["is_active"]) if values["is_active"] is not None else None
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE fixed_expenses
            SET amount=COALESCE(:amount, amount),
                due_day=COALESCE(:due_day, due_day),
                is_active=COALESCE(:is_active, is_active)
            WHERE id=:id RETURNING *
        """), {"id": expense_id, **values}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Fixed expense not found")
    return dict(row)


@router.delete("/fixed-expenses/{expense_id}")
def deactivate_fixed_expense(
    expense_id: int,
    _: dict = Depends(require_treasury_access),
):
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE fixed_expenses SET is_active=0
            WHERE id=:id AND is_active=1 RETURNING id
        """), {"id": expense_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Fixed expense not found")
    return {"status": "deactivated", "expense_id": expense_id}


@router.post("/actions/execute", status_code=status.HTTP_201_CREATED)
def execute_liquidity_action(
    data: LiquidityActionExecute,
    user: dict = Depends(require_ceo_approval),
):
    if data.action_type not in {"collection", "cash_sale", "reschedule"}:
        raise HTTPException(status_code=422, detail="Unsupported liquidity action")
    with engine.begin() as conn:
        existing = conn.execute(text("""
            SELECT id, assigned_to
            FROM tasks
            WHERE title=:title AND status <> 'completed'
            ORDER BY id DESC LIMIT 1
        """), {"title": data.title}).mappings().first()
        if existing:
            return {
                "status": "already_exists",
                "task_id": existing["id"],
                "assigned_to": existing["assigned_to"],
                "message": "این پیشنهاد قبلاً به تسک عملیاتی تبدیل شده است.",
            }
        assignees = conn.execute(text("""
            SELECT u.id
            FROM users u
            JOIN sales s ON s.salesperson_id=u.salesperson_id AND s.customer_id=:customer_id
            WHERE u.is_active=1 AND u.role='salesperson'
            GROUP BY u.id
            ORDER BY u.id LIMIT 2
        """), {"customer_id": data.customer_id}).mappings().all() if data.customer_id else []
        assigned_to = assignees[0]["id"] if len(assignees) == 1 else user["id"]
        task = conn.execute(text("""
            INSERT INTO tasks
                (title, description, priority, status, progress, assigned_to,
                 created_by, customer_id, due_date, created_at, updated_at)
            VALUES
                (:title, :description, 'high', 'new', 0, :assigned_to,
                 :created_by, :customer_id, :due_date, NOW(), NOW())
            RETURNING id, assigned_to
        """), {
            "title": data.title,
            "description": f"هدف مالی: {data.target_amount:,.0f} ریال\n{data.reason}",
            "assigned_to": assigned_to,
            "created_by": user["id"],
            "customer_id": data.customer_id,
            "due_date": iran_today() + timedelta(days=3),
        }).mappings().first()
    return {
        "status": "task_created",
        "task_id": task["id"],
        "assigned_to": task["assigned_to"],
        "message": "اقدام تأیید شد و به‌صورت تسک عملیاتی ثبت شد.",
    }


def expense_dates(start: date, end: date, due_day: int):
    yield from recurring_dates(start, end, due_day)


@router.get("/forecast")
def cashflow_forecast(
    days: int = Query(default=30, ge=1, le=365),
    _: dict = Depends(require_treasury_access),
):
    start = iran_today()
    end = start + timedelta(days=days)
    with engine.connect() as conn:
        accounts = conn.execute(text("""
            SELECT * FROM cash_accounts WHERE is_active=1 ORDER BY id
        """)).mappings().all()
        documents = conn.execute(
            text("""
                SELECT * FROM financial_documents
                WHERE due_date <= :end
                ORDER BY due_date, id
            """),
            {"end": end},
        ).mappings().all()
        expenses = conn.execute(text("""
            SELECT * FROM fixed_expenses WHERE is_active=1 ORDER BY due_day, id
        """)).mappings().all()
        latest_snapshot = conn.execute(text("""
            SELECT id FROM receivable_snapshots
            ORDER BY snapshot_date DESC, id DESC LIMIT 1
        """)).mappings().first()
        debtor_rows = []
        if latest_snapshot:
            debtor_rows = conn.execute(text("""
                SELECT counterparty, balance, customer_id
                FROM receivable_balances
                WHERE snapshot_id=:snapshot_id
                ORDER BY balance DESC, id LIMIT 30
            """), {"snapshot_id": latest_snapshot["id"]}).mappings().all()
        active_tasks = conn.execute(text("""
            SELECT id, title FROM tasks
            WHERE status <> 'completed'
            ORDER BY id DESC
        """)).mappings().all()
        task_by_title = {}
        for task in active_tasks:
            task_by_title.setdefault(task["title"], task["id"])

    opening_balance = sum(float(row["current_balance"] or 0) for row in accounts)
    reserve = sum(float(row["minimum_reserve"] or 0) for row in accounts)
    events = {}

    def add_event(event_date, event_type, title, amount, probability=1.0, original_due_date=None, reference_number=None):
        events.setdefault(event_date, []).append({
            "type": event_type,
            "title": title,
            "amount": float(amount),
            "probability": float(probability),
            "original_due_date": original_due_date or event_date,
            "reference_number": reference_number,
            "is_overdue": bool(original_due_date and original_due_date < start),
        })

    covered_expenses = {}
    for doc in documents:
        if doc.get("fixed_expense_id") and doc["document_type"] in PAYABLE_TYPES and doc["status"] != "cancelled":
            key = (doc["fixed_expense_id"], month_of(doc["due_date"]))
            covered_expenses[key] = covered_expenses.get(key, 0) + float(doc["amount"])
        if doc["status"] not in OPEN_STATUSES:
            continue
        if doc["document_type"] not in RECEIVABLE_TYPES | PAYABLE_TYPES:
            continue
        sign = 1 if doc["document_type"] in RECEIVABLE_TYPES else -1
        probability = float(doc["collection_probability"] if sign > 0 else 1)
        if sign > 0 and doc["status"] == "bounced":
            probability = 0
        effective_date = max(doc["due_date"], start)
        add_event(
            effective_date, "receivable" if sign > 0 else "payable", doc["counterparty"],
            sign * float(doc["amount"]), probability,
            doc["due_date"], doc["reference_number"],
        )
    for expense in expenses:
        for due_date in expense_dates(start, end, int(expense["due_day"])):
            remaining = max(0, float(expense["amount"]) - covered_expenses.get((expense["id"], month_of(due_date)), 0))
            if remaining:
                add_event(due_date, "fixed_expense", expense["title"], -remaining)

    expected_balance = opening_balance
    conservative_balance = opening_balance
    timeline = []
    shortage_days = []
    total_expected_inflow = 0.0
    total_outflow = 0.0
    for offset in range(days + 1):
        current_date = start + timedelta(days=offset)
        day_events = events.get(current_date, [])
        for event in day_events:
            expected_balance += event["amount"] * event["probability"]
            if event["amount"] < 0:
                conservative_balance += event["amount"]
                total_outflow += abs(event["amount"])
            else:
                total_expected_inflow += event["amount"] * event["probability"]
        available = expected_balance - reserve
        if available < 0:
            shortage_days.append({
                "date": current_date,
                "shortage": abs(available),
                "message": f"کسری نقدینگی پیش‌بینی‌شده در {current_date.isoformat()}",
            })
        timeline.append({
            "date": current_date,
            "expected_balance": round(expected_balance, 2),
            "conservative_balance": round(conservative_balance, 2),
            "available_after_reserve": round(available, 2),
            "events": day_events,
        })

    warnings = []
    for item in shortage_days:
        if not warnings or item["date"] != warnings[-1]["end_date"] + timedelta(days=1):
            warnings.append({**item, "start_date": item["date"], "end_date": item["date"], "max_shortage": item["shortage"]})
        else:
            warnings[-1]["end_date"] = item["date"]
            warnings[-1]["max_shortage"] = max(warnings[-1]["max_shortage"], item["shortage"])

    peak_shortage = max((item["shortage"] for item in shortage_days), default=0.0)
    recommendations = []
    remaining_shortage = peak_shortage
    if remaining_shortage > 0:
        for debtor in debtor_rows:
            if remaining_shortage <= 0:
                break
            target_amount = min(float(debtor["balance"] or 0), remaining_shortage)
            if target_amount <= 0:
                continue
            recommendations.append({
                "type": "collection",
                "priority": "high",
                "title": f"پیگیری وصول از {debtor['counterparty']}",
                "target_amount": round(target_amount, 2),
                "available_balance": float(debtor["balance"] or 0),
                "customer_id": debtor["customer_id"],
                "reason": "تأمین کسری پیش‌بینی‌شده از بزرگ‌ترین مانده‌های بدهکاران",
            })
            remaining_shortage -= target_amount
        if remaining_shortage > 0:
            recommendations.append({
                "type": "cash_sale",
                "priority": "high",
                "title": "برنامه فروش نقدی کوتاه‌مدت",
                "target_amount": round(remaining_shortage, 2),
                "reason": "بخش باقی‌مانده کسری با وصول پیشنهادی پوشش داده نمی‌شود",
            })
        payable_candidates = sorted(
            (doc for doc in documents if doc["document_type"] in PAYABLE_TYPES and doc["status"] in OPEN_STATUSES),
            key=lambda doc: float(doc["amount"] or 0), reverse=True,
        )
        if payable_candidates:
            candidate = payable_candidates[0]
            recommendations.append({
                "type": "reschedule",
                "priority": "medium",
                "title": f"بررسی جابه‌جایی سررسید {candidate['counterparty']}",
                "target_amount": float(candidate["amount"] or 0),
                "reason": "سناریوی جایگزین در صورت محقق‌نشدن وصول یا فروش نقدی",
            })

    for recommendation in recommendations:
        recommendation["executed_task_id"] = task_by_title.get(recommendation["title"])

    def due_total(document_type: str, horizon: int):
        horizon_end = start + timedelta(days=horizon)
        return sum(
            float(doc["amount"] or 0)
            for doc in documents
            if doc["status"] in OPEN_STATUSES and doc["document_type"] in (RECEIVABLE_TYPES if document_type == "receivable" else PAYABLE_TYPES) and doc["due_date"] <= horizon_end
        )

    return {
        "period": {"start": start, "end": end, "days": days},
        "opening_balance": opening_balance,
        "minimum_reserve": reserve,
        "summary": {
            "receivables_7_days": due_total("receivable", 7),
            "payables_7_days": due_total("payable", 7),
            "receivables_30_days": due_total("receivable", 30),
            "payables_30_days": due_total("payable", 30),
            "expected_inflow": round(total_expected_inflow, 2),
            "planned_outflow": round(total_outflow, 2),
            "closing_expected_balance": round(expected_balance, 2),
            "peak_shortage": round(peak_shortage, 2),
        },
        "timeline": timeline,
        "warnings": warnings,
        "recommendations": recommendations,
    }



# === KIARAD BI CHECKS & BALANCE SHEET EXTENSION ===
from fastapi import UploadFile, File

class ManualCheckCreate(TreasuryInput):
    check_type: str = Field(..., description="'receivable' (دریافتنی) یا 'payable' (پرداختنی)")
    counterparty: str = Field(..., description="نام طرف حساب / داروخانه / شرکت")
    amount: float = Field(..., gt=0, description="مبلغ چک")
    due_date: str = Field(..., description="تاریخ سررسید (مثلاً 1405/07/20 یا 2026-10-12)")
    reference_number: Optional[str] = Field(None, description="شماره چک یا شناسه صیادی")
    bank_name: Optional[str] = Field(None, description="نام بانک و شعبه")
    status: str = Field("open", description="'open', 'cleared', 'bounced'")
    notes: Optional[str] = Field(None, description="توضیحات تکمیلی")

class CheckStatusUpdate(BaseModel):
    status: str = Field(..., description="'open', 'cleared', 'bounced', 'cancelled'")


@router.post("/checks/manual", status_code=status.HTTP_201_CREATED)
def create_manual_check(data: ManualCheckCreate, _: dict = Depends(require_treasury_access)):
    if data.check_type not in {"receivable", "payable", "receivable_check", "payable_check", "دریافتنی", "پرداختنی"}:
        raise HTTPException(status_code=422, detail="نوع چک دریافتنی یا پرداختنی مشخص شود.")
    if data.status not in {"open", "cleared", "bounced", "cancelled"}:
        raise HTTPException(status_code=422, detail="وضعیت چک معتبر نیست.")
    clean_date_str, parsed_date = parse_jalali_date(data.due_date)
    if not parsed_date:
        try:
            parsed_date = date.fromisoformat(data.due_date.strip())
        except Exception:
            raise HTTPException(status_code=400, detail="فرمت تاریخ نامعتبر است. لطفاً به صورت شمسی (1405/07/20) یا میلادی وارد کنید.")
    
    doc_type = "receivable_check" if ("rec" in data.check_type.lower() or "دریافت" in data.check_type) else "payable_check"
    bank_desc = f"بانک: {data.bank_name}" if data.bank_name else ""
    full_notes = f"{bank_desc} | {data.notes or ''}".strip(" |")
    
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO financial_documents (
                    document_type, counterparty, amount, due_date, status, 
                    reference_number, notes, collection_probability, created_at
                ) VALUES (
                    :doc_type, :counterparty, :amount, :due_date, :status,
                    :ref_num, :notes, 1.0, NOW()
                ) RETURNING id
            """),
            {
                "doc_type": doc_type,
                "counterparty": data.counterparty.strip(),
                "amount": float(data.amount),
                "due_date": parsed_date,
                "status": data.status.strip().lower(),
                "ref_num": data.reference_number.strip() if data.reference_number else None,
                "notes": full_notes
            }
        )
        new_id = result.scalar()
        
    return {
        "success": True,
        "message": "چک با موفقیت ثبت گردید",
        "check_id": new_id,
        "document_type": doc_type,
        "amount": data.amount,
        "due_date": str(parsed_date)
    }


@router.patch("/checks/{check_id}/status")
def update_check_status(check_id: int, data: CheckStatusUpdate, _: dict = Depends(require_treasury_access)):
    valid_statuses = {"open", "cleared", "bounced", "cancelled"}
    new_status = data.status.strip().lower()
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"وضعیت نامعتبر است. وضعیت‌های مجاز: {valid_statuses}")
    
    with engine.begin() as conn:
        res = conn.execute(
            text("UPDATE financial_documents SET status = :status WHERE id = :id RETURNING id"),
            {"status": new_status, "id": check_id}
        )
        if not res.fetchone():
            raise HTTPException(status_code=404, detail="چک مورد نظر یافت نشد")
            
    return {"success": True, "check_id": check_id, "new_status": new_status}


@router.get("/checks/balance-sheet")
def get_checks_balance_sheet(_: dict = Depends(require_treasury_access)):
    today = iran_today()
    d7 = today + timedelta(days=7)
    d30 = today + timedelta(days=30)
    d60 = today + timedelta(days=60)
    
    with engine.connect() as conn:
        cash_res = conn.execute(text("SELECT COALESCE(SUM(current_balance), 0) FROM cash_accounts WHERE is_active = 1")).scalar() or 0.0
        rows = conn.execute(text("""
            SELECT id, document_type, counterparty, amount, due_date, status, reference_number, notes
            FROM financial_documents
            ORDER BY due_date ASC
        """)).mappings().all()
        
    rec_open = 0.0
    rec_open_count = 0
    rec_cleared = 0.0
    rec_bounced = 0.0
    rec_bounced_count = 0
    
    pay_open = 0.0
    pay_open_count = 0
    pay_cleared = 0.0
    pay_bounced = 0.0
    pay_bounced_count = 0
    
    aging_buckets = {
        "overdue": {"receivable": 0.0, "payable": 0.0, "count": 0},
        "next_7_days": {"receivable": 0.0, "payable": 0.0, "count": 0},
        "days_8_to_30": {"receivable": 0.0, "payable": 0.0, "count": 0},
        "days_31_to_60": {"receivable": 0.0, "payable": 0.0, "count": 0},
        "over_60_days": {"receivable": 0.0, "payable": 0.0, "count": 0}
    }
    
    high_risk_checks = []
    
    for r in rows:
        dtype = r["document_type"] or ""
        amt = float(r["amount"] or 0)
        st = (r["status"] or "open").lower()
        due = r["due_date"]
        
        is_rec = dtype in RECEIVABLE_TYPES
        is_pay = dtype in PAYABLE_TYPES
        
        if is_rec:
            if st in ("open", "overdue", "in_progress", "pending"):
                rec_open += amt
                rec_open_count += 1
                if due < today:
                    aging_buckets["overdue"]["receivable"] += amt
                    aging_buckets["overdue"]["count"] += 1
                    high_risk_checks.append({**dict(r), "risk_reason": "سررسید گذشته و وصول نشده"})
                elif due <= d7:
                    aging_buckets["next_7_days"]["receivable"] += amt
                    aging_buckets["next_7_days"]["count"] += 1
                elif due <= d30:
                    aging_buckets["days_8_to_30"]["receivable"] += amt
                    aging_buckets["days_8_to_30"]["count"] += 1
                elif due <= d60:
                    aging_buckets["days_31_to_60"]["receivable"] += amt
                    aging_buckets["days_31_to_60"]["count"] += 1
                else:
                    aging_buckets["over_60_days"]["receivable"] += amt
                    aging_buckets["over_60_days"]["count"] += 1
            elif st in ("cleared", "settled", "collected", "paid", "وصول"):
                rec_cleared += amt
            elif st in ("bounced", "dishonored", "برگشت"):
                rec_bounced += amt
                rec_bounced_count += 1
                high_risk_checks.append({**dict(r), "risk_reason": "چک برگشتی"})
                
        elif is_pay:
            if st in ("open", "overdue", "bounced", "dishonored", "برگشت", "in_progress", "pending"):
                pay_open += amt
                pay_open_count += 1
                if st in ("bounced", "dishonored", "برگشت"):
                    pay_bounced += amt
                    pay_bounced_count += 1
                    high_risk_checks.append({**dict(r), "risk_reason": "چک پرداختنی برگشتی؛ تعهد پرداخت همچنان باز است"})
                if due < today:
                    aging_buckets["overdue"]["payable"] += amt
                    aging_buckets["overdue"]["count"] += 1
                elif due <= d7:
                    aging_buckets["next_7_days"]["payable"] += amt
                    aging_buckets["next_7_days"]["count"] += 1
                elif due <= d30:
                    aging_buckets["days_8_to_30"]["payable"] += amt
                    aging_buckets["days_8_to_30"]["count"] += 1
                elif due <= d60:
                    aging_buckets["days_31_to_60"]["payable"] += amt
                    aging_buckets["days_31_to_60"]["count"] += 1
                else:
                    aging_buckets["over_60_days"]["payable"] += amt
                    aging_buckets["over_60_days"]["count"] += 1
            elif st in ("cleared", "settled", "paid", "پاس"):
                pay_cleared += amt
            elif st in ("bounced", "dishonored", "برگشت"):
                pay_bounced += amt
                pay_bounced_count += 1

    net_position = (cash_res + rec_open) - pay_open
    status_label = "ماندهٔ اسمی مثبت" if net_position >= 0 else "ماندهٔ اسمی منفی"
    
    return {
        "summary": {
            "cash_balance": cash_res,
            "receivable_open_total": rec_open,
            "receivable_open_count": rec_open_count,
            "receivable_cleared_total": rec_cleared,
            "receivable_bounced_total": rec_bounced,
            "receivable_bounced_count": rec_bounced_count,
            "payable_open_total": pay_open,
            "payable_open_count": pay_open_count,
            "payable_cleared_total": pay_cleared,
            "payable_bounced_total": pay_bounced,
            "payable_bounced_count": pay_bounced_count,
            "net_position": net_position,
            "status": status_label,
            "is_deficit": net_position < 0,
            "deficit_amount": abs(net_position) if net_position < 0 else 0.0
        },
        "method_note": "ماندهٔ اسمی حساب و اسناد، بدون زمان‌بندی و احتمال وصول است و تأیید کفایت نقدینگی نیست. دریافتنی برگشتی در وصول منظور نشده؛ پرداختنی برگشتی همچنان تعهد باز است. مبالغ برگشتی زیرمجموعهٔ وضعیت مربوط‌اند و نباید دوباره جمع شوند.",
        "aging_buckets": aging_buckets,
        "high_risk_checks": high_risk_checks[:50]
    }


def parse_checks_workbook(content: bytes):
    """Explicit columns only; validate every row before opening a transaction."""
    rows, _, _ = read_xlsx_cells(content)
    nonempty = [(n, row) for n, row in sorted(rows.items()) if any(v not in (None, "") for v in row.values())]
    if not nonempty:
        raise HTTPException(422, "فایل چک خالی است.")
    aliases = {
        "طرف حساب": "counterparty", "نام طرف حساب": "counterparty",
        "نوع چک": "direction", "نوع": "direction", "جهت": "direction",
        "مبلغ ریال": "amount_rial", "مبلغ (ریال)": "amount_rial", "مبلغ به ریال": "amount_rial",
        "مبلغ تومان": "amount_toman", "مبلغ (تومان)": "amount_toman", "مبلغ به تومان": "amount_toman",
        "سررسید": "due", "تاریخ سررسید": "due",
        "شماره چک": "reference", "شناسه صیادی": "reference", "شماره مرجع": "reference",
    }
    columns = {}
    for column, value in nonempty[0][1].items():
        key = aliases.get(normalize_text(value).replace("\u200c", " "))
        if key:
            if key in columns:
                raise HTTPException(422, "سرستون تکراری در فایل چک وجود دارد.")
            columns[key] = column
    amounts = [key for key in ("amount_rial", "amount_toman") if key in columns]
    if not all(key in columns for key in ("counterparty", "direction", "due", "reference")) or len(amounts) != 1:
        raise HTTPException(422, "سطر نخست باید سرستون‌های طرف حساب، نوع چک، تاریخ سررسید، شماره چک یا شناسه صیادی، و دقیقاً یکی از مبلغ ریال یا مبلغ تومان را داشته باشد.")
    result, references = [], set()
    directions = {"دریافتنی": "receivable_check", "دریافتی": "receivable_check", "دریافت": "receivable_check", "receivable": "receivable_check", "receivable_check": "receivable_check", "پرداختنی": "payable_check", "پرداختی": "payable_check", "پرداخت": "payable_check", "payable": "payable_check", "payable_check": "payable_check"}
    for number, row in nonempty[1:]:
        def cell(key):
            return normalize_text(row.get(columns[key])).translate(PERSIAN_DIGITS)
        error = f"سطر {number}: "
        counterparty, direction, reference = cell("counterparty"), directions.get(cell("direction").lower()), cell("reference")
        if not 2 <= len(counterparty) <= 200 or not direction or not 1 <= len(reference) <= 100:
            raise HTTPException(422, error + "طرف حساب، جهت دریافتنی یا پرداختنی، و شناسهٔ یکتای چک باید صریح و معتبر باشند.")
        if reference in references:
            raise HTTPException(422, error + "شناسهٔ چک در همین فایل تکرار شده است؛ هیچ ردیفی ثبت نشد.")
        references.add(reference)
        amount_text = cell(amounts[0]).replace(",", "").replace("٬", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", amount_text):
            raise HTTPException(422, error + "مبلغ باید عدد مثبت با واحد صریح سرستون باشد.")
        try:
            amount = Decimal(amount_text) * (10 if amounts[0] == "amount_toman" else 1)
        except InvalidOperation:
            raise HTTPException(422, error + "مبلغ معتبر نیست.")
        if not amount.is_finite() or amount <= 0 or amount > 10**15 or amount != amount.to_integral_value():
            raise HTTPException(422, error + "مبلغ باید تعداد صحیح ریال، مثبت و حداکثر یک میلیون میلیارد ریال باشد.")
        due_text = cell("due").replace("-", "/")
        if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", due_text):
            raise HTTPException(422, error + "تاریخ باید صریح مانند ۱۴۰۵/۰۷/۲۷ یا ۲۰۲۶/۱۰/۱۹ باشد؛ تاریخ حدس زده نمی‌شود.")
        year, month, day = map(int, due_text.split("/"))
        try:
            if 1200 <= year <= 1600:
                import jdatetime
                due = jdatetime.date(year, month, day).togregorian()
            elif 1900 <= year <= 2200:
                due = date(year, month, day)
            else:
                raise ValueError("year")
        except ValueError:
            raise HTTPException(422, error + "تاریخ سررسید معتبر نیست؛ هیچ ردیفی ثبت نشد.")
        result.append({"doc_type": direction, "counterparty": counterparty, "amount": int(amount), "due_date": due, "ref_num": reference})
    if not result:
        raise HTTPException(422, "فایل فقط سرستون دارد و چکی برای ورود ندارد.")
    if len(result) > 10000:
        raise HTTPException(422, "حداکثر ده هزار چک در هر فایل پذیرفته می‌شود.")
    return result


@router.post("/checks/import-excel", status_code=status.HTTP_201_CREATED)
async def import_checks_excel(file: UploadFile = File(...), _: dict = Depends(require_treasury_access)):
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(422, "حجم فایل باید حداکثر پنج مگابایت باشد.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                raise HTTPException(422, "حجم بازشدهٔ فایل بیش از حد مجاز است.")
    except BadZipFile:
        raise HTTPException(422, "فقط فایل اکسل با ساختار معتبر پذیرفته می‌شود.")
    values = parse_checks_workbook(content)
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('treasury-check-import', 0))"))
        existing = conn.execute(text("SELECT reference_number FROM financial_documents WHERE reference_number IS NOT NULL")).scalars().all()
        known = {normalize_text(value).translate(PERSIAN_DIGITS) for value in existing}
        if any(row["ref_num"] in known for row in values):
            raise HTTPException(422, "شناسهٔ یک یا چند چک قبلاً در خزانه ثبت شده است؛ هیچ ردیفی وارد نشد.")
        for value in values:
            conn.execute(text("""INSERT INTO financial_documents
                (document_type, counterparty, amount, due_date, status, reference_number, notes, collection_probability, created_at)
                VALUES (:doc_type, :counterparty, :amount, :due_date, 'open', :ref_num, 'ورود اعتبارسنجی‌شده از اکسل؛ وضعیت باز', 1, NOW())"""), value)
    return {"success": True, "inserted_count": len(values), "message": f"{len(values)} چک با سررسید و جهت صریح ثبت شد؛ ماندهٔ بانک تغییر نکرد."}


@router.post("/checks/sync-holoo")
def sync_checks_from_holoo(_: dict = Depends(require_treasury_access)):
    return {
        "success": False, "status": "unsupported", "supported": False,
        "connected": None, "inserted_count": 0,
        "message": "مسیر مستند دریافت چک‌ها در قرارداد فعلی وب‌سرویس هلو وجود ندارد. هیچ درخواست، ثبت یا تغییر مالی انجام نشد؛ فایل اکسل با سرستون‌های صریح یا مستند مسیر چک لازم است."
    }
