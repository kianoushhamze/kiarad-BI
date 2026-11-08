import os, csv, re, sys
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME", "kiaradbi"),
    user=os.getenv("DB_USER", "kiarad"),
    password=os.getenv("POSTGRES_PASSWORD"),
)
cur = conn.cursor()
cur.execute("SELECT code, name FROM products WHERE is_active=1")
holo = [{"code": r[0], "name": r[1]} for r in cur.fetchall()]
cur.execute("SELECT dkp_id, title FROM digikala_variants ORDER BY dkp_id")
dk = [{"dkp_id": r[0], "title": r[1]} for r in cur.fetchall()]
conn.close()

BRANDS = {
    "LABOREN":   "\u0644\u0627\u0628\u0648\u0631\u0646",
    "DELANO":    "\u062f\u0644\u0627\u0646\u0648",
    "DERMALIST": "\u062f\u0631\u0645\u0627\u0644\u06cc\u0633\u062a",
    "PLEASANT":  "\u067e\u0644\u0632\u0646\u062a",
    "LUCEL":     "\u0644\u0648\u0633\u0644",
    "MILITO":    "\u0645\u06cc\u0644\u06cc\u062a\u0648",
    "TOTAL":     "\u062a\u0648\u062a\u0627\u0644",
    "RICHMOND":  "\u0631\u06cc\u0686\u0645\u0648\u0646\u062f",
    "RINKON":    "\u0631\u06cc\u0646\u06a9\u0648\u0646",
    "ELVATAN":   "\u0627\u0644\u0648\u0627\u062a\u0627\u0646",
    "ACHIOTE":   "\u0622\u06a9\u06cc\u0648\u062a\u0647",
    "VINUR":     "\u0648\u06cc\u0646\u0648\u0631",
    "CYNO":      "\u0633\u06cc\u0646\u0648",
}

def detect_brand(t):
    for b, p in BRANDS.items():
        if p in t:
            return b
    return None

def norm(s):
    s = s.lower()
    s = s.replace("\u064a", "\u06cc")
    s = s.replace("\u0643", "\u06a9")
    s = s.replace("\u0622", "\u0627")
    s = re.sub(r"[^\w\s\u0600-\u06FF]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get_tokens(s):
    return set(norm(s).split())

def jaccard(a, b):
    aa = get_tokens(a)
    bb = get_tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)

holo_by_brand = {}
for h in holo:
    bk = h["name"].split()[0].upper()
    holo_by_brand.setdefault(bk, []).append(h)

brand_distinct = {}
for bk, prods in holo_by_brand.items():
    freq = Counter()
    for p in prods:
        for t in get_tokens(p["name"]):
            freq[t] += 1
    brand_distinct[bk] = set(t for t, c in freq.items() if c == 1)

rows = []
for d in dk:
    brand = detect_brand(d["title"])
    if not brand:
        rows.append({**d, "brand": "", "holo_code": "", "holo_name": "", "score": 0, "level": "NO_BRAND", "reason": ""})
        continue
    if brand not in holo_by_brand:
        rows.append({**d, "brand": brand, "holo_code": "", "holo_name": "", "score": 0, "level": "NO_HOLO", "reason": "no holo for " + brand})
        continue
    cands = holo_by_brand[brand]
    if len(cands) == 1:
        c = cands[0]
        rows.append({**d, "brand": brand, "holo_code": c["code"], "holo_name": c["name"], "score": 1.0, "level": "AUTO", "reason": "unique"})
        continue
    dist = brand_distinct[brand]
    title_toks = get_tokens(d["title"])
    title_dist = title_toks & dist
    best_c = None
    best_cnt = 0
    best_common = set()
    for c in cands:
        common = title_dist & get_tokens(c["name"])
        if len(common) > best_cnt:
            best_cnt = len(common)
            best_c = c
            best_common = common
    if best_cnt >= 1:
        lv = "AUTO"
        sc = round(0.5 + 0.1 * best_cnt, 3)
        reason = "dist=" + ",".join(sorted(best_common))
    else:
        scored = sorted([(c, jaccard(d["title"], c["name"])) for c in cands], key=lambda x: -x[1])
        top_c, top_j = scored[0]
        sec_j = scored[1][1] if len(scored) > 1 else 0
        m = top_j - sec_j
        if top_j >= 0.30 and m >= 0.10:
            lv = "AUTO"
            sc = round(top_j, 3)
        elif top_j >= 0.15:
            lv = "REVIEW"
            sc = round(top_j, 3)
        else:
            lv = "NONE"
            sc = round(top_j, 3)
        best_c = top_c
        reason = "jac=" + str(round(top_j, 2)) + " m=" + str(round(m, 2))
    rows.append({**d, "brand": brand, "holo_code": best_c["code"], "holo_name": best_c["name"], "score": sc, "level": lv, "reason": reason})

out = Path(__file__).resolve().parents[1] / "scripts" / "brand_match_result.csv"
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["dkp_id", "title", "brand", "holo_code", "holo_name", "score", "level", "reason"])
    w.writeheader()
    w.writerows(rows)

a = sum(1 for r in rows if r["level"] == "AUTO")
rv = sum(1 for r in rows if r["level"] == "REVIEW")
n = sum(1 for r in rows if r["level"] == "NONE")
nb = sum(1 for r in rows if r["level"] == "NO_BRAND")
nh = sum(1 for r in rows if r["level"] == "NO_HOLO")
print(f"AUTO={a} REVIEW={rv} NONE={n} NO_BRAND={nb} NO_HOLO={nh} TOTAL={len(rows)}")
print("By brand:")
for b, c in Counter(r["brand"] for r in rows if r["brand"]).most_common():
    print(f"  {b}: {c}")
print("CSV: " + str(out))