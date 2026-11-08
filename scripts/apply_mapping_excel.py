"""Apply the owner-filled mapping Excel back to the DB + variant_map.csv, then
push stock/prices to connected platforms. Usage:
    python -I scripts/apply_mapping_excel.py <path-to-xlsx>
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db import DATABASE_URL
from sqlalchemy import create_engine, text  # noqa: E402
from openpyxl import load_workbook  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: apply_mapping_excel.py <xlsx>")
        return 1
    src = Path(sys.argv[1])
    wb = load_workbook(src, data_only=True)
    ws = wb["نگاشت"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    engine = create_engine(DB_URL := DATABASE_URL)
    map_path = ROOT / "scripts" / "variant_map.csv"
    applied, skipped = [], []
    with engine.begin() as conn:
        for row in rows:
            dkp_id, final_code = row[0], row[9]
            if final_code in (None, ""):
                skipped.append({"dkp": dkp_id, "reason": "خالی"})
                continue
            final_code = str(final_code).strip()
            exists = conn.execute(text("SELECT 1 FROM products WHERE code=:c"), {"c": final_code}).scalar()
            if not exists:
                skipped.append({"dkp": dkp_id, "reason": f"کد {final_code} در هلو نیست"})
                continue
            conn.execute(text("UPDATE digikala_variants SET holoo_code=:h WHERE dkp_id=:d"),
                         {"h": final_code, "d": int(dkp_id)})
            applied.append((int(dkp_id), final_code))
    with open(map_path, "a", encoding="utf-8-sig", newline="") as h:
        w = csv.writer(h)
        for pair in applied:
            w.writerow(pair)
    # push prices/stock for the newly mapped codes
    codes = [c for _, c in applied]
    from platform_sync import push_stock_many
    pushed = push_stock_many(codes) if codes else []
    print(f"applied: {len(applied)} | skipped: {len(skipped)} | pushed: {len(pushed)}")
    for r in skipped[:10]:
        print("  skip:", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
