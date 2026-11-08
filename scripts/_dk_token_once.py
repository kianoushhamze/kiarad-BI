import os, sys, json, base64, urllib.request, urllib.parse, urllib.error

def die(msg):
    print("TOKENS_FAIL: " + msg)
    sys.exit(1)

cf = os.environ.get("DK_CODEFILE", "")
of = os.environ.get("DK_OUT", "")
mode = os.environ.get("DK_MODE", "refresh")
if not of:
    die("missing env")
sdir = os.path.dirname(of)
old_acc = ""
old_ref = ""
cc = ""
tokbase = os.path.join(sdir, "digikala_tokens.json")
if os.path.isfile(tokbase):
    try:
        j = json.loads(open(tokbase, "r", encoding="utf-8-sig").read())
        cc = j.get("client_code", "") or ""
        old_acc = j.get("access_token", "") or ""
        old_ref = j.get("refresh_token", "") or ""
        d = j.get("data", None)
        if isinstance(d, dict):
            if not cc:
                cc = d.get("client_code", "") or ""
            if not old_acc:
                old_acc = d.get("access_token", "") or ""
            if not old_ref:
                old_ref = d.get("refresh_token", "") or ""
    except Exception:
        pass

def post(url, payload, form, ua):
    hd = dict()
    hd.update(**{"User-Agent": ua, "Accept": "application/json"})
    body = None
    if form:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        hd.update(**{"Content-Type": "application/x-www-form-urlencoded"})
    else:
        body = json.dumps(payload).encode("utf-8")
        hd.update(**{"Content-Type": "application/json"})
    req = urllib.request.Request(url, data=body, headers=hd, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

authcode = ""
decnote = ""
if mode == "code":
    pemp = os.path.join(sdir, "digikala_private.pem")
    try:
        if not os.path.isfile(pemp):
            decnote = "private key not found"
        elif not os.path.isfile(cf):
            decnote = "code file missing"
        else:
            raw = open(cf, "r", encoding="utf-8-sig", errors="replace").read()
            code = "".join(raw.split()).strip('"').strip("'")
            if len(code) < 20:
                decnote = "code too short"
            else:
                from cryptography.hazmat.primitives import serialization, hashes
                from cryptography.hazmat.primitives.asymmetric import padding
                pem = open(pemp, "rb").read()
                key = serialization.load_pem_private_key(pem, password=None)
                blob = base64.b64decode(code)
                dec = None
                try:
                    dec = key.decrypt(blob, padding.PKCS1v15())
                except Exception as e1:
                    dec = key.decrypt(blob, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA1()), algorithm=hashes.SHA1(), label=None))
                authcode = dec.decode("utf-8", "replace").strip()
    except ImportError:
        decnote = "cryptography module missing - refresh path will be used"
    except Exception as e:
        decnote = "decrypt failed: " + repr(e)
    if decnote:
        print("DECRYPT_NOTE: " + decnote)

uas = list()
uas.append("DigikalaTrustedBot/SelfToken")
uas.append("kiarad-bi")
uas.append("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36")
got = None
final = "no attempt made"
if decnote:
    final = "note: " + decnote
url = "https://seller.digikala.com/open-api/v1/auth/token"
tries = list()
if authcode:
    tries.append(("A", dict(authorization_code=authcode), True))
    tries.append(("B", dict(authorization_code=authcode), False))
    if cc:
        tries.append(("C", dict(authorization_code=authcode, client_code=cc), True))
        tries.append(("D", dict(authorization_code=authcode, client_code=cc), False))
for tag, payload, form in tries:
    for ua in uas:
        try:
            raw2 = post(url, payload, form, ua)
            j2 = json.loads(raw2)
            d2 = j2.get("data", None)
            if isinstance(d2, dict) and d2.get("access_token", ""):
                got = d2
                print("TOKENS_OK attempt " + tag + " ua=" + ua)
                break
            final = "attempt " + tag + " ua=" + ua + " body: " + raw2
        except urllib.error.HTTPError as e:
            eb = ""
            try:
                eb = e.read().decode("utf-8", "replace")
            except Exception:
                eb = ""
            final = "attempt " + tag + " ua=" + ua + " HTTP " + str(e.code) + " body: " + eb
        except Exception as e:
            final = "attempt " + tag + " ua=" + ua + " error: " + repr(e)
    if got is not None:
        break
if got is None and old_ref:
    rurl = "https://seller.digikala.com/open-api/v1/auth/refresh-token"
    for rtag, rform in (("R1", False), ("R2", True)):
        for ua in uas:
            rpay = dict()
            rpay.update(access_token=old_acc, refresh_token=old_ref)
            try:
                raw3 = post(rurl, rpay, rform, ua)
                j3 = json.loads(raw3)
                d3 = j3.get("data", None)
                if isinstance(d3, dict) and d3.get("access_token", ""):
                    got = d3
                    print("TOKENS_OK_VIA_REFRESH " + rtag + " ua=" + ua)
                    break
                final = "refresh " + rtag + " ua=" + ua + " body: " + raw3
            except urllib.error.HTTPError as e:
                eb = ""
                try:
                    eb = e.read().decode("utf-8", "replace")
                except Exception:
                    eb = ""
                final = "refresh " + rtag + " ua=" + ua + " HTTP " + str(e.code) + " body: " + eb
            except Exception as e:
                final = "refresh " + rtag + " ua=" + ua + " error: " + repr(e)
        if got is not None:
            break
if got is None:
    die(final)
payload = dict()
for k in ("access_token", "refresh_token", "seller_id", "client_code", "expires_in", "token_type"):
    v = got.get(k, "")
    if v:
        payload.update(**{k: v})
payload.update(saved_at=os.path.basename(of))
with open(of, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print("access_len: " + str(len(got.get("access_token", ""))))
print("refresh_len: " + str(len(got.get("refresh_token", ""))))
print("client_code: " + str(got.get("client_code", cc)))
print("saved: " + of)
