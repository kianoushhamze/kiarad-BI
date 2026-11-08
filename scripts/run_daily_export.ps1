$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'D:\project\kiaradbi'
try {
    & 'D:\project\kiaradbi\.venv\Scripts\python.exe' 'D:\project\kiaradbi\daily_proforma_export.py' 2>&1 | Out-File -LiteralPath 'D:\project\kiaradbi\daily-export-run.log' -Append -Encoding utf8
    exit $LASTEXITCODE
} catch {
    ('Export failed: ' + $_.Exception.GetType().Name) | Out-File -LiteralPath 'D:\project\kiaradbi\daily-export-run.log' -Append -Encoding utf8
    exit 1
}
