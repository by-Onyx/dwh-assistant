[CmdletBinding()]
param([string]$AssetsDir)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $AssetsDir) { $AssetsDir = Join-Path $ProjectRoot 'var' }
$AssetsDir = [IO.Path]::GetFullPath($AssetsDir)
$RuntimeDir = Join-Path $AssetsDir 'runtime'
$ModelsDir = Join-Path $AssetsDir 'models'
New-Item -ItemType Directory -Force -Path $RuntimeDir, $ModelsDir | Out-Null
$Server = Join-Path $RuntimeDir 'llama\llama-server.exe'
if (-not (Test-Path -LiteralPath $Server)) {
    $Archive = Join-Path $RuntimeDir 'llama-b11524.zip'
    curl.exe -fL --retry 3 -o $Archive 'https://github.com/ggml-org/llama.cpp/releases/download/b11524/llama-b11524-bin-win-vulkan-x64.zip'
    if ($LASTEXITCODE -ne 0) { throw 'llama.cpp download failed' }
    Expand-Archive -LiteralPath $Archive -DestinationPath (Join-Path $RuntimeDir 'llama') -Force
}
$ManifestPath = Join-Path $ProjectRoot 'configs\model_manifest.json'
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($model in $Manifest) {
    $Target = [IO.Path]::GetFullPath((Join-Path $ModelsDir $model.file))
    if (-not $Target.StartsWith($ModelsDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Model path escapes models directory' }
    if (-not (Test-Path -LiteralPath $Target)) {
        $Url = 'https://huggingface.co/' + $model.repo + '/resolve/' + $model.revision + '/' + $model.file
        curl.exe -fL --retry 3 -C - -o "$Target.part" $Url
        if ($LASTEXITCODE -ne 0) { throw ('Model download failed: ' + $model.file) }
        $Hash = (Get-FileHash -LiteralPath "$Target.part" -Algorithm SHA256).Hash.ToLower()
        if ($Hash -ne $model.sha256) { throw ('Checksum mismatch: ' + $model.file) }
        Move-Item -LiteralPath "$Target.part" -Destination $Target
    }
    $Hash = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLower()
    if ($Hash -ne $model.sha256) { throw ('Checksum mismatch: ' + $model.file) }
}
Write-Host 'Ready: .\.venv\Scripts\python.exe labs/01_dwh_agent/run_local.py --backend local-4b'
Write-Host ('Assets: ' + $AssetsDir)
