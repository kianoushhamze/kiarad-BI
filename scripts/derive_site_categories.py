"""Populate cms_product_meta with site-facing subgroup categories + images.

Subgroups are derived from product-name keywords (cosmetics/pharma vocabulary)
as a sensible default; the owner can override each row later — the site and
/public/catalog read cms_product_meta first, products.category as fallback.
Images come from mapped Digikala variants (raw->>'image_src').
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import DATABASE_URL
from sqlalchemy import create_engine, text  # noqa: E402

DB_URL = DATABASE_URL

# Ordered: first hit wins, so put more specific phrases before generic ones.
SUBGROUP_KEYWORDS = [
    ("ضدآفتاب", ["ضد آفتاب", "ضدآفتاب", "sunscreen", "spf"]),
    ("شامپو", ["شامپو", "shampoo"]),
    ("نرم‌کننده مو", ["نرم کننده", "نرم‌کننده", "بالم مو", " conditioner", "ماسک مو", "ترمیم کننده", "ترمیم‌کننده", "ریزش مو", "تقویت مو", "مخصوص مو"]),
    ("سرم مو", ["سرم مو", "hair serum"]),
    ("رنگ مو", ["رنگ مو", "دکلره", "اکسیژن", "hair color"]),
    ("کرم دور چشم", ["دور چشم", "چشم", "eye cream", "اوربیتال", "orbital"]),
    ("ماسک صورت", ["ماسک صورت", "ماسك صورت", "face mask", "ماسک"]),
    ("سرم صورت", ["سرم", "serum"]),
    ("ضد لک", ["ضد لک", "ضدلک", "روشن کننده", "روشن‌کننده"]),
    ("ضد جوش", ["ضد جوش", "ضدجوش", "آکنه", "acne"]),
    ("ضد چروک", ["ضد چروک", "ضدچروک", "جوانساز", "آنتی ایج", "anti", "پیشگیری از پیری"]),
    ("مرطوب کننده", ["مرطوب کننده", "مرطوب‌کننده", "هیدراته", "moisturizer", "آبرسان"]),
    ("پاک‌کننده", ["پاک کننده", "پاک‌کننده", "شست و شو", "شست‌وشو", "شوینده", "cleanser", "ژل شستشو", "غسل دهنده", "لایه بردار مکانیکی"]),
    ("تونر", ["تونر", "toner"]),
    ("کرم بدن", ["کرم بدن", "بادی باتر", "لوسیون بدن", "body"]),
    ("کرم دست", ["کرم دست", "هند کرم"]),
    ("کانتورینگ", ["کانتورینگ", "کانتور", "contour"]),
    ("پرایمر", ["پرایمر", "primer"]),
    ("پودر صورت", ["پودر", "پاف", "powder"]),
    ("کرم پودر", ["کرم پودر", "foundation"]),
    ("رژ لب", ["رژ لب", "روژ", "lipstick", "بالم لب", "لیپ"]),
    ("خط چشم", ["خط چشم", "ایلاینر", "eyeliner", "کاجل", "مداد ابرو", "سایه ابرو", "اشدو"]),
    ("ریمل", ["ریمل", "mascara"]),
    ("سایه چشم", ["سایه چشم", "اشدو", "eyeshadow", "پالت"]),
    ("ژل بدن", ["ژل", "gel"]),
    ("لوسیون", ["لوسیون", "lotion"]),
    ("روغن", ["روغن", "oil"]),
    ("اسکراب", ["اسکراب", "scrub", "پیلینگ", "peeling"]),
    ("خمیردندان", ["خمیر دندان", "خمیردندان", "دهان شویه", "دهان‌وشویه", "مسواک"]),
    ("عطر و بو", ["عطر", "ادکلن", "اسپری خوشبو", "بودی اسپری", "perfume"]),
    ("مکمل و ویتامین", ["ویتامین", "مکمل", "قرص", "کپسول", "زینک", "کلاژن"]),
    ("سوپ و غذای کمکی", ["سوپ", "غذای کمکی", "کمکی کودک"]),
    ("کودک", ["کودک", "بچه", "بیبی", "baby", "نوزاد"]),
]


def derive(name: str) -> str:
    lowered = name.lower()
    for label, keys in SUBGROUP_KEYWORDS:
        for key in keys:
            if key in lowered or key in name:
                return label
    return "متفرقه"


def main() -> int:
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS cms_product_meta(
            code VARCHAR(100) PRIMARY KEY, site_category TEXT, image_url TEXT,
            hidden BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        products = conn.execute(text("""
            SELECT p.code, p.name, p.category,
                   (SELECT v.raw->>'image_src' FROM digikala_variants v
                     WHERE v.holoo_code = p.code ORDER BY v.updated_at DESC NULLS LAST LIMIT 1) AS image_url
            FROM products p WHERE p.is_active = 1
        """)).mappings().all()
        inserted = 0
        force = "--force" in sys.argv  # recompute auto categories (owner edits: none yet)
        for row in products:
            existing = conn.execute(text(
                "SELECT site_category FROM cms_product_meta WHERE code=:c"
            ), {"c": row["code"]}).scalar()
            category = (derive(row["name"] or "") if force else None) or existing or derive(row["name"] or "")
            conn.execute(text("""
                INSERT INTO cms_product_meta (code, site_category, image_url, hidden, updated_at)
                VALUES (:c, :cat, :img, FALSE, NOW())
                ON CONFLICT (code) DO UPDATE SET
                    site_category=EXCLUDED.site_category,
                    image_url=COALESCE(EXCLUDED.image_url, cms_product_meta.image_url),
                    updated_at=NOW()
            """), {"c": row["code"], "cat": category, "img": row["image_url"]})
            inserted += 1
        from collections import Counter
        counts = Counter(conn.execute(text(
            "SELECT site_category FROM cms_product_meta")).scalars().all())
    print(f"cms_product_meta: {inserted} products")
    for label, count in counts.most_common(12):
        print(f"  {label}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
