# =====================================================================
#  KIARAD - MORNING CHECK v1 (2026-10-30)  -- run at the office
#  1) Holoo server reachability (192.168.1.105:8080)
#  2) close duplicate uvicorn / public_proxy processes (keeps newest)
#  3) postgres + catalog freshness (latest updated/synced timestamps)
#  4) backend 8000 / frontend 3000 health
#  Usage: paste this WHOLE block into PowerShell, press Enter.
# =====================================================================
$ErrorActionPreference = "Continue"
$root = "D:\project\kiaradbi"
$logs = Join-Path $root "logs"
foreach ($d in @($logs)) { if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null } }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path $logs ("kiarad_morning_" + $stamp + ".txt")
$lines = New-Object System.Collections.ArrayList
$say = { param($t) $null = $lines.Add($t); Write-Host $t }

& $say "====================================================="
& $say " KIARAD MORNING CHECK v1"
& $say (" time : " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
& $say "====================================================="

function Close-Dups {
  param($procs, $label)
  $k = 0
  if ($procs) {
    $groups = $procs | Group-Object -Property Name
    foreach ($g in $groups) {
      if ($g.Count -gt 1) {
        $keep = $g.Group | Sort-Object CreationDate | Select-Object -Last 1
        & $say (" " + $label + " " + $g.Name + " x" + $g.Count + " - keeping newest PID " + $keep.ProcessId)
        foreach ($p in $g.Group) {
          if ($p.ProcessId -ne $keep.ProcessId) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            & $say ("   closed PID " + $p.ProcessId)
            $k = $k + 1
          }
        }
      }
    }
  }
  return $k
}

& $say ""
& $say "=== 1) HOLOO SERVER (office network) ==="
$t = Test-NetConnection -ComputerName 192.168.1.105 -Port 8080 -WarningAction SilentlyContinue
if ("$($t.TcpTestSucceeded)" -eq "True") {
  & $say " holoo REACHABLE on 192.168.1.105:8080"
} else {
  & $say " holoo NOT reachable - are you on the office network?"
}

& $say ""
& $say "=== 2) DUPLICATE PROCESSES (keeps newest of each) ==="
$uv = Get-CimInstance Win32_Process | Where-Object { "$($_.CommandLine)" -like "*uvicorn*" }
$k1 = Close-Dups -procs $uv -label "uvicorn"
$pp = Get-CimInstance Win32_Process | Where-Object { ("$($_.CommandLine)" -like "*public_proxy*") -or ("$($_.Name)" -like "*public_proxy*") }
$k2 = Close-Dups -procs $pp -label "public_proxy"
& $say (" duplicates closed: " + ($k1 + $k2))

& $say ""
& $say "=== 3) DATABASE + CATALOG FRESHNESS ==="
$pg = ""
$cl = docker ps --format "{{.Names}}|{{.Image}}" 2>$null
foreach ($l in $cl) {
  if ($l -like "*postgres*") { $pg = ($l -split "\|") | Select-Object -First 1 }
}
if ($pg -eq "") {
  & $say " postgres container NOT running - start Docker Desktop"
} else {
  $db = "postgres"
  $alt = ""
  $dbs = docker exec $pg psql -U postgres -tAc "SELECT datname FROM pg_database WHERE datistemplate = false" 2>$null
  foreach ($d in $dbs) {
    $dn = "$d".Trim()
    if ($dn -like "*kiarad*") { $db = $dn }
    elseif ($dn -ne "postgres" -and $alt -eq "") { $alt = $dn }
  }
  if ($db -eq "postgres" -and $alt -ne "") { $db = $alt }
  & $say (" postgres up - db: " + $db)
  $tabs = docker exec $pg psql -U postgres -d $db -tAc "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'" 2>$null
  foreach ($tn in $tabs) {
    $tn = "$tn".Trim()
    if ($tn -eq "") { continue }
    if ($tn -like "*holoo*" -or $tn -like "*kala*" -or $tn -like "*product*" -or $tn -like "*catalog*") {
      $col = ""
      $h1 = docker exec $pg psql -U postgres -d $db -tAc ("SELECT count(*) FROM information_schema.columns WHERE table_name = '" + $tn + "' AND column_name = 'updated_at'") 2>$null
      if ("$h1".Trim() -eq "1") { $col = "updated_at" }
      else {
        $h2 = docker exec $pg psql -U postgres -d $db -tAc ("SELECT count(*) FROM information_schema.columns WHERE table_name = '" + $tn + "' AND column_name = 'synced_at'") 2>$null
        if ("$h2".Trim() -eq "1") { $col = "synced_at" }
      }
      if ($col -ne "") {
        $mx = docker exec $pg psql -U postgres -d $db -tAc ("SELECT max(" + $col + ") FROM " + $tn) 2>$null
        & $say (" " + $tn + "  latest " + $col + ": " + "$mx".Trim())
      }
    }
  }
  $dk = docker exec $pg psql -U postgres -d $db -tAc "SELECT count(*) FROM digikala_variants" 2>$null
  if ("$dk".Trim() -ne "") { & $say (" digikala_variants rows: " + "$dk".Trim() + " (simulated until the Digikala gate opens)") }
}
& $say " newest holoo-related log files:"
$hfiles = Get-ChildItem -Path $logs -Filter "*holoo*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3
if ($hfiles) {
  foreach ($f in $hfiles) { & $say ("   " + $f.Name + "   " + $f.LastWriteTime) }
} else {
  & $say "   none found"
}

& $say ""
& $say "=== 4) SERVICES ==="
try {
  $r1 = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/docs" -TimeoutSec 8
  & $say (" backend 8000: HTTP " + $r1.StatusCode)
} catch {
  & $say " backend 8000: NOT responding - start it (uvicorn)"
}
try {
  $r2 = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:3000" -TimeoutSec 8
  & $say (" frontend 3000: HTTP " + $r2.StatusCode)
} catch {
  & $say " frontend 3000: NOT responding - start it (next dev)"
}

& $say ""
& $say "=== VERDICT ==="
& $say " Morning check done. If anything shows NOT responding, a big duplicate count,"
& $say " or a catalog date older than 1 day, paste the report in the chat."
& $say ""
& $say (" report: " + $reportPath)
$lines | Out-File -FilePath $reportPath -Encoding utf8
Set-Clipboard -Value ($lines -join "`r`n") -ErrorAction SilentlyContinue
if (Test-Path $reportPath) { Start-Process notepad.exe $reportPath }
exit 0
