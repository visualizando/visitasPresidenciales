param([switch]$Download)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if ($Download) { uv run python -m pipeline.drive_sync --download }
    else { uv run python -m pipeline.drive_sync }
    if ($LASTEXITCODE -ne 0) { throw "La revisión de Drive falló (código $LASTEXITCODE)" }
} finally { Pop-Location }
