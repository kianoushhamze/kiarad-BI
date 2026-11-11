param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot), [switch]$SkipImageExport)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$package = Join-Path $root "private_exports\release-package-20261102"
New-Item -ItemType Directory -Path $package -Force | Out-Null
foreach ($folder in @("scripts", "migrations", "docs")) {
  New-Item -ItemType Directory -Path (Join-Path $package $folder) -Force | Out-Null
}
foreach ($file in @("docker-compose.yml", "deploy.ps1", ".env.example")) {
  Copy-Item -LiteralPath (Join-Path $root $file) -Destination (Join-Path $package $file)
}
foreach ($file in @("backup_release.ps1", "postgres_container.ps1", "restore_release_backup.ps1", "restore_release_media.ps1", "verify_release_package.ps1", "release_health.ps1", "run_migrations.py")) {
  Copy-Item -LiteralPath (Join-Path $root "scripts\$file") -Destination (Join-Path $package "scripts\$file")
}
Get-ChildItem -LiteralPath (Join-Path $root "migrations") -File | Copy-Item -Destination (Join-Path $package "migrations")
Copy-Item -LiteralPath (Join-Path $root "docs\Server_Deployment_Runbook_20261101.md") -Destination (Join-Path $package "docs")
foreach ($document in @('Independent_Completion_20261102.md','Kiarad_Handoff_Master_20261101.md')) {
  Copy-Item -LiteralPath (Join-Path $root "docs\$document") -Destination (Join-Path $package 'docs')
}
if (-not $SkipImageExport) {
  docker save -o (Join-Path $package "postgres-image.tar") postgres:16
  if ($LASTEXITCODE -ne 0) { throw "postgres_image_export_failed" }
}
$backup = Get-ChildItem -LiteralPath (Join-Path $root "private_exports\release-backups") -Directory |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $backup) { throw "backup_missing" }
$backupTarget = Join-Path $package "backup"
New-Item -ItemType Directory -Path $backupTarget -Force | Out-Null
Get-ChildItem -LiteralPath $backup.FullName -File | Copy-Item -Destination $backupTarget
$hashes = Get-ChildItem -LiteralPath $package -File -Recurse |
  Where-Object Name -ne "checksums.json" | ForEach-Object {
    @{ path = $_.FullName.Substring($package.Length + 1); bytes = $_.Length;
       sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
  }
$hashes | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $package "checksums.json") -Encoding utf8
[ordered]@{ package=$package; files=$hashes.Count; contains_env=$false } | ConvertTo-Json -Compress
