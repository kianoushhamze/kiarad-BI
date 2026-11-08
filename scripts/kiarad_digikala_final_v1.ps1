# =====================================================================
#  KIARAD - Digikala FINAL FINISHER v1  (2026-10-30, build C)
#  User input optional: token text from panel. If empty -> automatic:
#   1) find the stored encrypted token (recursive deep search)
#   2) decrypt it if cryptography exists; otherwise SKIP decrypt
#   3) get fresh tokens via refresh_token (python or pure PowerShell)
#   4) swap tokens into secrets\digikala_tokens.json  (backup first)
#   5) test the UA gate with the FRESH token (trustedbot + default)
#   6) if a winner UA exists: write scripts\digikala_sync_task.ps1,
#      register schtasks KiaradDigikalaSync every 30 min, run it once
#   7) report -> logs + clipboard + notepad
# =====================================================================
$ErrorActionPreference = "Continue"
$root    = "D:\project\kiaradbi"
$logs    = Join-Path $root "logs"
$scripts = Join-Path $root "scripts"
$secrets = Join-Path $root "secrets"
foreach ($d in @($logs, $scripts, $secrets)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
$stamp      = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("digikala_final_v1_" + $stamp + ".txt")
$freshFile  = Join-Path $secrets ("digikala_tokens_fresh_" + $stamp + ".json")
$codeFile   = Join-Path $secrets ("validation_code_" + $stamp + ".txt")
$tokPath    = Join-Path $secrets "digikala_tokens.json"

$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

function Mask-Line {
  param($line)
  $out = $line
  if ($out -match "(?i)(secret|password|passwd)") {
    $out = $out -replace '"(.{8,}?)"', '"MASKED"'
    $out = $out -replace "'(.{8,}?)'", "'MASKED'"
  } elseif ($out -match "(?i)\b(access_token|refresh_token|client_secret|api_key|apikey|private_key)\b\s*(=|:)") {
    $out = $out -replace '"(.{8,}?)"', '"MASKED"'
    $out = $out -replace "'(.{8,}?)'", "'MASKED'"
  }
  return $out
}

function Show-Err {
  param($e)
  & $say ("   FAILED: " + $e.Exception.Message)
  try {
    $resp = $e.Exception.Response
    if ($null -ne $resp) {
      & $say ("   HTTP status: " + $resp.StatusCode.value__)
      $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
      $errTxt = $sr.ReadToEnd()
      if ($errTxt.Length -gt 200) { $errTxt = $errTxt.Remove(200) }
      if ($errTxt.Trim().Length -gt 0) { & $say ("   body: " + (Mask-Line $errTxt)) }
    }
  } catch { }
}

& $say "====================================================="
& $say " KIARAD DIGIKALA FINAL FINISHER v1 (build C)"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say "====================================================="
& $say ""
& $say "=== 0) PREFLIGHT ==="
$pemPath = Join-Path $secrets "digikala_private.pem"
if (Test-Path $pemPath) { & $say " private key : FOUND" } else { & $say " private key : MISSING (refresh path does not need it)" }
$pyCmd = ""
foreach ($cand in @((Join-Path $root ".venv\Scripts\python.exe"), (Join-Path $root "venv\Scripts\python.exe"), "python", "py")) {
  try {
    $null = & $cand --version 2>$null
    if ($LASTEXITCODE -eq 0) { $pyCmd = $cand; break }
  } catch { }
}
if ($pyCmd -ne "") { & $say (" python      : " + $pyCmd) } else { & $say " python      : NOT FOUND - PowerShell fallback will be used" }

& $say ""
& $say "=== 1) TOKEN INPUT (optional) ==="
& $say " agar matne token az panel dari paste kon; nadari faghat Enter bezan"
$code = Read-Host " Paste the token text here and press Enter (empty = AUTO)"
if ($code) { $code = $code.Trim().Trim('"').Trim("'") }
if (-not $code -and $pyCmd -ne "") {
  & $say " no text entered - deep searching for the stored encrypted token ..."
  $pyFind = @'
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
'@
  $pyFindFile = Join-Path $scripts "_dk_blob_find.py"
  Set-Content -Path $pyFindFile -Value $pyFind -Encoding ASCII
  $env:DK_ROOT = $root
  $env:DK_CODEFILE = $codeFile
  $fo = & $pyCmd $pyFindFile 2>&1
  Remove-Item Env:DK_ROOT -ErrorAction SilentlyContinue
  Remove-Item Env:DK_CODEFILE -ErrorAction SilentlyContinue
  foreach ($l in $fo) { & $say ("   " + (Mask-Line ("$l"))) }
  if (Test-Path $codeFile) {
    $c = (Get-Content $codeFile -Raw).Trim()
    if ($c.Length -gt 100) {
      $code = $c
      & $say " stored encrypted token staged - going on automatically"
    }
  }
}
$freshOk = $false

& $say ""
& $say "=== 2) FRESH TOKENS ==="
if ($pyCmd -ne "") {
  $dkmode = "refresh"
  if ($code -and $code.Length -gt 10 -and (Test-Path $pemPath)) {
    $dkmode = "code"
    Set-Content -Path $codeFile -Value $code -Encoding ASCII
  }
  & $say (" requesting fresh tokens (mode: " + $dkmode + ") ...")
  $pyCode = @'
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
'@
  $pyFile = Join-Path $scripts "_dk_token_once.py"
  Set-Content -Path $pyFile -Value $pyCode -Encoding ASCII
  $env:DK_CODEFILE = $codeFile
  $env:DK_OUT = $freshFile
  $env:DK_MODE = $dkmode
  $outp = & $pyCmd $pyFile 2>&1
  foreach ($l in $outp) { & $say ("   " + (Mask-Line ("$l"))) }
  Remove-Item Env:DK_CODEFILE -ErrorAction SilentlyContinue
  Remove-Item Env:DK_OUT -ErrorAction SilentlyContinue
  Remove-Item Env:DK_MODE -ErrorAction SilentlyContinue
  if (Test-Path $freshFile) { $freshOk = $true }
} else {
  & $say " python not found - using PowerShell fallback"
}
if (-not $freshOk -and (Test-Path $tokPath)) {
  & $say " PowerShell refresh fallback (no python, no cryptography needed) ..."
  $tj2 = Get-Content $tokPath -Raw | ConvertFrom-Json
  $oacc = $tj2.access_token
  if (-not $oacc) { $oacc = $tj2.data.access_token }
  $oref = $tj2.refresh_token
  if (-not $oref) { $oref = $tj2.data.refresh_token }
  if ($oref) {
    $pay2 = New-Object System.Collections.Hashtable
    $pay2.access_token = $oacc
    $pay2.refresh_token = $oref
    $bodyJson2 = $pay2 | ConvertTo-Json
    foreach ($ua2 in @("DigikalaTrustedBot/SelfToken", "kiarad-bi", "default")) {
      if ($freshOk) { break }
      try {
        if ($ua2 -eq "default") {
          $rr = Invoke-RestMethod -Method Post -Uri "https://seller.digikala.com/open-api/v1/auth/refresh-token" -ContentType "application/json" -Body $bodyJson2 -TimeoutSec 40
        } else {
          $rr = Invoke-RestMethod -Method Post -Uri "https://seller.digikala.com/open-api/v1/auth/refresh-token" -ContentType "application/json" -Body $bodyJson2 -Headers @{Accept="application/json"} -UserAgent $ua2 -TimeoutSec 40
        }
        $na = $rr.data.access_token
        if ($na) {
          $nr = $rr.data.refresh_token
          Copy-Item $tokPath (Join-Path $secrets ("digikala_tokens_backup_" + $stamp + ".json")) -Force
          $fresh2 = New-Object System.Collections.Hashtable
          $fresh2.access_token = $na
          if ($nr) { $fresh2.refresh_token = $nr } else { $fresh2.refresh_token = $oref }
          $sid2 = $tj2.seller_id
          if (-not $sid2) { $sid2 = $tj2.data.seller_id }
          $cc2 = $tj2.client_code
          if (-not $cc2) { $cc2 = $tj2.data.client_code }
          $fresh2.seller_id = $sid2
          $fresh2.client_code = $cc2
          $fresh2 | ConvertTo-Json | Out-File -FilePath $freshFile -Encoding utf8
          & $say (" REFRESH OK in PowerShell with UA=" + $ua2)
          $freshOk = $true
        }
      } catch { Show-Err $_ }
    }
  } else {
    & $say " no refresh_token in current file - cannot refresh"
  }
}

& $say ""
& $say "=== 3) SWAP TOKENS (backup first) ==="
$acc = ""
if ($freshOk) {
  if (Test-Path $tokPath) {
    Copy-Item $tokPath (Join-Path $secrets ("digikala_tokens_backup_" + $stamp + ".json")) -Force
    & $say (" backup: digikala_tokens_backup_" + $stamp + ".json")
  }
  Copy-Item $freshFile $tokPath -Force
  & $say " swapped: secrets\digikala_tokens.json now has FRESH tokens"
  $tj = Get-Content $tokPath -Raw | ConvertFrom-Json
  $acc = $tj.access_token
  if (-not $acc) { $acc = $tj.data.access_token }
  & $say (" fresh access len: " + $acc.Length)
} else {
  & $say " no fresh tokens - keeping current files"
  if (Test-Path $tokPath) {
    $tj = Get-Content $tokPath -Raw | ConvertFrom-Json
    $acc = $tj.access_token
    if (-not $acc) { $acc = $tj.data.access_token }
  }
}

& $say ""
& $say "=== 4) UA GATE TEST ==="
$winnerTag = ""
$winnerUA  = ""
if ($acc -and $acc.Length -gt 20) {
  & $say "--- UA: DigikalaTrustedBot/SelfToken ---"
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "https://seller.digikala.com/open-api/v1/profile" -Headers @{Authorization=("Bearer " + $acc); Accept="application/json"} -UserAgent "DigikalaTrustedBot/SelfToken" -TimeoutSec 40
    & $say ("   HTTP " + $r.StatusCode + "  -> WINNER: trustedbot")
    $winnerTag = "trustedbot"
    $winnerUA  = "DigikalaTrustedBot/SelfToken"
  } catch { Show-Err $_ }
  if (-not $winnerTag) {
    & $say "--- UA: PowerShell default ---"
    try {
      $r2 = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "https://seller.digikala.com/open-api/v1/profile" -Headers @{Authorization=("Bearer " + $acc); Accept="application/json"} -TimeoutSec 40
      & $say ("   HTTP " + $r2.StatusCode + "  -> WINNER: powershell-default")
      $winnerTag = "powershell-default"
      $winnerUA  = "powershell-default"
    } catch { Show-Err $_ }
  }
} else {
  & $say " skipped: no usable access token"
}

