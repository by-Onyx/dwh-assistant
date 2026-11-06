[CmdletBinding()]
param([string]$AssetsDir, [ValidateSet('02', '03')][string]$Lab = '02')
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Create .venv and install dependencies as described in README.md' }
if ($AssetsDir) {
    $env:DWH_ASSETS_DIR = (Resolve-Path -LiteralPath $AssetsDir).Path
}
Set-Location -LiteralPath $ProjectRoot
$Notebook = if ($Lab -eq '03') { 'labs\03_rag\notebooks\03_rag.ipynb' } else { 'labs\02_fact_memory\notebooks\02_fact_memory.ipynb' }
& $Python -m notebook (Join-Path $ProjectRoot $Notebook)
exit $LASTEXITCODE
