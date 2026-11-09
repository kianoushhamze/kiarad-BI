param(
  [string]$ProjectRoot = $PSScriptRoot,
  [switch]$SkipBuild,
  [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location -LiteralPath $root

if (-not (Test-Path -LiteralPath (Join-Path $root ".env"))) { throw "env_file_missing" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "docker_not_found" }
docker version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "docker_engine_unavailable" }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "compose_config_invalid" }

if (-not $SkipBuild) {
  docker compose build backend frontend
  if ($LASTEXITCODE -ne 0) { throw "image_build_failed" }
}

$offlineArgs = @()
if ($SkipBuild) { $offlineArgs = @("--no-build", "--pull", "never") }
docker compose up -d @offlineArgs postgres
if ($LASTEXITCODE -ne 0) { throw "postgres_start_failed" }

$deadline = (Get-Date).AddMinutes(2)
do {
  $health = docker inspect -f "{{.State.Health.Status}}" kiarad-postgres 2>$null
  if ($health -eq "healthy") { break }
  Start-Sleep -Seconds 3
} while ((Get-Date) -lt $deadline)
if ($health -ne "healthy") { throw "postgres_health_timeout" }

# A fresh volume passes SELECT 1 but does not contain the restored application schema.
docker compose run --rm --no-deps --pull never backend python scripts/check_release_database.py
if ($LASTEXITCODE -ne 0) { throw "database_restore_required_or_unavailable" }

if (-not $SkipBackup) {
  & (Join-Path $root "scripts\backup_release.ps1") -ProjectRoot $root
  if ($LASTEXITCODE -ne 0) { throw "predeploy_backup_failed" }
}

docker compose run --rm --no-deps --pull never -v "${root}\migrations:/app/migrations:ro" -v "${root}\scripts\run_migrations.py:/app/scripts/run_migrations.py:ro" backend python scripts/run_migrations.py
if ($LASTEXITCODE -ne 0) { throw "migration_failed" }

docker compose up -d @offlineArgs backend frontend
if ($LASTEXITCODE -ne 0) { throw "application_start_failed" }

& (Join-Path $root "scripts\release_health.ps1")
if ($LASTEXITCODE -ne 0) { throw "release_health_failed" }

docker compose ps
