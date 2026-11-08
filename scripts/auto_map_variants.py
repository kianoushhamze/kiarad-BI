"""Auto-map Digikala variants to Holoo products by fuzzy title matching.

High-confidence unique matches are applied immediately (DB + variant_map.csv).
Ambiguous/low-score cases go to a review CSV for the owner. Safe: never guesses
a mapping below the confidence threshold.
"""
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
MIN_SCORE = 0.62
MARGIN = 0.12  # best must beat runner-up by this much

STOP = set("و از به با در برای حاوی مدل سایز حجم میلی مناسب انواع نوع کالا محصول عدد لیتر گرم تیوب قوطی بسته پک عددی".split())


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    s = re.sub(r"[^0-9a-z\u0600-\u06FF\s\.]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return [t for t in norm(s).split() if t and t not in STOP and len(t) > 1]


def vol(s):
    m = re.search(r"(\d{2,4})\s*(ml|میلی لیتر|میلیلیتر|گرم|g)\b", s, re.I)
    return m.group(1) if m else None


def score(t1, t2):
    tk1, tk2 = set(toks(t1)), set(toks(t2))
    if not tk1 or not tk2:
        return 0.0
    inter, union = tk1 & tk2, tk1 | tk2
    base = len(inter) / len(union)
    en1 = {t for t in tk1 if re.match(r"^[a-z]+$", t)}
    en2 = {t for t in tk2 if re.match(r"^[a-z]+$", t)}
    boost = 0.30 * (len(en1 & en2) / max(len(en1 | en2), 1)) if (en1 and en2) else 0.0
    v1, v2 = vol(t1), vol(t2)
    vol_bonus = 0.15 if (v1 and v2 and v1 == v2) else 0.0
    return min(1.0, base + boost + vol_bonus)


def main() -> int:
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        variants = conn.execute(text("""
            SELECT dkp_id, title, holoo_code FROM digikala_variants
            WHERE holoo_code IS NULL AND status='active' ORDER BY dkp_id
        """)).mappings().all()
        products = conn.execute(text(
            "SELECT code, name FROM products WHERE is_active=1"
        )).mappings().all()

    prod_list = [(p["code"], p["name"], toks(p["name"])) for p in products]
    applied, review = [], []
    used_codes = set()

    with engine.connect() as conn:
        existing = {r[0]: r[1] for r in conn.execute(text(
            "SELECT dkp_id, holoo_code FROM digikala_variants WHERE holoo_code IS NOT NULL")).all()}

    for v in variants:
        vt = v["title"] or ""
        scored = []
        for code, name, ptoks in prod_list:
            if code in used_codes or code in existing.values():
                continue
            s = score(vt, name)
            if s > 0:
                scored.append((s, code, name))
        scored.sort(reverse=True)
        if scored and scored[0][0] >= MIN_SCORE and (len(scored) == 1 or scored[0][0] - scored[1][0] >= MARGIN):
            s, code, name = scored[0]
            used_codes.add(code)
            applied.append({"dkp_id": v["dkp_id"], "holoo_code": code, "score": round(s, 2), "product": name})
        elif scored:
            review.append({"dkp_id": v["dkp_id"], "title": vt[:90],
                           "best": scored[0][1] + " — " + scored[0][2][:50],
                           "best_score": round(scored[0][0], 2),
                           "second": scored[1][1] + " — " + scored[1][2][:50] if len(scored) > 1 else ""})

    # apply to DB + variant_map.csv
    map_path = ROOT / "scripts" / "variant_map.csv"
    with engine.begin() as conn:
        for row in applied:
            conn.execute(text("UPDATE digikala_variants SET holoo_code=:h WHERE dkp_id=:d"),
                         {"h": row["holoo_code"], "d": row["dkp_id"]})
    file_exists = map_path.exists()
    with open(map_path, "a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(["supplier_code", "holoo_code"])
        for row in applied:
            writer.writerow([row["dkp_id"], row["holoo_code"]])

    review_path = ROOT / "private_exports" / "mapping_review_needed.csv"
    with open(review_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dkp_id", "title", "best", "best_score", "second"])
        writer.writeheader()
        writer.writerows(review)

    print(f"auto-applied: {len(applied)}  |  need review: {len(review)}  → {review_path}")
    for row in applied[:15]:
        print(f"  dkp {row['dkp_id']} → {row['holoo_code']} ({row['score']}) {row['product'][:50]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
