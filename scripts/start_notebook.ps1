[CmdletBinding()]
param([string]$AssetsDir)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Create .venv and install dependencies as described in README.md' }
if ($AssetsDir) {
    $env:DWH_ASSETS_DIR = (Resolve-Path -LiteralPath $AssetsDir).Path
}
Set-Location -LiteralPath $ProjectRoot
& $Python -m notebook (Join-Path $ProjectRoot 'labs\02_fact_memory\notebooks\02_fact_memory.ipynb')
exit $LASTEXITCODE
