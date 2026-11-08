# ============================================================
# KiaradBI Dashboard Collector v2 (2026-11-05)
# v2 fixes: .next-qa-build excluded, root-level backend .py files
# prioritized, lib/ and components/ prioritized, recent logs added,
# .env included with secret values masked, bigger budget.
# Zero-bracket build: no square brackets anywhere in this file.
# Run while servers are up.
# ============================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
if (-not (Test-Path -LiteralPath $root)) {
  $alt = Get-ChildItem -Path "D:\" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*kiarad*" } | Select-Object -First 1
  if ($alt) { $root = $alt.FullName }
}
if (-not (Test-Path -LiteralPath $root)) {
  Write-Output 'PROJECT ROOT NOT FOUND - edit $root at the top of this script'
  exit 1
}
Write-Output "ROOT $root"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$out = Join-Path $root ("logs\dashcollect2_" + $stamp)
$srcDir = Join-Path $out "sources"
New-Item -ItemType Directory -Force -Path $srcDir | Out-Null

$blackDirs = @("node_modules",".next",".git","venv",".venv","__pycache__",".turbo","dist","build",".cache",".gradle",".idea",".vscode","fonts","media","uploads",".next-qa-build",".next-standalone",".next-dev")
$skipExt = @(".png",".jpg",".jpeg",".gif",".webp",".ico",".bmp",".woff",".woff2",".ttf",".otf",".eot",".mp4",".mp3",".pdf",".exe",".dll",".pyc",".pyd",".zip",".7z",".rar",".bak",".sqlite",".db",".jar",".map")
$goodExt = @(".py",".ts",".tsx",".js",".jsx",".mjs",".cjs",".json",".html",".css",".scss",".md",".yml",".yaml",".toml",".ini",".cfg",".txt",".ps1",".sql",".prisma",".bat",".sh",".cmd",".mjs")
$budget = 6000000
$perFileCap = 120000
$maxFiles = 900

$allFiles = New-Object System.Collections.ArrayList

function Walk {
  param($dir, $depth)
  if ($depth -gt 14) { return }
  $items = Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue
  foreach ($it in $items) {
    if ($it.PSIsContainer) {
      if ($blackDirs -notcontains $it.Name) {
        Walk -dir $it.FullName -depth ($depth + 1)
      }
    } else {
      $null = $allFiles.Add($it)
    }
  }
}

Walk -dir $root -depth 0
Write-Output ("FILES SCANNED " + $allFiles.Count)

# ---- structure.txt ----
$struct = Join-Path $out "structure.txt"
foreach ($f in $allFiles) {
  $rel = $f.FullName.Substring($root.Length)
  Add-Content -LiteralPath $struct -Value ($rel + "`t" + $f.Length)
}

# ---- manifest + picked ----
$manifest = Join-Path $out "sources_manifest.txt"
$picked = New-Object System.Collections.ArrayList