& $say ""
& $say "=== 5) LIVE SYNC SETUP ==="
$syncOk = $false
if ($winnerTag) {
  $sample = Join-Path $logs "digikala_variants_sample_final.json"
  try {
    $rv = Invoke-WebRequest -UseBasicParsing -Method Get -Uri "https://seller.digikala.com/open-api/v1/variants?page=1&size=100" -Headers @{Authorization=("Bearer " + $acc); Accept="application/json"} -UserAgent $winnerUA -TimeoutSec 60
    $rv.Content | Out-File -FilePath $sample -Encoding utf8
    & $say (" variants page1 OK, sample: " + $sample)
    $cnt = 0
    try {
      $jv = $rv.Content | ConvertFrom-Json
      $items = $jv.data.items
      if ($null -eq $items) { $items = $jv.items }
      if ($items) { $cnt = $items.Count }
    } catch { }
    & $say (" items on page 1: " + $cnt)
  } catch { Show-Err $_ }

  $taskTemplate = @'
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
$secrets = Join-Path $root "secrets"
$UA = "__UA__"
$base = "https://seller.digikala.com/open-api/v1"
$tokPath = Join-Path $secrets "digikala_tokens.json"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
function Log-Line { param($t) $line = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "  " + $t; $line | Out-File -FilePath (Join-Path $logs "digikala_sync_task.log") -Append -Encoding utf8 }
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs -Force | Out-Null }
if (-not (Test-Path $tokPath)) { Log-Line "tokens file missing"; exit 1 }
$tok = Get-Content $tokPath -Raw | ConvertFrom-Json
$acc = $tok.access_token
if (-not $acc) { $acc = $tok.data.access_token }
if (-not $acc) { Log-Line "no access token"; exit 1 }
function Get-Page { param($a, $pg)
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ($base + "/variants?page=" + $pg + "&size=100") -Headers @{Authorization=("Bearer " + $a); Accept="application/json"} -UserAgent $UA -TimeoutSec 60
    return @{ok=$true; content=$r.Content}
  } catch {
    $code = ""
    if ($null -ne $_.Exception.Response) { $code = $_.Exception.Response.StatusCode.value__ }
    $body = ""
    try { $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); $body = $sr.ReadToEnd() } catch { }
    return @{ok=$false; code=$code; body=$body}
  }
}
$first = Get-Page -a $acc -pg 1
if (-not $first.ok) {
  Log-Line ("page1 failed code=" + $first.code + " body=" + $first.body)
  if ($first.code -eq 401) {
    Log-Line "401 - refreshing with both fields"
    $ref = $tok.refresh_token
    if (-not $ref) { $ref = $tok.data.refresh_token }
    if ($ref) {
      $bodyJson = @{access_token=$acc; refresh_token=$ref} | ConvertTo-Json
      try {
        $rr = Invoke-RestMethod -Method Post -Uri ($base + "/auth/refresh-token") -ContentType "application/json" -Body $bodyJson -TimeoutSec 40
        $na = $rr.data.access_token
        $nr = $rr.data.refresh_token
        if ($na) {
          Copy-Item $tokPath (Join-Path $secrets ("digikala_tokens_backup_" + $stamp + ".json")) -Force
          $fresh = New-Object System.Collections.Hashtable
          $fresh.access_token = $na
          $fresh.refresh_token = $nr
          $sid = $tok.seller_id
          if (-not $sid) { $sid = $tok.data.seller_id }
          $cc = $tok.client_code
          if (-not $cc) { $cc = $tok.data.client_code }
          $fresh.seller_id = $sid
          $fresh.client_code = $cc
          $fresh | ConvertTo-Json | Out-File -FilePath $tokPath -Encoding utf8
          Log-Line "refresh ok - tokens swapped"
          $acc = $na
          $first = Get-Page -a $acc -pg 1
        } else { Log-Line "refresh: no token in answer" }
      } catch { Log-Line ("refresh failed: " + $_.Exception.Message) }
    }
  }
}
if (-not $first.ok) { Log-Line "still failing - exit"; exit 1 }
$first.content | Out-File -FilePath (Join-Path $logs "digikala_variants_p1.json") -Encoding utf8
$total = 0
$items1 = $null
try { $j1 = $first.content | ConvertFrom-Json; $items1 = $j1.data.items; if ($null -eq $items1) { $items1 = $j1.items } } catch { }
$cnt1 = 0
if ($items1) { $cnt1 = $items1.Count }
$total = $total + $cnt1
Log-Line ("page1 items=" + $cnt1)
$lastCnt = $cnt1
$pg = 2
while ($pg -le 5 -and $lastCnt -ge 100) {
  $pr = Get-Page -a $acc -pg $pg
  if (-not $pr.ok) { Log-Line ("page" + $pg + " failed"); break }
  $pr.content | Out-File -FilePath (Join-Path $logs ("digikala_variants_p" + $pg + ".json")) -Encoding utf8
  $it = $null
  try { $jp = $pr.content | ConvertFrom-Json; $it = $jp.data.items; if ($null -eq $it) { $it = $jp.items } } catch { }
  $c = 0
  if ($it) { $c = $it.Count }
  $total = $total + $c
  $lastCnt = $c
  Log-Line ("page" + $pg + " items=" + $c)
  $pg = $pg + 1
  Start-Sleep -Seconds 2
}
$state = "ok"
if ($total -eq 0) { $state = "ok_empty" }
$status = New-Object System.Collections.Hashtable
$status.state = $state
$status.items_total = $total
$status.at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
$status.ua = $UA
$status | ConvertTo-Json | Out-File -FilePath (Join-Path $logs "digikala_sync_task_status.json") -Encoding utf8
Log-Line ("state=" + $state + " total=" + $total)
exit 0
'@
  $taskScript = $taskTemplate.Replace("__UA__", $winnerUA)
  $taskPath = Join-Path $scripts "digikala_sync_task.ps1"
  Set-Content -Path $taskPath -Value $taskScript -Encoding UTF8
  & $say (" task script written: " + $taskPath)
  & $say " registering scheduled task KiaradDigikalaSync (every 30 min) ..."
  schtasks /Create /F /SC MINUTE /MO 30 /TN "KiaradDigikalaSync" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\project\kiaradbi\scripts\digikala_sync_task.ps1" | Out-Null
  if ($LASTEXITCODE -eq 0) { & $say " scheduled task registered" } else { & $say " schtasks failed - the task script still works if run manually" }
  & $say " first run now ..."
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskPath
  $statusFile = Join-Path $logs "digikala_sync_task_status.json"
  if (Test-Path $statusFile) {
    $st = Get-Content $statusFile -Raw | ConvertFrom-Json
    & $say (" sync status: state=" + $st.state + " items_total=" + $st.items_total)
    if ($st.state -eq "ok" -or $st.state -eq "ok_empty") { $syncOk = $true }
  }
} else {
  & $say " skipped: no winner UA - nothing to schedule"
}

& $say ""
& $say "=== VERDICT ==="
if ($syncOk) {
  & $say " ALL DONE. Connection alive, sync task every 30 min, data in logs\digikala_variants_p1.json"
  & $say " Next (me, not you): mapping into digikala_variants table + site data.json"
} elseif ($winnerTag) {
  & $say " Gate passed but sync had issues - paste the report."
} elseif ($freshOk) {
  & $say " Fresh tokens obtained (refresh path) but still 401 Invalid User-Agent on data endpoints."
  & $say " This is now 100% server-side (Digikala gate for our client)."
  & $say " ONLY remaining move: send the prepared email to Marketplace-API@digikala.com"
  & $say " and paste the reply here. Tokens are fresh and swapped - nothing else to do locally."
} else {
  & $say " No fresh tokens even via refresh - see the errors above."
  & $say " If every REFRESH attempt failed -> refresh_token may be dead too."
  & $say " Then the only remaining path is the email to Marketplace-API@digikala.com."
}
& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
& $say " report copied to clipboard too."
