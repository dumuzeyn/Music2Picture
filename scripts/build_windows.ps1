param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$BuildRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $BuildRoot
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name M2P-Studio `
    --exclude-module scipy --exclude-module matplotlib --exclude-module pandas `
    --exclude-module torch --exclude-module cv2 --exclude-module IPython `
    --add-data 'licenses;licenses' --add-data 'README.md;.' m2p_gui.py
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
Write-Output 'Created dist/M2P-Studio.exe. FFmpeg is an external dependency (see README).'
