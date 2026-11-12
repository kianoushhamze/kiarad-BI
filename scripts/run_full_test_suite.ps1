param([string]$ProjectRoot = "D:\project\kiaradbi")

# "Continue": python's stderr (warnings) must not abort the run; failures are
# detected explicitly through $LASTEXITCODE below.
$ErrorActionPreference = "Continue"
$root = (Resolve-Path -LiteralPath $ProjectRoot).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "python_runtime_missing" }
Set-Location -LiteralPath $root

& $python -m unittest discover -s tests -q
if ($LASTEXITCODE -ne 0) { throw "default_test_suite_failed" }

$groups = @(
  @{ File = "test_attendance_workflow.py"; Flag = "KIARAD_TEST_ATTENDANCE_DB" },
  @{ File = "test_base_proposals.py"; Flag = "KIARAD_TEST_BASE_PROPOSALS_DB" },
  @{ File = "test_base_readiness.py"; Flag = "KIARAD_TEST_BASE_READINESS_DB" },
  @{ File = "test_base_registry.py"; Flag = "KIARAD_TEST_BASE_REGISTRY_DB" },
  @{ File = "test_base_route_workflow.py"; Flag = "KIARAD_TEST_BASE_ROUTE_DB" },
  @{ File = "test_data_entry.py"; Flag = "KIARAD_TEST_TREASURY_DB" },
  @{ File = "test_field_day_workflow.py"; Flag = "KIARAD_TEST_PAYROLL_DB" },
  @{ File = "test_field_intelligence.py"; Flag = "KIARAD_TEST_TREASURY_DB" },
  @{ File = "test_holoo_operational_sync.py"; Flag = "KIARAD_TEST_TREASURY_DB" },
  @{ File = "test_integration_schema_upgrade.py"; Flag = "KIARAD_TEST_INTEGRATION_DB" },
  @{ File = "test_payroll_service.py"; Flag = "KIARAD_TEST_PAYROLL_DB" },
  @{ File = "test_personnel_access_e2e.py"; Flag = "KIARAD_TEST_PERSONNEL_E2E_DB" },
  @{ File = "test_personnel_session_safety.py"; Flag = "KIARAD_TEST_PERSONNEL_DB" },
  @{ File = "test_proforma_ownership.py"; Flag = "KIARAD_TEST_PROFORMA_OWNERSHIP_DB" },
  @{ File = "test_target_schema.py"; Flag = "KIARAD_TEST_TARGET_SCHEMA_DB" },
  @{ File = "test_task_workflow.py"; Flag = "KIARAD_TEST_TASK_WORKFLOW_DB" },
  @{ File = "test_treasury_excel.py"; Flag = "KIARAD_TEST_TREASURY_DB" },
  @{ File = "test_treasury_strategy.py"; Flag = "KIARAD_TEST_TREASURY_DB" },
  @{ File = "test_visit_checkin_workflow.py"; Flag = "KIARAD_TEST_VISIT_WORKFLOW_DB" },
  @{ File = "test_visit_coverage.py"; Flag = "KIARAD_TEST_VISIT_COVERAGE_DB" },
  @{ File = "test_voice_report_workflow.py"; Flag = "KIARAD_TEST_VOICE_WORKFLOW_DB" },
  @{ File = "test_storefront_orders.py"; Flag = "KIARAD_TEST_STOREFRONT_DB" },
  @{ File = "test_agent_tracking_db.py"; Flag = "KIARAD_TEST_AGENT_DB" },
  @{ File = "test_site_cms_regressions.py"; Flag = "KIARAD_TEST_CMS_DB" }
)

$originalPgOptions = $env:PGOPTIONS
try {
  $env:PGOPTIONS = "-c search_path=pg_temp -c statement_timeout=30000 -c lock_timeout=5000"
  foreach ($group in $groups) {
    [Environment]::SetEnvironmentVariable($group.Flag, "1", "Process")
    try {
      & $python -m unittest discover -s tests -p $group.File -q
      if ($LASTEXITCODE -ne 0) { throw ("isolated_test_group_failed:" + $group.File) }
    } finally {
      [Environment]::SetEnvironmentVariable($group.Flag, $null, "Process")
    }
  }
} finally {
  $env:PGOPTIONS = $originalPgOptions
}

[ordered]@{
  status = "passed"
  default_suite = "passed"
  isolated_database_groups = $groups.Count
  production_schema_writes = $false
} | ConvertTo-Json -Compress
