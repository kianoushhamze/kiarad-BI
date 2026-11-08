import os, re, sys
root = os.environ.get("DK_ROOT", "")
outf = os.environ.get("DK_CODEFILE", "")
skip = (".venv", "venv", "node_modules", ".git", "__pycache__", "logs", "uploads", "photos", ".next")
ok_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
hits = list()

def normblob(s):
    return re.sub("\\s+", "", s)

def scan_text(txt, fp):
    found = list()
    val = ""
    m = re.search("(?i)(\\w*B64\\w*)\\s*=\\s*\"(.+?)\"", txt, re.S)
    if m:
        val = m.group(2)
    else:
        m = re.search("(?i)(\\w*B64\\w*)\\s*=\\s*'(.+?)'", txt, re.S)
        if m:
            val = m.group(2)
    if val:
        b = normblob(val)
        if len(b) >= 150 and all(c in ok_chars for c in b):
            found.append(b)
    low = txt.lower()
    if ("decrypt" in low) and ("token" in low) and fp.endswith(".py"):
        cur = list()
        for ch in txt:
            if (ch in ok_chars) or (ch == " ") or (ch == "\r") or (ch == "\n") or (ch == "\t"):
                cur.append(ch)
            else:
                if len(cur) > 0:
                    b = normblob("".join(cur))
                    if len(b) >= 300 and all(c in ok_chars for c in b):
                        found.append(b)
                    cur = list()
        if len(cur) > 0:
            b = normblob("".join(cur))
            if len(b) >= 300 and all(c in ok_chars for c in b):
                found.append(b)
    return found

if root and outf:
    for dirpath, dirnames, filenames in os.walk(root):
        keep = list()
        for dn in dirnames:
            if dn not in skip:
                keep.append(dn)
        dirnames.clear()
        dirnames.extend(keep)
        for name in filenames:
            if not name.endswith((".py", ".txt", ".json")):
                continue
            fp = os.path.join(dirpath, name)
            try:
                txt = open(fp, "r", encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            for b in scan_text(txt, fp):
                hits.append((fp, b))

if len(hits) == 0:
    print("BLOB_NONE")
    sys.exit(0)
best_score = -1
best_fp = ""
best_blob = ""
for fp2, b2 in hits:
    score = len(b2)
    if "token" in os.path.basename(fp2).lower():
        score = score + 100000
    if score > best_score:
        best_score = score
        best_fp = fp2
        best_blob = b2
open(outf, "w", encoding="ascii").write(best_blob)
print("BLOB_OK len=" + str(len(best_blob)) + " src=" + os.path.basename(best_fp))
