# ============================================================
# KiaradBI Dashboard Collector v1 (2026-11-05)
# Builds a small TEXT-ONLY diagnostic zip for chat upload.
# Excludes: node_modules, .next, .git, venv, fonts, binaries.
# Zero-bracket build: no square brackets anywhere in this file.
# Run it while both servers (3000 and 8000) are up, if possible.
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
$out = Join-Path $root ("logs\dashcollect_" + $stamp)
$srcDir = Join-Path $out "sources"
New-Item -ItemType Directory -Force -Path $srcDir | Out-Null

$blackDirs = @("node_modules",".next",".git","venv",".venv","__pycache__",".turbo","dist","build",".cache",".gradle",".idea",".vscode","fonts","media","uploads")
$skipExt = @(".png",".jpg",".jpeg",".gif",".webp",".ico",".bmp",".woff",".woff2",".ttf",".otf",".eot",".mp4",".mp3",".pdf",".exe",".dll",".pyc",".pyd",".zip",".7z",".rar",".bak",".sqlite",".db",".jar",".map")
$goodExt = @(".py",".ts",".tsx",".js",".jsx",".mjs",".cjs",".json",".html",".css",".scss",".sass",".less",".md",".yml",".yaml",".toml",".ini",".cfg",".conf",".txt",".ps1",".sql",".prisma",".bat",".sh",".cmd",".env",".gitignore",".lock",".log")

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

# ---- structure.txt : every file with its size ----
$struct = Join-Path $out "structure.txt"
foreach ($f in $allFiles) {
  $rel = $f.FullName.Substring($root.Length)
  Add-Content -LiteralPath $struct -Value ($rel + "`t" + $f.Length)
}

# ---- pick text sources, priority first, size-capped ----
$budget = 2200000
$perFileCap = 50000
$maxFiles = 350
$manifest = Join-Path $out "sources_manifest.txt"
$picked = New-Object System.Collections.ArrayList
foreach ($f in $allFiles) {
  $ext = $f.Extension.ToLower()
  $n = $f.Name.ToLower()
  $full = $f.FullName
  $rel = $full.Substring($root.Length)
  if ($rel -match "\\logs\\") { continue }
  $isSrc = $false
  if ($goodExt -contains $ext) { $isSrc = $true }
  if ($n -eq ".env" -or $n -like ".env*" -or $n -like "dockerfile*") { $isSrc = $true }
  if ($skipExt -contains $ext) { $isSrc = $false }
  if (-not $isSrc) { continue }
  $score = 10
  if ($n -eq "package.json") { $score = 100 }
  elseif ($n -like ".env*") { $score = 98 }
  elseif ($n -like "next.config*") { $score = 96 }
  elseif ($n -like "tailwind.config*") { $score = 94 }
  elseif ($n -like "tsconfig*") { $score = 92 }
  elseif ($n -like "requirements*.txt") { $score = 92 }
  elseif ($rel -match "\\api\\") { $score = 86 }
  elseif ($rel -match "\\backend\\") { $score = 86 }
  elseif ($rel -match "\\app\\") { $score = 82 }
  elseif ($rel -match "\\pages\\") { $score = 82 }
  elseif ($rel -match "\\lib\\" -or $rel -match "\\utils\\") { $score = 76 }
  elseif ($rel -match "\\components\\") { $score = 74 }
  elseif ($ext -eq ".py") { $score = 78 }
  elseif ($ext -eq ".ps1") { $score = 60 }
  if ($n -like "*.lock") { $score = 4 }
  $null = $picked.Add(($score.ToString("000")) + "|" + $full)
}
$sorted = $picked | Sort-Object -Descending

$count = 0
$rawTotal = 0
foreach ($line in $sorted) {
  if ($count -ge $maxFiles) { break }
  if ($budget -le 2000) { break }
  $idx = $line.IndexOf("|")
  $full = $line.Substring($idx + 1)
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
  "http://localhost:3000/",
  "http://localhost:8000/openapi.json",
  "http://localhost:8000/docs",
  "http://localhost:8000/health",
  "http://localhost:8000/api/health",
  "http://192.168.1.105:8080/"
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

try {
  $mg = Invoke-WebRequest -Uri "http://localhost:3000/management" -UseBasicParsing -TimeoutSec 10
  Set-Content -LiteralPath (Join-Path $out "management_page.html") -Value $mg.Content -Encoding UTF8
  Copy-Item -LiteralPath (Join-Path $out "management_page.html") -Destination (Join-Path $root "kiarad_management_page.html") -Force
} catch {
  Add-Content -LiteralPath $probe -Value ("management page not saved :: " + $_.Exception.Message)
}

try {
  $oa = Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing -TimeoutSec 10
  Set-Content -LiteralPath (Join-Path $out "openapi.json") -Value $oa.Content -Encoding UTF8
  Copy-Item -LiteralPath (Join-Path $out "openapi.json") -Destination (Join-Path $root "kiarad_openapi.json") -Force
} catch {
  Add-Content -LiteralPath $probe -Value ("openapi not saved :: " + $_.Exception.Message)
}

try { (Get-Process node,python -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime | Out-String) | Add-Content -LiteralPath $probe } catch {}
try { (netstat -ano | Select-String ":3000|:8000|:8080|:5432" | Out-String) | Add-Content -LiteralPath $probe } catch {}
try { (docker ps 2>&1 | Out-String) | Add-Content -LiteralPath $probe } catch {}

# ---- zip ----
$zip = Join-Path $root ("kiarad_dashcollect_" + $stamp + ".zip")
Compress-Archive -Path (Join-Path $out "*") -DestinationPath $zip -Force
$zl = -1
try { $zl = (Get-Item -LiteralPath $zip).Length } catch {}
Write-Output ("ZIP " + $zip)
Write-Output ("ZIP SIZE BYTES " + $zl)

# ---- summary at root (fallback if zip upload fails) ----
$summary = Join-Path $root "kiarad_collect_summary.txt"
Add-Content -LiteralPath $summary -Value ("=== kiarad dashcollect " + $stamp + " ===")
Add-Content -LiteralPath $summary -Value ("root " + $root)
Add-Content -LiteralPath $summary -Value ("files scanned " + $allFiles.Count)
Add-Content -LiteralPath $summary -Value ("sources collected " + $count + " rawchars " + $rawTotal)
Add-Content -LiteralPath $summary -Value ("zip " + $zip + "  size " + $zl)
try { Add-Content -LiteralPath $summary -Value (Get-Content -LiteralPath $probe -Raw) } catch {}

try { Set-Clipboard -Value $zip; Write-Output "ZIP PATH COPIED TO CLIPBOARD" } catch {}
Write-Output "DONE - upload the zip file to the chat"
