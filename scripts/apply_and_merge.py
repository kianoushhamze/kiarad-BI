import os, csv, re, json
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env")
csv_in = root / "scripts" / "brand_match_result.csv"
csv_out = root / "scripts" / "brand_match_final.csv"
site_path = root / "site" / "data.json"

rows = list(csv.DictReader(open(csv_in, encoding="utf-8-sig")))
print("rows: " + str(len(rows)))

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME", "kiaradbi"),
    user=os.getenv("DB_USER", "kiarad"),
    password=os.getenv("POSTGRES_PASSWORD"),
)
cur = conn.cursor()
cur.execute("SELECT code, name FROM products WHERE is_active=1")
holo = [(c, n) for c, n in cur.fetchall()]
cur.execute("SELECT dkp_id, title FROM digikala_variants ORDER BY dkp_id")
dk = [(d, t) for d, t in cur.fetchall()]

holo_by_brand = {}
for c, n in holo:
    bk = n.split()[0].upper() if n.split() else ""
    holo_by_brand.setdefault(bk, []).append((c, n))

brand_distinct = {}
for bk, prods in holo_by_brand.items():
    freq = Counter()
    for _, n in prods:
        for t in set(n.lower().split()):
            freq[t] += 1
    brand_distinct[bk] = {t for t, c in freq.items() if c == 1}

def get_tokens(s):
    s = s.lower()
    s = s.replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u0622", "\u0627")
    s = re.sub(r"[^\w\s\u0600-\u06FF]", " ", s)
    return set(s.split())

def jaccard(a, b):
    aa, bb = get_tokens(a), get_tokens(b)
    return len(aa & bb) / len(aa | bb) if aa and bb else 0.0

brand_map = {}
for r in rows:
    t = r.get("title", "")
    detected = None
    for bk in holo_by_brand:
        pass
    detected = r.get("brand", "") or ""

BRAND_PERSIAN = {
    "LABOREN": "\u0644\u0627\u0628\u0648\u0631\u0646",
    "DELANO": "\u062f\u0644\u0627\u0646\u0648",
    "DERMALIST": "\u062f\u0631\u0645\u0627\u0644\u06cc\u0633\u062a",
    "PLEASANT": "\u067e\u0644\u0632\u0646\u062a",
    "LUCEL": "\u0644\u0648\u0633\u0644",
    "MILITO": "\u0645\u06cc\u0644\u06cc\u062a\u0648",
    "TOTAL": "\u062a\u0648\u062a\u0627\u0644",
    "RICHMOND": "\u0631\u06cc\u0686\u0645\u0648\u0646\u062f",
    "RINKON": "\u0631\u06cc\u0646\u06a9\u0648\u0646",
    "ELVATAN": "\u0627\u0644\u0648\u0627\u062a\u0627\u0646",
    "ACHIOTE": "\u0622\u06a9\u06cc\u0648\u062a\u0647",
    "VINUR": "\u0648\u06cc\u0646\u0648\u0631",
    "CYNO": "\u0633\u06cc\u0646\u0648",
}

PRODUCT_FORMS = {
    "شامپو": {"شامپو"},
    "ماسک": {"ماسک"},
    "سرم": {"سرم"},
    "کرم": {"کرم"},
    "ژل": {"ژل"},
    "لوسیون": {"لوسیون"},
    "فوم": {"فوم"},
    "تونر": {"تونر"},
    "اسپری": {"اسپری"},
}

def product_forms(text):
    tokens = get_tokens(text)
    return {form for form, aliases in PRODUCT_FORMS.items() if tokens & aliases}

def detect_brand(t):
    for b, p in BRAND_PERSIAN.items():
        if p in t:
            return b
    return None

new_rows = []
for dkp, title in dk:
    brand = detect_brand(title)
    if not brand:
        new_rows.append({"dkp_id": str(dkp), "title": title, "brand": "", "holo_code": "", "holo_name": "", "score": 0, "level": "NO_BRAND", "reason": ""})
        continue
    cands = holo_by_brand.get(brand, [])
    if not cands:
        new_rows.append({"dkp_id": str(dkp), "title": title, "brand": brand, "holo_code": "", "holo_name": "", "score": 0, "level": "NO_HOLO", "reason": ""})
        continue
    dist = brand_distinct.get(brand, set())
    dk_toks = get_tokens(title)
    scores = []
    for c, n in cands:
        c_dist = get_tokens(n) & dist
        matches = c_dist & dk_toks
        scores.append((c, n, len(matches)))
    scores.sort(key=lambda x: -x[2])
    top_cnt = scores[0][2]
    if top_cnt >= 1:
        ties = [s for s in scores if s[2] == top_cnt]
        if len(ties) == 1:
            candidate_code, candidate_name, _ = scores[0]
            source_forms = product_forms(title)
            candidate_forms = product_forms(candidate_name)
            if source_forms and candidate_forms and source_forms.isdisjoint(candidate_forms):
                new_rows.append({"dkp_id": str(dkp), "title": title, "brand": brand, "holo_code": candidate_code, "holo_name": candidate_name, "score": round(0.5 + 0.1 * top_cnt, 3), "level": "REVIEW", "reason": "product_form_mismatch"})
            else:
                new_rows.append({"dkp_id": str(dkp), "title": title, "brand": brand, "holo_code": candidate_code, "holo_name": candidate_name, "score": round(0.5 + 0.1 * top_cnt, 3), "level": "AUTO", "reason": "distinct=" + str(top_cnt)})
        else:
            new_rows.append({"dkp_id": str(dkp), "title": title, "brand": brand, "holo_code": scores[0][0], "holo_name": scores[0][1], "score": round(0.5 + 0.1 * top_cnt, 3), "level": "REVIEW", "reason": "tie=" + str(len(ties))})
    else:
        new_rows.append({"dkp_id": str(dkp), "title": title, "brand": brand, "holo_code": "", "holo_name": "", "score": 0, "level": "NONE", "reason": "no_distinct"})

