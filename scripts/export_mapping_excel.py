"""Export Digikala variants to Excel for the owner's manual mapping, with
auto-suggested candidates. On return, scripts/apply_mapping_excel.py applies it."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db import DATABASE_URL
from sqlalchemy import create_engine, text  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import importlib  # noqa: E402
amv = importlib.import_module("auto_map_variants2")

DB_URL = DATABASE_URL
OUT = Path.home() / "Downloads" / "نگاشت_دیجی_کالا_20261107.xlsx"


def main() -> int:
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        variants = conn.execute(text("""
            SELECT dkp_id, title, raw->>'main_category_title' AS cat,
                   price_selling, stock, holoo_code
            FROM digikala_variants WHERE status='active' ORDER BY (holoo_code IS NULL) DESC, dkp_id
        """)).mappings().all()
        products = conn.execute(text("SELECT code, name, price, stock FROM products WHERE is_active=1")).mappings().all()

    prod_index = [{"code": p["code"], "name": p["name"], "brand": amv.find_brand(p["name"]),
                   "type": amv.find_type(p["name"]), "vol": amv.vol(p["name"])} for p in products]
    existing_codes = {p["code"] for p in products}

    wb = Workbook()
    ws = wb.active
    ws.title = "نگاشت"
    header = ["dkp_id", "عنوان دیجی‌کالا", "دسته", "قیمت (ریال)", "موجودی دیجی‌کالا",
              "کد هلو فعلی", "پیشنهاد خودکار — کد", "پیشنهاد خودکار — نام", "امتیاز",
              "✍ کد هلو نهایی (این ستون را پر کن)"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="5B3FD6")

    for v in variants:
        vtitle = v["title"] or ""
        vbrand = amv.find_brand(vtitle) or amv.find_brand(v["cat"] or "")
        vtype = amv.find_type(vtitle)
        vvol = amv.vol(vtitle)
        best_code, best_name, best_score = "", "", 0.0
        if vbrand:
            cands = [p for p in prod_index if p["brand"] == vbrand]
            exact = [p for p in cands if vtype and p["type"] == vtype]
            pool = exact or cands
            if vvol:
                same_vol = [p for p in pool if p["vol"] == vvol]
                if same_vol:
                    pool = same_vol
            if pool:
                best = pool[0]
                best_code, best_name = best["code"], best["name"]
                best_score = 0.9 if (exact and vvol and same_vol) else (0.7 if exact else 0.5)
        ws.append([v["dkp_id"], vtitle, v["cat"], v["price_selling"], v["stock"],
                   v["holoo_code"] or "", best_code, best_name, best_score,
                   v["holoo_code"] or ""])

    widths = [10, 55, 16, 14, 10, 12, 12, 40, 8, 22]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{ws.max_row}"

    # sheet 2: holoo products reference
    ws2 = wb.create_sheet("کالاهای هلو")
    ws2.append(["کد", "نام", "قیمت (ریال)", "موجودی"])
    for cell in ws2[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F6F5B")
    for p in products:
        ws2.append([p["code"], p["name"], p["price"], p["stock"]])
    for i, w in enumerate([12, 55, 14, 10], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    wb.save(OUT)
    print(f"saved: {OUT}")
    print(f"rows: {len(variants)} variants, {len(products)} holoo products")
    return 0


if __name__ == "__main__":
    sys.exit(main())
