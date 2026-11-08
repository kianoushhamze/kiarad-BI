import csv, re, sys, unicodedata

STOP = set("مدل حجم میلی لیتر میلیلیتر میلیلیتری گرم گرمی گارانتی اصلی اورجینال برند شرکتی بسته عدد و با در به از برای یا the of and for with".split())
PMAP = {"ي":"ی","ك":"ک","آ":"ا","أ":"ا","إ":"ا","ة":"ه"}
for i,c in enumerate("۰۱۲۳۴۵۶۷۸۹"): PMAP[c] = str(i)

def norm(s):
    if not s: return ""
    out = []
    for ch in str(s).strip():
        out.append(PMAP.get(ch, ch))
    s = unicodedata.normalize("NFKC", "".join(out)).lower()
    s = re.sub(r"[^0-9a-z\u0600-\u06FF\s\.]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def toks(s):
    return [t for t in norm(s).split() if t and t not in STOP]

def vol(s):
    m = re.search(r"(\d{2,4})\s*(ml|میلی\s*لیتر|میلیلیتر|گرم|g)\b", s, re.I)
    return m.group(1) if m else None

def spf(s):
    m = re.search(r"spf\s*(\d{1,3})", s, re.I)
    return m.group(1) if m else None

def color(s):
    m = re.search(r"\b([cnCN]\d{1,3})\b", s)
    return m.group(1).lower() if m else None

def score(t1, t2):
    tk1, tk2 = set(toks(t1)), set(toks(t2))
    if not tk1 or not tk2: return 0.0
    inter, union = tk1 & tk2, tk1 | tk2
    if not union: return 0.0
    base = len(inter) / len(union)
    en1 = {t for t in tk1 if re.match(r"^[a-z]+$", t)}
    en2 = {t for t in tk2 if re.match(r"^[a-z]+$", t)}
    boost = 0.30 * (len(en1 & en2) / max(len(en1 | en2), 1)) if (en1 and en2) else 0.0
    v1, v2 = vol(t1), vol(t2)
    vd = (0.20 if v1==v2 else -0.20) if (v1 and v2) else 0.0
    s1, s2 = spf(t1), spf(t2)
    sd = (0.15 if s1==s2 else -0.15) if (s1 and s2) else 0.0
    c1, c2 = color(t1), color(t2)
    cd = (0.10 if c1==c2 else -0.10) if (c1 and c2) else 0.0
    return max(0.0, min(1.0, base + boost + vd + sd + cd))

def main():
    p_file, d_file, o_file = sys.argv[1], sys.argv[2], sys.argv[3]
    prods = [{"code": r["code"], "name": r["name"]} for r in csv.DictReader(open(p_file, encoding="utf-8-sig"))]
    dks = [{"dkp_id": r["dkp_id"], "title": r["title"]} for r in csv.DictReader(open(d_file, encoding="utf-8-sig"))]
    hits = {}
    rows = []
    for d in dks:
        scored = sorted([{"p": p, "s": score(d["title"], p["name"])} for p in prods], key=lambda x: x["s"], reverse=True)
        top = scored[0] if scored else None
        sec = scored[1] if len(scored) > 1 else None
        level, match, margin = "NONE", None, 0.0
        if top:
            margin = top["s"] - (sec["s"] if sec else 0.0)
            if top["s"] >= 0.40:
                level = "AUTO" if margin >= 0.05 else "REVIEW"
                match = top["p"]
            elif top["s"] >= 0.22:
                level = "REVIEW"
                match = top["p"]
        if match:
            hits.setdefault(match["code"], []).append(d["dkp_id"])
        rows.append({"dkp_id": d["dkp_id"], "digikala_title": d["title"],
                     "holoo_code": match["code"] if match else "",
                     "holoo_name": match["name"] if match else "",
                     "score": round(top["s"], 3) if top else 0,
                     "margin": round(margin, 3), "level": level, "warn": ""})
    for r in rows:
        if r["holoo_code"] and len(hits.get(r["holoo_code"], [])) > 1:
            r["warn"] = "DUP"
    with open(o_file, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dkp_id","digikala_title","holoo_code","holoo_name","score","margin","level","warn"])
        w.writeheader()
        [w.writerow(r) for r in rows]
    a = sum(1 for r in rows if r["level"]=="AUTO")
    b = sum(1 for r in rows if r["level"]=="REVIEW")
    c = sum(1 for r in rows if r["level"]=="NONE")
    print(f"AUTO={a} REVIEW={b} NONE={c} TOTAL={len(rows)}")

if __name__ == "__main__":
    main()