"""Preview-first treasury spreadsheets. Files are data, never instructions/code."""
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import csv
import json
from pathlib import Path
import re
from typing import Literal
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from db import engine
from treasury import read_xlsx_cells, require_treasury_access, parse_jalali_date
from treasury_finance import MONEY_FIELDS, month_key
from iran_time import iran_today

router = APIRouter(prefix="/treasury/excel", tags=["treasury"])
KINDS = {"balances": "حساب و موجودی", "checks": "چک‌ها", "purchases": "خرید", "sales": "فروش", "purchase_returns": "برگشت خرید", "sales_returns": "برگشت فروش", "monthly": "گزارش ماهانه", "inventory": "موجودی کالا", "general": "گزارش عمومی"}
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MAX_FILE = 5 * 1024 * 1024
AMOUNTS = {"فروش ناخالص": "revenue", "برگشت فروش": "returns", "تخفیف فروش": "discounts", "بهای کالای فروش رفته": "cogs", "هزینه متغیر": "variable_costs", "هزینه ثابت": "fixed_costs", "هزینه مالی": "finance_costs", "مالیات": "taxes", "سایر درآمد": "other_income"}


def norm(value):
    return re.sub(r"\s+", " ", str(value if value is not None else "").replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").translate(DIGITS)).strip()


def fail(message):
    raise HTTPException(422, message)


def number(value, *, factor=1, negative=False):
    if value is None or isinstance(value, bool) or norm(value) == "":
        fail("مبلغ یا تعداد لازم خالی است؛ مقدار نامعلوم صفر نمی‌شود.")
    try:
        result = Decimal(norm(value).replace(",", "").replace("٬", "")) * factor
    except InvalidOperation:
        fail("مبلغ یا تعداد معتبر نیست.")
    if not result.is_finite() or abs(result) > 10**16 or (result < 0 and not negative):
        fail("مبلغ یا تعداد خارج از محدوده است.")
    return result


def amount(value, factor, negative=False):
    result = number(value, factor=factor, negative=negative)
    if result != result.to_integral_value():
        fail("مبلغ باید پس از تبدیل، تعداد صحیح ریال باشد.")
    return int(result)


def day(value):
    raw = norm(value).replace("-", "/")
    if not re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", raw):
        fail("تاریخ را صریح مانند ۱۴۰۵/۰۷/۲۷ وارد کنید؛ شمارهٔ سریال تاریخ اکسل پذیرفته نیست.")
    y, m, d = map(int, raw.split("/"))
    try:
        if 1200 <= y <= 1600:
            import jdatetime
            parsed = jdatetime.date(y,m,d).togregorian()
        elif 1900 <= y <= 2200:
            parsed = date(y,m,d)
        else:
            raise ValueError()
        return parsed.isoformat()
    except ValueError:
        fail("تاریخ معتبر نیست.")


def inspect_file(content):
    if len(content) > MAX_FILE:
        fail("حداکثر حجم فایل پنج مگابایت است.")
    try:
        with ZipFile(BytesIO(content)) as z:
            if len(z.infolist()) > 3000 or sum(i.file_size for i in z.infolist()) > 50*1024*1024:
                fail("حجم بازشدهٔ فایل بیش از حد مجاز است.")
            if any("vbaproject" in i.filename.lower() or "externallinks/" in i.filename.lower() for i in z.infolist()):
                fail("فایل دارای ماکرو یا پیوند خارجی پذیرفته نیست؛ خروجی مقادیر ساده بگیرید.")
            root = ET.fromstring(z.read("xl/workbook.xml"))
            sheets = [i.attrib["name"] for i in root.findall(f"{{{NS}}}sheets/{{{NS}}}sheet")]
            if not sheets or len(sheets) > 40:
                fail("تعداد شیت‌های فایل معتبر نیست.")
            return sheets
    except (BadZipFile, KeyError, ET.ParseError, ValueError):
        fail("فقط فایل اکسل معتبر با پسوند ایکس‌ال‌اس‌ایکس پذیرفته می‌شود.")


def table(content, sheet_name="", allow_empty=False):
    sheets = inspect_file(content)
    if sheet_name and sheet_name not in sheets:
        fail("شیت انتخاب‌شده در فایل وجود ندارد.")
    # Cached formula results can be stale and must not become financial inputs.
    with ZipFile(BytesIO(content)) as z:
        for entry in z.infolist():
            if entry.filename.startswith("xl/worksheets/") and entry.filename.endswith(".xml"):
                root = ET.fromstring(z.read(entry))
                if root.find(f".//{{{NS}}}f") is not None:
                    fail("فایل فرمول دارد؛ یک نسخه با مقادیر محاسبه‌شده و بدون فرمول ذخیره و بارگذاری کنید.")
    rows, max_row, max_col = read_xlsx_cells(content, sheet_name or sheets[0])
    if max_row > 10001 or max_col > 60:
        fail("حداکثر ده هزار ردیف و شصت ستون در هر شیت پذیرفته می‌شود.")
    nonempty = [(n, r) for n, r in sorted(rows.items()) if any(v not in (None, "") for v in r.values())]
    if not nonempty or (len(nonempty) < 2 and not allow_empty):
        fail("فایل باید سرستون و حداقل یک ردیف دیتا داشته باشد.")
    headers = [norm(nonempty[0][1].get(i)) for i in range(1, max_col+1)]
    while headers and not headers[-1]:
        headers.pop()
    if not all(headers) or len(set(headers)) != len(headers):
        fail("سرستون خالی یا تکراری پذیرفته نیست.")
    values = [[str(r.get(i)) if isinstance(r.get(i), Decimal) else r.get(i) for i in range(1, len(headers)+1)] for _, r in nonempty[1:]]
    if any(len(str(v or "")) > 2000 for r in values for v in r):
        fail("متن بعضی سلول‌ها بیش از حد مجاز است.")
    return headers, values, sheet_name or sheets[0]


def parse_report(content, kind, unit, sheet_name="", from_date="", to_date=""):
    if kind not in KINDS or unit not in {"IRR", "TOMAN"}:
        fail("نوع گزارش و واحد مبلغ را مشخص کنید.")
    headers,values,sheet=table(content,sheet_name,allow_empty=kind in {"purchases","sales","purchase_returns","sales_returns"})
    return parse_report_rows(headers,values,kind,unit,sheet,from_date,to_date)


def parse_report_rows(headers,values,kind,unit,sheet="دستی",from_date="",to_date=""):
    if kind not in KINDS or unit not in {"IRR", "TOMAN"}:
        fail("نوع گزارش و واحد مبلغ را مشخص کنید.")
    is_invoice=kind in {"purchases","sales","purchase_returns","sales_returns"}
    if not headers or len(headers)>60 or len(set(headers))!=len(headers) or not all(isinstance(h,str) and h.strip() for h in headers):
        fail("سرستون‌ها باید مشخص، غیرتکراری و حداکثر شصت ستون باشند.")
    if not values and not is_invoice:fail("حداقل یک ردیف گزارش لازم است.")
    if len(values)>10000 or any(len(row)!=len(headers) for row in values):fail("تعداد ردیف یا ستون معتبر نیست.")
    rows = [dict(zip(headers, r)) for r in values]
    factor = 1 if unit == "IRR" else 10
    required = {
        "balances": ["کد حساب", "نام حساب", "نوع حساب", "مانده", "تاریخ"],
        "checks": ["شماره مرجع", "طرف حساب", "نوع چک", "مبلغ", "سررسید", "وضعیت", "احتمال وصول"],
        "monthly": ["ماه", "نوع گزارش", *AMOUNTS],
        "inventory": ["شناسه کالا", "تعداد", "ارزش موجودی", "تاریخ"],
    }.get(kind, ["شماره فاکتور", "تاریخ", "شناسه کالا", "تعداد", "قیمت واحد", "تخفیف ردیف", "درصد تخفیف ردیف", "تخفیف کل فاکتور", "مالیات و عوارض فاکتور"] if kind != "general" else [])
    if any(column not in headers for column in required):
        fail("سرستون‌های لازم: " + "، ".join(required))
    normalized, seen = [], set()
    invoices = {}
    for index, row in enumerate(rows, 2):
        try:
            if kind == "balances":
                key, name = norm(row["کد حساب"]), norm(row["نام حساب"])
                account_type = {"بانک": "banks", "صندوق": "cash"}.get(norm(row["نوع حساب"]))
                if not key or not name or not account_type or key in seen:
                    fail("کد یکتا، نام و نوع بانک یا صندوق لازم است.")
                seen.add(key)
                normalized.append({"source": account_type, "code": key, "name": name, "balance": amount(row["مانده"], factor, True), "as_of": day(row["تاریخ"])})
            elif kind == "checks":
                reference, party = norm(row["شماره مرجع"]), norm(row["طرف حساب"])
                direction = {"دریافتنی": "receivable_check", "پرداختنی": "payable_check"}.get(norm(row["نوع چک"]))
                status = {"باز": "open", "سررسید گذشته": "overdue", "برگشتی": "bounced", "تسویه": "settled", "وصول": "cleared", "لغو": "cancelled"}.get(norm(row["وضعیت"]))
                if not reference or len(reference)>100 or not 2<=len(party)<=200 or not direction or not status or reference in seen:
                    fail("شناسهٔ یکتا، طرف حساب، جهت و وضعیت معتبر لازم است؛ چک خرج‌شده را به‌عنوان چک باز وارد نکنید.")
                seen.add(reference)
                value, probability = amount(row["مبلغ"], factor), number(row["احتمال وصول"])
                if value <= 0 or probability > 100:
                    fail("مبلغ چک باید مثبت و احتمال بین صفر تا صد باشد.")
                normalized.append({"reference": reference, "counterparty": party, "document_type": direction, "status": status, "amount": value, "due_date": day(row["سررسید"]), "collection_probability": str(probability/100)})
            elif kind == "monthly":
                month = month_key(norm(row["ماه"]).replace("/", "-"))
                report_kind = {"عملکرد": "actual", "بودجه": "budget"}.get(norm(row["نوع گزارش"]))
                key = (month, report_kind)
                if not report_kind or key in seen:
                    fail("ماه و نوع عملکرد یا بودجه باید یکتا باشند.")
                seen.add(key)
                normalized.append({"month": month, "kind": report_kind, **{field: amount(row[label], factor) for label, field in AMOUNTS.items()}})
            elif kind == "inventory":
                key = norm(row["شناسه کالا"])
                if not key or key in seen:
                    fail("شناسهٔ کالا باید یکتا باشد.")
                seen.add(key)
                normalized.append({"product_code": key, "quantity": str(number(row["تعداد"])), "value_irr": amount(row["ارزش موجودی"], factor), "as_of": day(row["تاریخ"])})
            elif kind != "general":
                key, product = norm(row["شماره فاکتور"]), norm(row["شناسه کالا"])
                if not key or not product:
                    fail("شمارهٔ فاکتور و شناسهٔ کالا لازم است.")
                when, hd, tax = day(row["تاریخ"]), amount(row["تخفیف کل فاکتور"], factor), amount(row["مالیات و عوارض فاکتور"], factor)
                inv = invoices.setdefault(key, {"ErpCode": key, "Date": when, "SumPrice": "0", "SumDiscount": hd, "SumLevy": tax, "SumScot": 0, "Detail": []})
                if (inv["Date"], inv["SumDiscount"], inv["SumLevy"]) != (when, hd, tax):
                    fail("تاریخ و تخفیف کل و مالیات در همهٔ ردیف‌های یک فاکتور باید یکسان باشند.")
                qty, price = number(row["تعداد"]), number(row["قیمت واحد"], factor=factor)
                discount, percent = number(row["تخفیف ردیف"], factor=factor), number(row["درصد تخفیف ردیف"])
                if qty <= 0 or percent > 100:
                    fail("تعداد مثبت و درصد تخفیف حداکثر صد لازم است.")
                inv["Detail"].append({"ProductErpCode": product, "Few": str(qty), "Price": str(price), "SumPrice": str(qty*price), "Discount": str(discount), "PersentDiscount": str(percent), "Levy": 0, "Scot": 0})
                inv["SumPrice"] = str(Decimal(inv["SumPrice"]) + qty*price)
        except HTTPException as exc:
            fail(f"سطر {index}: {exc.detail}")
        except (ValueError, InvalidOperation):
            fail(f"سطر {index}: مقدار یا ماه معتبر نیست.")
    result = {"headers": headers, "rows": values, "sheet": sheet, "normalized": normalized, "kind": kind, "unit": "IRR", "input_unit": unit, "row_count": len(values)}
    if is_invoice:
        start, end = day(from_date), day(to_date)
        if start > end or (date.fromisoformat(end)-date.fromisoformat(start)).days > 1100:
            fail("بازهٔ گزارش فاکتور معتبر نیست.")
        from purchase_profit import _normalize_invoice, EvidenceError
        for invoice in invoices.values():
            if not start <= invoice["Date"] <= end:
                fail("فاکتور خارج از بازهٔ اعلام‌شده وجود دارد.")
            try:
                _normalize_invoice(invoice, Decimal(1), {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"})
            except EvidenceError:
                fail("تعداد، قیمت و تخفیف یکی از فاکتورها تطبیق ندارد؛ تخفیف کل باید شامل تخفیف ردیف‌ها باشد.")
        result.update(normalized=list(invoices.values()), from_date=start, to_date=end)
    if kind in {"balances", "inventory"}:
        dates = {r["as_of"] for r in normalized}
        if len(dates) != 1:
            fail("تاریخ همهٔ مانده‌ها در یک گزارش باید یکسان باشد.")
        result["as_of"] = next(iter(dates))
    return result


async def upload(file):
    return await file.read(MAX_FILE+1)


@router.post("/sheets")
async def workbook_sheets(file: UploadFile = File(...), _: dict = Depends(require_treasury_access)):
    return {"sheets": inspect_file(await upload(file))}


@router.post("/preview")
async def preview_report(file: UploadFile = File(...), kind: str = Form(...), unit: str = Form(...), title: str = Form(...), source_note: str = Form(...), sheet_name: str = Form(""), from_date: str = Form(""), to_date: str = Form(""), user: dict = Depends(require_treasury_access)):
    if not 2 <= len(title.strip()) <= 200 or not 8 <= len(source_note.strip()) <= 2000:
        fail("عنوان گزارش و توضیح منبع و دوره را کامل کنید.")
    content = await upload(file)
    payload = parse_report(content, kind, unit, sheet_name, from_date, to_date)
    digest = sha256(content + json.dumps([kind, unit, sheet_name, from_date, to_date], ensure_ascii=False).encode()).hexdigest()
    return save_report_preview(payload,digest,title,source_note,user)


def save_report_preview(payload,digest,title,source_note,user):
    kind=payload['kind']
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": "treasury-excel:"+kind})
        existing = conn.execute(text("SELECT id,status FROM treasury_excel_batches WHERE kind=:kind AND content_hash=:hash"), {"kind": kind, "hash": digest}).mappings().first()
        if existing:
            raise HTTPException(409, "این فایل و شیت قبلاً پیش‌نمایش یا ثبت شده است؛ از فهرست گزارش‌ها بازش کنید.")
        if kind == "monthly":
            from treasury_strategy import _latest

            payload["expected_revisions"] = {f"{r['kind']}:{r['month']}": (old["revision"] if (old := _latest(conn, f"{r['kind']}:{r['month']}")) else 0) for r in payload["normalized"]}
        row = conn.execute(text("""INSERT INTO treasury_excel_batches(kind,title,source_note,content_hash,payload,created_by)
            VALUES(:kind,:title,:note,:hash,CAST(:payload AS JSONB),:user) RETURNING id"""), {"kind": kind, "title": title.strip(), "note": source_note.strip(), "hash": digest, "payload": json.dumps(payload, ensure_ascii=False), "user": user["id"]}).scalar_one()
    return {"id": row, "kind": kind, "title": title, "source_note":source_note, "status": "preview", "row_count": payload["row_count"], "headers": payload["headers"], "rows": payload["rows"][:100], "preview_limit": 100, "effects": effects(kind)}


def effects(kind):
    return {"checks": "پس از تأیید، چک‌ها با وضعیت صریح به اسناد خزانه اضافه می‌شوند؛ ماندهٔ بانک عوض نمی‌شود.", "monthly": "پس از تأیید، نسخهٔ پیش‌نویس گزارش ماهانه ذخیره می‌شود؛ گزارش واقعی خودکار تأیید نمی‌شود.", "balances": "گزارش مانده مستقل نگهداری می‌شود و به‌عنوان مبنای اکسل در برنامهٔ وجه قابل انتخاب است؛ حساب هلو یا دستی عوض نمی‌شود.", "inventory": "موجودی کالا برای مشاهده و تطبیق نگهداری می‌شود؛ تا تأیید تاریخ آغاز، واحد کالا و نگاشت، بهای ابتدای دوره از آن ساخته نمی‌شود."}.get(kind, "گزارش به‌صورت مستقل نگهداری و قابل مشاهده می‌شود؛ اطلاعات هلو بازنویسی نمی‌شوند.")


INVOICE_HEADERS=['شماره فاکتور','تاریخ','شناسه کالا','تعداد','قیمت واحد','تخفیف ردیف','درصد تخفیف ردیف','تخفیف کل فاکتور','مالیات و عوارض فاکتور']
MANUAL_HEADERS={
    'balances':['کد حساب','نام حساب','نوع حساب','مانده','تاریخ'],
    'checks':['شماره مرجع','طرف حساب','نوع چک','مبلغ','سررسید','وضعیت','احتمال وصول'],
    'monthly':['ماه','نوع گزارش',*AMOUNTS],
    'inventory':['شناسه کالا','تعداد','ارزش موجودی','تاریخ'],
    'general':['عنوان','مقدار'],
    **{key:INVOICE_HEADERS for key in ('purchases','sales','purchase_returns','sales_returns')},
}


@router.get('/manual-schema')
def manual_schema(kind:str,_:dict=Depends(require_treasury_access)):
    if kind not in MANUAL_HEADERS:fail('نوع گزارش معتبر نیست.')
    return {'headers':MANUAL_HEADERS[kind],'max_rows':500,'effects':effects(kind)}


class ManualReportInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    kind:str
    unit:str
    title:str=Field(min_length=2,max_length=200)
    source_note:str=Field(min_length=8,max_length=2000)
    headers:list[str]=Field(min_length=1,max_length=60)
    rows:list[list[str|int|float|None]]=Field(max_length=500)
    from_date:str=''
    to_date:str=''


@router.post('/manual/preview')
def preview_manual_report(data:ManualReportInput,user:dict=Depends(require_treasury_access)):
    if not 2<=len(data.title.strip())<=200 or not 8<=len(data.source_note.strip())<=2000:fail('عنوان و توضیح منبع را کامل کنید.')
    if len(json.dumps(data.model_dump(),ensure_ascii=False).encode())>MAX_FILE:fail('حجم ورودی دستی بیش از حد مجاز است.')
    if any(len(str(cell or ''))>2000 or (isinstance(cell,str) and cell.lstrip().startswith('=')) for row in data.rows for cell in row):fail('متن طولانی یا فرمول در ورودی دستی مجاز نیست.')
    payload=parse_report_rows(data.headers,data.rows,data.kind,data.unit,'دستی',data.from_date,data.to_date)
    payload['input_mode']='manual'
    digest=sha256(json.dumps(data.model_dump(),ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return save_report_preview(payload,digest,data.title,'ورود دستی ـ '+data.source_note,user)


class ConfirmImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal[True]


@router.post("/{batch_id}/commit")
def commit_report(batch_id: int, data: ConfirmImport, user: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM treasury_excel_batches WHERE id=:id FOR UPDATE"), {"id": batch_id}).mappings().first()
        if not row:
            raise HTTPException(404, "گزارش پیدا نشد.")
        if row["status"] != "preview":
            raise HTTPException(409, "گزارش قبلاً ثبت شده؛ ورود دوباره انجام نشد.")
        payload = row["payload"]
        if row["kind"] == "checks":
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('treasury-check-import',0))"))
            known = {norm(r) for r in conn.execute(text("SELECT reference_number FROM financial_documents WHERE reference_number IS NOT NULL")).scalars()}
            if any(r["reference"] in known for r in payload["normalized"]):
                raise HTTPException(409, "شناسهٔ یک یا چند چک قبلاً ثبت شده؛ هیچ ردیفی وارد نشد.")
            for value in payload["normalized"]:
                conn.execute(text("""INSERT INTO financial_documents(document_type,counterparty,amount,due_date,status,reference_number,collection_probability,notes,created_at)
                    VALUES(:document_type,:counterparty,:amount,:due_date,:status,:reference,:collection_probability,:note,NOW())"""), {**value, "note": f"ورود از اکسل؛ گزارش {batch_id}؛ " + row["source_note"]})
        elif row["kind"] == "monthly":
            from treasury_strategy import _save

            for value in payload["normalized"]:
                scope = f"{value['kind']}:{value['month']}"
                _save(conn, scope, payload["expected_revisions"][scope], {**value, "source_note": f"گزارش اکسل {batch_id}؛ "+row["source_note"], "coverage_confirmed": False, "approve": False}, user)
        conn.execute(text("UPDATE treasury_excel_batches SET status='committed',committed_by=:user,committed_at=NOW() WHERE id=:id"), {"user": user["id"], "id": batch_id})
    return {"id": batch_id, "status": "committed", "row_count": payload["row_count"], "message": effects(row["kind"]), "holoo_writes": False}


@router.get("/reports")
def report_list(_: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        return [dict(r) for r in conn.execute(text("""SELECT id,kind,title,status,created_at,committed_at,payload->>'row_count' AS row_count,
            payload->>'input_unit' AS input_unit FROM treasury_excel_batches ORDER BY id DESC LIMIT 60""")).mappings()]


@router.get("/reports/{batch_id}")
def report_detail(batch_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), _: dict = Depends(require_treasury_access)):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT * FROM treasury_excel_batches WHERE id=:id"), {"id": batch_id}).mappings().first()
        if not row:
            raise HTTPException(404, "گزارش پیدا نشد.")
        payload = row["payload"]
        return {"id": row["id"], "kind": row["kind"], "title": row["title"], "status": row["status"], "source_note": row["source_note"], "headers": payload["headers"], "rows": payload["rows"][offset:offset+limit], "row_count": payload["row_count"], "offset": offset, "preview_limit": limit, "effects": effects(row["kind"])}


def csv_cell(value):
    value = str(value if value is not None else "")
    return "'"+value if re.match(r"^[\s]*[=+\-@\t\r]",value) else value


@router.get("/reports/{batch_id}/export")
def export_report(batch_id: int, _: dict = Depends(require_treasury_access)):
    from io import StringIO
    with engine.begin() as conn:
        row = conn.execute(text("SELECT payload FROM treasury_excel_batches WHERE id=:id"),{"id":batch_id}).scalar()
        if not row:
            raise HTTPException(404,"گزارش پیدا نشد.")
    out=StringIO(newline="")
    writer=csv.writer(out)
    writer.writerows([[csv_cell(v) for v in r] for r in [row["headers"],*row["rows"]]])
    return Response(content=('\ufeff'+out.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="treasury-report-{batch_id}.csv"'})


@router.get("/template")
def template(_: dict = Depends(require_treasury_access)):
    path = Path(__file__).parent/"templates"/"treasury-import.xlsx"
    if not path.exists():
        raise HTTPException(404, "فایل نمونه هنوز آماده نشده است.")
    return FileResponse(path, filename="treasury-import.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def excel_balance_summary(conn):
    row = conn.execute(text("SELECT * FROM treasury_excel_batches WHERE kind='balances' AND status='committed' ORDER BY id DESC LIMIT 1")).mappings().first()
    if not row:
        return None
    payload = row["payload"]
    balances = payload["normalized"]
    return {"id": row["id"], "source": "excel", "captured_at": payload["as_of"], "to_date": payload["as_of"], "currency_verified": True,
            "balances": balances, "sources": [{"kind": kind, "ok": True, "complete": True, "count": len(items := [b for b in balances if b["source"] == kind]), "valid_amounts": len(items), "duplicate_or_missing_keys": 0, "total_irr": sum(b["balance"] for b in items)} for kind in ("cash", "banks")]}


def excel_invoice_estimate(conn, monthly_expense_irr):
    rows = conn.execute(text("""SELECT DISTINCT ON(kind) id,kind,title,payload,committed_at FROM treasury_excel_batches
        WHERE status='committed' AND kind IN ('purchases','sales','purchase_returns','sales_returns') ORDER BY kind,id DESC""")).mappings().all()
    if not rows:
        return None
    # Never mix periods or join spreadsheet history with ERP history implicitly.
    latest = max(rows, key=lambda r: r["id"])
    start, end = latest["payload"]["from_date"], latest["payload"]["to_date"]
    sources, provenance = {}, []
    for kind in ("purchases", "sales", "purchase_returns", "sales_returns"):
        row = next((r for r in rows if r["kind"] == kind and r["payload"]["from_date"] == start and r["payload"]["to_date"] == end), None)
        sources[kind] = {"ok": bool(row), "complete": bool(row), "rows": row["payload"]["normalized"] if row else []}
        provenance.append({"kind": kind, "report_id": row["id"] if row else None, "title": row["title"] if row else "گزارش هم‌بازه موجود نیست"})
    from purchase_profit import estimate_purchase_profit
    estimate = estimate_purchase_profit({"currency_factor": 1, "from_date": start, "to_date": end, "sources": sources,
        "invoice_amount_semantics": {kind: {"header_sum_price": "gross_before_discount_tax", "header_discount_scope": "includes_line_discounts"} for kind in sources}}, monthly_expense_irr)
    return {"estimate": estimate, "provenance": provenance, "source": "excel_only"}
