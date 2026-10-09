$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force -Path runtime, models, logs | Out-Null
if (-not (Test-Path 'runtime/llama/llama-server.exe')) {
    curl.exe -fL --retry 3 -o 'runtime/llama-b11524.zip' 'https://github.com/ggml-org/llama.cpp/releases/download/b11524/llama-b11524-bin-win-vulkan-x64.zip'
    if ($LASTEXITCODE -ne 0) { throw 'llama.cpp download failed' }
    Expand-Archive -LiteralPath 'runtime/llama-b11524.zip' -DestinationPath 'runtime/llama' -Force
}
$manifest = Get-Content -LiteralPath 'model_manifest.json' -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($model in $manifest) {
    $target = Join-Path 'models' $model.file
    if (-not (Test-Path -LiteralPath $target)) {
        $url = 'https://huggingface.co/' + $model.repo + '/resolve/' + $model.revision + '/' + $model.file
        curl.exe -fL --retry 3 -C - -o "$target.part" $url
        if ($LASTEXITCODE -ne 0) { throw ('Model download failed: ' + $model.file) }
        $hash = (Get-FileHash -LiteralPath "$target.part" -Algorithm SHA256).Hash.ToLower()
        if ($hash -ne $model.sha256) { throw ('Checksum mismatch: ' + $model.file) }
        Move-Item -LiteralPath "$target.part" -Destination $target
    }
    $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $model.sha256) { throw ('Checksum mismatch: ' + $model.file) }
}
Write-Host 'Ready: python run_local.py --backend local-4b'
