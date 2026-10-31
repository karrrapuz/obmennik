$ErrorActionPreference = 'Stop'
$Backend = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Backend '.venv/Scripts/python.exe'
$Script = Join-Path $PSScriptRoot 'telegram_catalog.py'
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host 'Local Python environment is missing.'
    exit 1
}
& $Python $Script login
exit $LASTEXITCODE
