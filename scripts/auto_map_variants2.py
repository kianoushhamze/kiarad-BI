"""Auto-map v2: brand transliteration + product-type matching.

DK titles use Persian brand names (لابورن) while Holoo uses Latin (LABOREN).
Require a brand match, then score by product-type words + volume."""
import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db import DATABASE_URL
from sqlalchemy import create_engine, text  # noqa: E402

DB_URL = DATABASE_URL

BRANDS = {
    "LABOREN": ["لابورن", "laboren"],
    "DERMALIST": ["درمالیست", "درمال?ست", "dermalist"],
    "ELVATAN": ["الواتان", "الوات?ن", "elvatan"],
    "CIP": ["سی آی پی", "س? آ? ??", "cip"],
    "DELANO": ["دلانو", "delano"],
    "PLEASANT": ["پلزنت", "pleasant"],
    "RICHMOND": ["ریچموند", "richmond"],
    "MILITO": [" میلیتو", "milito"],
    "V&V": ["وی اند وی", "v&v"],
    "LUCEL": ["لوسل", "lucel"],
    "OLD STOP": ["اولد استاپ", "old stop"],
    "VINUR": ["وینور", "vinur"],
    "MC HAIR": ["ام سی هیر", "mc hair"],
    "LUFENTE": ["لوفنته", "lufente"],
}
TYPES = {
    "شامپو": ["شامپو", "شام?و", "shampoo"],
    "کرم": ["کرم", "?رم", "cream"],
    "ضد آفتاب": ["ضد آفتاب", "ضدآفتاب", "ضد آفت?ب", "sun"],
    "سرم": ["سرم", "س?م"],
    "ژل": ["ژل", "?ل"],
    "لوسیون": ["لوسیون", "لو?يون"],
    "ماسک": ["ماسک", "ماس?"],
    "صابون": ["صابون"],
    "فلوئید": ["فلوئید", "فلوئ?د"],
    "تونر": ["تونر"],
}


def norm(s):
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return s.replace("ي", "ی").replace("ك", "ک")


def vol(s):
    m = re.search(r"(\d{2,4})\s*(ml|میلی|م?ل??ل?تر|گرم)", norm(s), re.I)
    return m.group(1) if m else None


def find_brand(s):
    low = norm(s)
    for latin, keys in BRANDS.items():
        for k in keys:
            if k.lower() in low:
                return latin
    for latin in BRANDS:
        if latin.lower() in low:
            return latin
    return None


def find_type(s):
    low = norm(s)
    for t, keys in TYPES.items():
        for k in keys:
            if k in low:
                return t
    return None


def main() -> int:
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        variants = conn.execute(text("""
            SELECT dkp_id, title, raw->>'main_category_title' AS category FROM digikala_variants
            WHERE holoo_code IS NULL AND status='active' ORDER BY dkp_id
        """)).mappings().all()
        products = conn.execute(text("SELECT code, name FROM products WHERE is_active=1")).mappings().all()
        existing = {r[0]: r[1] for r in conn.execute(text(
            "SELECT dkp_id, holoo_code FROM digikala_variants WHERE holoo_code IS NOT NULL")).all()}

    prod_index = []
    for p in products:
        prod_index.append({"code": p["code"], "name": p["name"],
                           "brand": find_brand(p["name"]), "type": find_type(p["name"]), "vol": vol(p["name"])})

    applied, review = [], []
    used = set()
    for v in variants:
        vbrand = find_brand(v["title"] or "") or find_brand(v["category"] or "")
        vtype = find_type(v["title"] or "")
        vvol = vol(v["title"] or "")
        if not vbrand:
            review.append({"dkp_id": v["dkp_id"], "title": (v["title"] or "")[:80], "reason": "برند شناسایی نشد"})
            continue
        cands = [p for p in prod_index if p["brand"] == vbrand and p["code"] not in used
                 and p["code"] not in existing.values()]
        exact = [p for p in cands if vtype and p["type"] == vtype]
        pool = exact if exact else cands
        if not pool:
            review.append({"dkp_id": v["dkp_id"], "title": (v["title"] or "")[:80],
                           "reason": f"کالای {vbrand} در هلو نیست"})
            continue
        if len(pool) == 1 or (vvol and len([p for p in pool if p["vol"] == vvol]) == 1):
            best = pool[0]
            if vvol:
                same_vol = [p for p in pool if p["vol"] == vvol]
                if same_vol:
                    best = same_vol[0]
            used.add(best["code"])
            applied.append({"dkp_id": v["dkp_id"], "code": best["code"], "name": best["name"],
                            "brand": vbrand, "type": vtype})
        else:
            review.append({"dkp_id": v["dkp_id"], "title": (v["title"] or "")[:80],
                           "reason": "چند کاندیدای هم‌برند: " + " | ".join(p["name"][:30] for p in pool[:3])})

    map_path = ROOT / "scripts" / "variant_map.csv"
    with engine.begin() as conn:
        for row in applied:
            conn.execute(text("UPDATE digikala_variants SET holoo_code=:h WHERE dkp_id=:d"),
                         {"h": row["code"], "d": row["dkp_id"]})
    with open(map_path, "a", encoding="utf-8-sig", newline="") as h:
        w = csv.writer(h)
        for row in applied:
            w.writerow([row["dkp_id"], row["code"]])
    review_path = ROOT / "private_exports" / "mapping_review_needed.csv"
    with open(review_path, "w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, fieldnames=["dkp_id", "title", "reason"])
        w.writeheader()
        w.writerows(review)

    print(f"auto-applied: {len(applied)} | review: {len(review)}")
    for row in applied:
        print(f"  {row['brand']} [{row['type']}] dkp {row['dkp_id']} → {row['code']} {row['name'][:45]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
