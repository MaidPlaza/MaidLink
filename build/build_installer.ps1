$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "[installer] 1/4 building UI (vite)..."
& npm --prefix (Join-Path $root "ui") run build
if ($LASTEXITCODE -ne 0) { throw "UI build failed" }

Write-Host "[installer] 2/4 building backend.exe..."
& (Join-Path $root "build\build_backend.ps1")
$exeDir = Join-Path $root "build\dist\backend"
if (-not (Test-Path (Join-Path $exeDir "backend.exe"))) { throw "backend build failed (no backend.exe)" }

Write-Host "[installer] 3/4 cleaning dev data (install dir ships assets only)..."
foreach ($d in @("characters", "data", "runtime_cache", "addons", "logs")) {
    $p = Join-Path $exeDir $d
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
$cb = Join-Path $exeDir "characters_baseline"
if (Test-Path $cb) { Remove-Item -Recurse -Force $cb }

Write-Host "[installer] license texts -> build\dist\licenses (installed as <install>\licenses)..."
& (Join-Path $root "build\venv_build\Scripts\python.exe") (Join-Path $root "build\collect_licenses.py")
if ($LASTEXITCODE -ne 0) { throw "license collection failed" }

Write-Host "[installer] 4/4 electron-builder (NSIS)..."
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"

$wcsCache = Join-Path $env:LOCALAPPDATA "electron-builder\Cache\winCodeSign"
$wcsDir = Join-Path $wcsCache "winCodeSign-2.6.0"
if (-not (Test-Path (Join-Path $wcsDir "windows-10"))) {
    Write-Host "[installer] seeding winCodeSign cache (excluding darwin symlinks)..."
    New-Item -ItemType Directory -Force -Path $wcsCache | Out-Null
    $wcsArc = Join-Path $wcsCache "winCodeSign-2.6.0.7z"
    if (-not (Test-Path $wcsArc)) {
        Invoke-WebRequest -UseBasicParsing -OutFile $wcsArc `
            -Uri "https://github.com/electron-userland/electron-builder-binaries/releases/download/winCodeSign-2.6.0/winCodeSign-2.6.0.7z"
    }
    & (Join-Path $root "node_modules\7zip-bin\win\x64\7za.exe") x $wcsArc "-o$wcsDir" "-xr!darwin" -y | Out-Null
    Write-Host "[installer] winCodeSign cache seeded"
}

$pyExe = Join-Path $root "build\venv_build\Scripts\python.exe"
if (Test-Path $pyExe) {
    & $pyExe (Join-Path $root "build\patch_installer_strings.py")
} else {
    Write-Host "[installer] WARN: venv python не найден, строки установщика не пропатчены"
}

Push-Location $root
try {
    & npx electron-builder --win nsis
    if ($LASTEXITCODE -ne 0) { throw "electron-builder failed" }
} finally {
    Pop-Location
}
Write-Host "[installer] DONE -> release/"
