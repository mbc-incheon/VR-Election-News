param([switch]$InstallOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $localPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 이상을 설치한 뒤 다시 실행하세요.' }
}
& $localPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '필요한 패키지를 설치하지 못했습니다.' }
if (-not $InstallOnly) { & (Join-Path $PSScriptRoot 'start.ps1') }