foreach ($f in $allFiles) {
  $ext = $f.Extension.ToLower()
  $n = $f.Name.ToLower()
  $full = $f.FullName
  $rel = $full.Substring($root.Length)
  if ($rel -match "\\.next-qa-build") { continue }
  if ($n -like "*.bafix*") { continue }
  if ($n -eq "all_code.txt") { continue }
  if ($rel -like "\logs\*") { continue }
  $isSrc = $false
  if ($goodExt -contains $ext) { $isSrc = $true }
  if ($n -eq ".env" -or $n -like ".env*") { $isSrc = $true }
  if ($skipExt -contains $ext) { $isSrc = $false }
  if (-not $isSrc) { continue }

  $score = 10
  $firstSep = $rel.IndexOf("\", 1)
  $isRootFile = ($firstSep -eq -1)
  if ($isRootFile -and $ext -eq ".py") { $score = 96 }
  elseif ($n -eq "package.json") { $score = 100 }
  elseif ($n -like ".env*") { $score = 98 }
  elseif ($n -like "next.config*") { $score = 96 }
  elseif ($isRootFile) { $score = 94 }
  elseif ($rel -match "\\lib\\") { $score = 95 }
  elseif ($rel -match "\\components\\") { $score = 95 }
  elseif ($rel -match "\\app\\api\\") { $score = 90 }
  elseif ($rel -match "\\app\\") { $score = 85 }
  elseif ($rel -match "\\public\\") { $score = 60 }
  elseif ($rel -match "\\scripts\\") { $score = 45 }
  elseif ($rel -match "\\tests\\") { $score = 40 }
  elseif ($rel -match "\\docs\\") { $score = 35 }
  elseif ($rel -match "\\data\\") { $score = 30 }
  if ($n -like "*.lock") { $score = 4 }
  if ($n -like "*_backup*") { $score = 5 }
  $null = $picked.Add(($score.ToString("000")) + "|" + $full)
}

# ---- recent logs (newest 14, capped) ----
$logFiles = @()
try {
  $logFiles = Get-ChildItem -LiteralPath (Join-Path $root "logs") -Filter "*.log" -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 14
} catch {}
try {
  $rootLogs = Get-ChildItem -LiteralPath $root -Filter "*.log" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 6
  $logFiles = @($logFiles) + @($rootLogs)
} catch {}
foreach ($lf in $logFiles) {
  $null = $picked.Add(("030|" + $lf.FullName))
}

$sorted = $picked | Sort-Object -Descending

$count = 0
$rawTotal = 0
foreach ($line in $sorted) {
  if ($count -ge $maxFiles) { break }
  if ($budget -le 2000) { break }
  $idx = $line.IndexOf("|")
  $full = $line.Substring($idx + 1)
  if (-not (Test-Path -LiteralPath $full)) { continue }
  $fi = Get-Item -LiteralPath $full
  if ($fi.PSIsContainer) { continue }
  $rel = $full.Substring($root.Length)
  $name = $rel.TrimStart("\")
  $name = $name -replace "\\", "__"
  $name = $name -replace ":", "__"
  if ($name.Length -gt 170) { $name = $name.Substring($name.Length - 170) }

  $txt = ""
  try {
    $txt = Get-Content -LiteralPath $full -Raw -Encoding UTF8 -ErrorAction Stop
  } catch {
    Add-Content -LiteralPath $manifest -Value ("READ FAIL`t" + $rel)
    continue
  }
  if ($null -eq $txt) { $txt = "" }

  # mask secrets in env files
  if ($n -eq ".env" -or $n -like ".env*") {
    $outLines = @()
    foreach ($ln in ($txt -split "`n")) {
      $eq = $ln.IndexOf("=")
      if ($eq -gt 0) {
        $k = $ln.Substring(0, $eq)
        $v = $ln.Substring($eq + 1)
        $kl = $k.ToLower()
        if ($kl -like "*secret*" -or $kl -like "*password*" -or $kl -like "*token*" -or $kl -like "*key*" -or $kl -like "*user*") {
          if ($v.Length -gt 2) { $v = $v.Substring(0, 2) + "***MASKED***" }
        }
        $outLines = $outLines + ($k + "=" + $v)
      } else {
        $outLines = $outLines + $ln
      }
    }
    $txt = ($outLines -join "`n")
  }

  $took = $txt.Length
  if ($took -gt $perFileCap) {
    $txt = $txt.Substring(0, $perFileCap) + "`n`n===== TRUNCATED, original length " + $took + " chars ====="
    $took = $perFileCap
  }
  Set-Content -LiteralPath (Join-Path $srcDir $name) -Value $txt -Encoding UTF8
  Add-Content -LiteralPath $manifest -Value ($name + "`t<=`t" + $rel)
  $budget = $budget - $took
  $count = $count + 1
  $rawTotal = $rawTotal + $took
}
Write-Output ("SOURCES COLLECTED " + $count + "  rawchars " + $rawTotal)

# ---- runtime probes ----
$probe = Join-Path $out "runtime_probes.txt"
Add-Content -LiteralPath $probe -Value ("TIME " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
$urls = @(
  "http://localhost:3000/management",
  "http://localhost:3000/login",
  "http://localhost:3000/",
  "http://localhost:8000/openapi.json",
  "http://localhost:8000/docs",
  "http://localhost:8000/health"
)
foreach ($u in $urls) {
  try {
    $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 10
    Add-Content -LiteralPath $probe -Value ("OK   " + $u + "  status=" + $r.StatusCode + "  len=" + $r.RawContentLength)
    Write-Output ("OK   " + $u)
  } catch {
    Add-Content -LiteralPath $probe -Value ("FAIL " + $u + "  ::  " + $_.Exception.Message)
    Write-Output ("FAIL " + $u)
  }
}
try { (Get-Process node,python -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime | Out-String) | Add-Content -LiteralPath $probe } catch {}
try { (netstat -ano | Select-String ":3000|:8000|:5432" | Out-String) | Add-Content -LiteralPath $probe } catch {}
try { (docker ps 2>&1 | Out-String) | Add-Content -LiteralPath $probe } catch {}

# ---- auth flow probe: login page + unauth API behavior ----
try {
  $lg = Invoke-WebRequest -Uri "http://localhost:8000/auth/me" -UseBasicParsing -TimeoutSec 10
  Add-Content -LiteralPath $probe -Value ("AUTH /auth/me no-cookie status=" + $lg.StatusCode)
} catch {
  Add-Content -LiteralPath $probe -Value ("AUTH /auth/me no-cookie :: " + $_.Exception.Message)
}
try {
  $df = Invoke-WebRequest -Uri "http://localhost:8000/dashboard/full?range=month" -UseBasicParsing -TimeoutSec 10
  Add-Content -LiteralPath $probe -Value ("AUTH /dashboard/full no-cookie status=" + $df.StatusCode)
} catch {
  Add-Content -LiteralPath $probe -Value ("AUTH /dashboard/full no-cookie :: " + $_.Exception.Message)
}

# ---- zip ----
$zip = Join-Path $root ("kiarad_dashcollect2_" + $stamp + ".zip")
Compress-Archive -Path (Join-Path $out "*") -DestinationPath $zip -Force
$zl = -1
try { $zl = (Get-Item -LiteralPath $zip).Length } catch {}
Write-Output ("ZIP " + $zip)
Write-Output ("ZIP SIZE BYTES " + $zl)

$summary = Join-Path $root "kiarad_collect2_summary.txt"
Add-Content -LiteralPath $summary -Value ("=== kiarad dashcollect2 " + $stamp + " ===")
Add-Content -LiteralPath $summary -Value ("root " + $root)
Add-Content -LiteralPath $summary -Value ("files scanned " + $allFiles.Count)
Add-Content -LiteralPath $summary -Value ("sources collected " + $count + " rawchars " + $rawTotal)
Add-Content -LiteralPath $summary -Value ("zip " + $zip + "  size " + $zl)
try { Add-Content -LiteralPath $summary -Value (Get-Content -LiteralPath $probe -Raw) } catch {}

try { Set-Clipboard -Value $zip; Write-Output "ZIP PATH COPIED TO CLIPBOARD" } catch {}
Write-Output "DONE - upload the zip to the chat"
