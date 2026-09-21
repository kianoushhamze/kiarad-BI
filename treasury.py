from calendar import monthrange
from datetime import date, timedelta
import hashlib
from io import BytesIO
import posixpath
import re
from typing import Optional
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import engine
from operations import current_user


router = APIRouter(prefix="/treasury", tags=["treasury"])
TREASURY_ROLES = {"ceo", "finance"}
PERSIAN_DIGITS = str.maketrans("????????????????????", "01234567890123456789")


def require_treasury_access(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in TREASURY_ROLES:
        raise HTTPException(status_code=403, detail="Treasury access required")
    return user


def require_ceo_approval(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "ceo":
        raise HTTPException(status_code=403, detail="CEO approval required")
    return user


class CashAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    account_type: str
    current_balance: float = 0
    minimum_reserve: float = Field(default=0, ge=0)


class FinancialDocumentCreate(BaseModel):
    document_type: str
    counterparty: str = Field(min_length=2, max_length=200)
    amount: float = Field(gt=0)
    due_date: date
    collection_probability: float = Field(default=1, ge=0, le=1)
    reference_number: Optional[str] = None
    customer_id: Optional[int] = None
    notes: Optional[str] = None


class FixedExpenseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    amount: float = Field(gt=0)
    due_day: int = Field(ge=1, le=31)
    notes: Optional[str] = None


class DocumentStatusUpdate(BaseModel):
    status: str


class AccountBalanceUpdate(BaseModel):
    current_balance: float
    minimum_reserve: Optional[float] = Field(default=None, ge=0)


class FixedExpenseUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    due_day: Optional[int] = Field(default=None, ge=1, le=31)
    is_active: Optional[bool] = None


class LiquidityActionExecute(BaseModel):
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


def read_xlsx_cells(contents: bytes):
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
            first_sheet = workbook_root.find(f"{{{main_ns}}}sheets/{{{main_ns}}}sheet")
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
                        numeric = float(value_node.text)
                        value = int(numeric) if numeric.is_integer() else numeric
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
        "snapshot_date": snapshot_date or date.today(),
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
        row = conn.execute(
            text("""
                INSERT INTO financial_documents
                    (document_type, counterparty, amount, due_date, status,
                     collection_probability, reference_number, customer_id, notes, created_at)
                VALUES
                    (:document_type, :counterparty, :amount, :due_date, 'open',
                     :collection_probability, :reference_number, :customer_id, :notes, NOW())
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
    open_receivables = sum(float(x["amount"] or 0) for x in documents if x["document_type"] == "receivable" and x["status"] == "open")
    open_payables = sum(float(x["amount"] or 0) for x in documents if x["document_type"] == "payable" and x["status"] == "open")
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
        assignee = conn.execute(text("""
            SELECT u.id
            FROM users u
            LEFT JOIN sales s ON s.salesperson_id=u.salesperson_id
                AND (:customer_id IS NULL OR s.customer_id=:customer_id)
            WHERE u.is_active=1 AND u.role='salesperson'
            GROUP BY u.id
            ORDER BY COALESCE(SUM(s.total_amount), 0) DESC, u.id
            LIMIT 1
        """), {"customer_id": data.customer_id}).mappings().first()
        assigned_to = assignee["id"] if assignee else user["id"]
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
            "due_date": date.today() + timedelta(days=3),
        }).mappings().first()
    return {
        "status": "task_created",
        "task_id": task["id"],
        "assigned_to": task["assigned_to"],
        "message": "اقدام تأیید شد و به‌صورت تسک عملیاتی ثبت شد.",
    }


def expense_dates(start: date, end: date, due_day: int):
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        day = min(due_day, monthrange(cursor.year, cursor.month)[1])
        expense_date = date(cursor.year, cursor.month, day)
        if start <= expense_date <= end:
            yield expense_date
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)


@router.get("/forecast")
def cashflow_forecast(
    days: int = Query(default=30, ge=1, le=365),
    _: dict = Depends(require_treasury_access),
):
    start = date.today()
    end = start + timedelta(days=days)
    with engine.connect() as conn:
        accounts = conn.execute(text("""
            SELECT * FROM cash_accounts WHERE is_active=1 ORDER BY id
        """)).mappings().all()
        documents = conn.execute(
            text("""
                SELECT * FROM financial_documents
                WHERE status='open' AND due_date <= :end
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

    for doc in documents:
        sign = 1 if doc["document_type"] == "receivable" else -1
        probability = float(doc["collection_probability"] if sign > 0 else 1)
        effective_date = max(doc["due_date"], start)
        add_event(
            effective_date, doc["document_type"], doc["counterparty"],
            sign * float(doc["amount"]), probability,
            doc["due_date"], doc["reference_number"],
        )
    for expense in expenses:
        for due_date in expense_dates(start, end, int(expense["due_day"])):
            add_event(due_date, "fixed_expense", expense["title"], -float(expense["amount"]))

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
            (doc for doc in documents if doc["document_type"] == "payable"),
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
            if doc["document_type"] == document_type and doc["due_date"] <= horizon_end
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

class ManualCheckCreate(BaseModel):
    check_type: str = Field(..., description="'receivable' (دریافتنی) یا 'payable' (پرداختنی)")
    counterparty: str = Field(..., description="نام طرف حساب / داروخانه / شرکت")
    amount: float = Field(..., description="مبلغ چک")
    due_date: str = Field(..., description="تاریخ سررسید (مثلاً 1405/07/20 یا 2026-10-12)")
    reference_number: Optional[str] = Field(None, description="شماره چک یا شناسه صیادی")
    bank_name: Optional[str] = Field(None, description="نام بانک و شعبه")
    status: str = Field("open", description="'open', 'cleared', 'bounced'")
    notes: Optional[str] = Field(None, description="توضیحات تکمیلی")

class CheckStatusUpdate(BaseModel):
    status: str = Field(..., description="'open', 'cleared', 'bounced', 'cancelled'")


@router.post("/checks/manual", status_code=status.HTTP_201_CREATED)
def create_manual_check(data: ManualCheckCreate, _: dict = Depends(require_treasury_access)):
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
    today = date.today()
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
        
        is_rec = "rec" in dtype.lower() or "دریافت" in dtype
        is_pay = "pay" in dtype.lower() or "پرداخت" in dtype
        
        if is_rec:
            if st in ("open", "in_progress", "pending"):
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
            elif st in ("cleared", "collected", "paid", "وصول"):
                rec_cleared += amt
            elif st in ("bounced", "dishonored", "برگشت"):
                rec_bounced += amt
                rec_bounced_count += 1
                high_risk_checks.append({**dict(r), "risk_reason": "چک برگشتی"})
                
        elif is_pay:
            if st in ("open", "in_progress", "pending"):
                pay_open += amt
                pay_open_count += 1
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
            elif st in ("cleared", "paid", "پاس"):
                pay_cleared += amt
            elif st in ("bounced", "dishonored", "برگشت"):
                pay_bounced += amt
                pay_bounced_count += 1

    net_position = (cash_res + rec_open) - pay_open
    status_label = "مازاد نقدینگی" if net_position >= 0 else "کسری نقدینگی"
    
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
        "aging_buckets": aging_buckets,
        "high_risk_checks": high_risk_checks[:50]
    }


@router.post("/checks/import-excel", status_code=status.HTTP_201_CREATED)
async def import_checks_excel(file: UploadFile = File(...), _: dict = Depends(require_treasury_access)):
    content = await file.read()
    try:
        cells = read_xlsx_cells(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"خطا در خواندن فایل اکسل: {str(e)}")
        
    rows_by_idx = {}
    for cell in cells:
        rows_by_idx.setdefault(cell["row"], {})[cell["col"]] = str(cell["value"]).strip()
        
    inserted_count = 0
    with engine.begin() as conn:
        for r_idx in sorted(rows_by_idx.keys()):
            r_data = rows_by_idx[r_idx]
            vals = list(r_data.values())
            if any("مبلغ" in v or "طرف" in v or "چک" in v for v in vals):
                continue
                
            counterparty, amount, due_str, ref_num = "", 0.0, "", ""
            check_type = "receivable_check"
            
            for col_i, v in r_data.items():
                clean_v = v.translate(PERSIAN_DIGITS).replace(",", "").replace("/", "-")
                if not amount and re.match(r"^\d{4,12}$", clean_v):
                    amount = float(clean_v)
                elif not due_str and re.search(r"(13|14)\d{2}[-/]\d{1,2}[-/]\d{1,2}", v.translate(PERSIAN_DIGITS)):
                    due_str = v
                elif not counterparty and len(v) > 2 and not v.isdigit():
                    if "پرداخت" in v:
                        check_type = "payable_check"
                    elif "دریافت" in v:
                        check_type = "receivable_check"
                    else:
                        counterparty = v
                elif not ref_num and re.match(r"^\d{6,16}$", clean_v):
                    ref_num = clean_v
                    
            if counterparty and amount > 0:
                _, parsed_d = parse_jalali_date(due_str) if due_str else (None, date.today() + timedelta(days=30))
                if not parsed_d:
                    parsed_d = date.today() + timedelta(days=30)
                    
                conn.execute(
                    text("""
                        INSERT INTO financial_documents (
                            document_type, counterparty, amount, due_date, status,
                            reference_number, notes, collection_probability, created_at
                        ) VALUES (
                            :doc_type, :counterparty, :amount, :due_date, 'open',
                            :ref_num, 'ورود از اکسل', 1.0, NOW()
                        )
                    """),
                    {
                        "doc_type": check_type,
                        "counterparty": counterparty,
                        "amount": amount,
                        "due_date": parsed_d,
                        "ref_num": ref_num or None
                    }
                )
                inserted_count += 1
                
    return {
        "success": True,
        "message": f"تعداد {inserted_count} فقره چک با موفقیت از اکسل ثبت گردید",
        "inserted_count": inserted_count
    }


@router.post("/checks/sync-holoo")
def sync_checks_from_holoo(_: dict = Depends(require_treasury_access)):
    import holo_api
    import requests
    
    try:
        token = holo_api.login()
    except Exception as e:
        return {
            "success": False,
            "connected": False,
            "message": "عدم دسترسی به سرور هلو در دفتر (احتمالاً خارج از شبکه دفتر هستید یا آی‌پی هلو پاسخ نمی‌دهد).",
            "error": str(e)
        }
        
    headers = {"Authorization": token}
    holo_url = holo_api.HOLO_URL
    for endpoint in ["/Sanad/Cheque", "/Cheque", "/Sanad"]:
        try:
            resp = requests.get(f"{holo_url}{endpoint}", headers=headers, timeout=10)
            if resp.status_code == 200:
                return {
                    "success": True,
                    "connected": True,
                    "message": "اتصال به هلو با موفقیت برقرار شد.",
                    "data": resp.json()
                }
        except Exception:
            continue
            
    return {
        "success": True,
        "connected": True,
        "message": "اتصال به هلو برقرار شد اما رکورد جدیدی در اندپوینت چک‌ها یافت نشد."
    }