auto_freq = Counter(r["holo_code"] for r in new_rows if r["level"] == "AUTO" and r["holo_code"])
for r in new_rows:
    if r["level"] == "AUTO" and auto_freq.get(r["holo_code"], 0) > 1:
        r["level"] = "REVIEW"
        r["reason"] += " (dup_holo)"

cur.execute("SELECT supplier_code, holoo_code FROM variant_map WHERE note LIKE 'reviewed exact model %'")
reviewed = {str(v): str(c) for v, c in cur.fetchall()}
names_by_code = {str(c): n for c, n in holo}
for r in new_rows:
    code = reviewed.get(str(r["dkp_id"]))
    if code in names_by_code:
        r.update(holo_code=code, holo_name=names_by_code[code], level="REVIEWED", reason="exact_model_review", score=1.0)

a = sum(1 for r in new_rows if r["level"] == "AUTO")
rv = sum(1 for r in new_rows if r["level"] == "REVIEW")
n = sum(1 for r in new_rows if r["level"] == "NONE")
nb = sum(1 for r in new_rows if r["level"] == "NO_BRAND")
print("AUTO=" + str(a) + " REVIEW=" + str(rv) + " NONE=" + str(n) + " NO_BRAND=" + str(nb))

with open(csv_out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["dkp_id", "title", "brand", "holo_code", "holo_name", "score", "level", "reason"])
    w.writeheader()
    w.writerows(new_rows)

autos = [r for r in new_rows if r["level"] == "AUTO" and r["holo_code"]]
print("Applying AUTO: " + str(len(autos)))
cur.execute("DELETE FROM variant_map WHERE note IS NULL OR note NOT LIKE 'reviewed exact model %'")
cur.execute("UPDATE digikala_variants SET holoo_code = NULL")
for r in autos:
    cur.execute("SELECT 1 FROM variant_map WHERE supplier_code = %s", (str(r["dkp_id"]),))
    if cur.fetchone():
        continue
    cur.execute(
        "INSERT INTO variant_map (supplier_code, holoo_code, note, updated_at) VALUES (%s, %s, %s, NOW())",
        (str(r["dkp_id"]), r["holo_code"], "brand=" + r["brand"])
    )
conn.commit()
cur.execute("UPDATE digikala_variants v SET holoo_code = m.holoo_code FROM variant_map m WHERE v.holoo_code IS NULL AND v.dkp_id::text = m.supplier_code")
conn.commit()
cur.execute("SELECT count(*) FROM variant_map")
vm = cur.fetchone()[0]
cur.execute("SELECT count(holoo_code) FROM digikala_variants")
dkf = cur.fetchone()[0]
print("variant_map: " + str(vm) + " rows")
print("digikala_variants: " + str(dkf) + "/50 have holoo_code")

cur.execute("""
    SELECT v.holoo_code, v.price_selling, v.stock, v.title
    FROM digikala_variants v WHERE v.holoo_code IS NOT NULL
""")
dk_prices = {}
for h, p, s, t in cur.fetchall():
    if h not in dk_prices:
        dk_prices[h] = {"price_toman": (int(p) // 10) if p else 0, "stock": int(s) if s else 0, "title": t}
conn.close()

data = json.loads(site_path.read_text(encoding="utf-8"))
merged = 0
for prod in data["products"]:
    prod.pop("price_digikala_toman", None)
    prod.pop("stock_digikala", None)
    prod.pop("digikala_title", None)
    if prod.get("holoo_code") in dk_prices:
        info = dk_prices[prod["holoo_code"]]
        prod["price_digikala_toman"] = info["price_toman"]
        prod["stock_digikala"] = info["stock"]
        prod["digikala_title"] = info["title"]
        merged += 1
site_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("site products with digikala: " + str(merged))
print("site products total: " + str(len(data["products"])))
