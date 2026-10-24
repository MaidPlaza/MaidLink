$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root "build\venv_build"
$dist = Join-Path $root "build\dist"
$work = Join-Path $root "build\work"

Write-Host "[build] repo root: $root"

if (-not (Test-Path $venv)) {
    Write-Host "[build] creating clean venv -> $venv"
    py -3 -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r (Join-Path $root "requirements.txt")
& $py -m pip install pyinstaller

Push-Location $root
try {
    & $py -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $root "build\backend.spec")
} finally {
    Pop-Location
}

$exeDir = Join-Path $dist "backend"
if (($LASTEXITCODE -ne 0) -or -not (Test-Path (Join-Path $exeDir "backend.exe"))) {
    throw "[build] PyInstaller failed: no backend.exe produced. See log above."
}

$assets = @(
    "content",
    "image_gen\workflows", "image_gen\embeddings", "image_gen\comfy_guard.py",
    "drawing\danbooru_tags"
)
foreach ($a in $assets) {
    $src = Join-Path $root $a
    if (Test-Path $src) {
        $dst = Join-Path $exeDir $a
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -Recurse -Force $src $dst
        Write-Host "[build] asset: $a"
    } else {
        Write-Host "[build] SKIP (missing): $a"
    }
}

$cudaRuntime = '^(cudart64|cublas64|cublasLt64)_\d+\.dll$'
$llSrc = Join-Path $root "llama-server"
if (Test-Path $llSrc) {
    $llDst = Join-Path $exeDir "llama-server"
    New-Item -ItemType Directory -Force -Path $llDst | Out-Null
    Get-ChildItem $llSrc -File | Where-Object {
        ($_.Name -eq "llama-server.exe") -or
        ($_.Extension -eq ".jinja") -or (
            $_.Extension -eq ".dll" -and
            $_.Name -notmatch $cudaRuntime -and (
                $_.Name -notmatch '^llama-.*-impl\.dll$' -or
                $_.Name -eq "llama-server-impl.dll"
            )
        )
    } | ForEach-Object { Copy-Item $_.FullName $llDst -Force }
    Write-Host "[build] llama-server (cleaned: server.exe + own DLLs + *.jinja; no CUDA runtime, *.zip, tool impl-DLLs)"
} else {
    Write-Host "[build] SKIP (missing): llama-server"
}

Write-Host ""
Write-Host "[build] DONE -> $exeDir\backend.exe"
Write-Host "[build] Test it: set the env vars MAIDLINK_PORT=8001 and MAIDLINK_API_TOKEN=<16+ chars>, run backend.exe;"
Write-Host "[build]   every request needs the header X-MaidLink-Token (api/local_guard.py)"
