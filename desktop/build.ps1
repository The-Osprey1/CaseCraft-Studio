# One-command release build for CaseCraft Studio (Windows PowerShell 5.1+).
#   powershell -ExecutionPolicy Bypass -File desktop\build.ps1 [-Python <path>] [-SkipTests] [-SkipInstaller]
# Steps: frontend build -> fast tests -> PyInstaller -> frozen smoke test -> Inno Setup installer.
# Stops at the first failing step.
param(
    [string]$Python = "",
    [switch]$SkipTests,
    [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($name) { Write-Host ""; Write-Host "==> $name" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

if (-not $Python) {
    $candidates = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "py")
    foreach ($c in $candidates) { if (Get-Command $c -ErrorAction SilentlyContinue) { $Python = $c; break } }
}
if (-not $Python) { throw "Python 3.12 not found; pass -Python <path to python.exe>" }
$Version = (& $Python -c "from version import __version__; print(__version__)").Trim()
Check "Reading the version"
Write-Host "CaseCraft Studio $Version  (Python: $Python)"

Step "Frontend build"
Push-Location web
try {
    if (Test-Path package-lock.json) { npm ci --no-audit --no-fund } else { npm install --no-audit --no-fund }
    Check "npm install"
    npm run build
    Check "npm run build"
} finally { Pop-Location }

if (-not $SkipTests) {
    Step "Fast tests"
    & $Python -m pytest -m "not slow" -q
    Check "Tests"
}

Step "PyInstaller"
& $Python -m PyInstaller desktop\casecraft.spec --noconfirm --distpath dist --workpath build\pyinstaller
Check "PyInstaller"

Step "Smoke test of the packaged app"
& $Python desktop\smoke_test.py dist\CaseCraftStudio\CaseCraftStudio.exe
Check "Smoke test"

if (-not $SkipInstaller) {
    Step "Installer"
    $iscc = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 not found. Install it (winget install JRSoftware.InnoSetup) or pass -SkipInstaller." }
    & $iscc "/DAppVersion=$Version" desktop\installer.iss
    Check "Inno Setup"
    Write-Host ""
    Write-Host "Installer: dist\CaseCraftStudio-Setup-$Version.exe" -ForegroundColor Green
}
Write-Host "App folder: dist\CaseCraftStudio\" -ForegroundColor Green
