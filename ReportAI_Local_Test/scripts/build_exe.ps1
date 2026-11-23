$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
$env:TEMP = "$Project\tmp"
$env:TMP = $env:TEMP
$env:PYINSTALLER_CONFIG_DIR = "$Project\build\pyinstaller-cache"
& "$Project\.venv\Scripts\python.exe" -m PyInstaller --noconfirm --onedir --windowed --name ReportAI_Local_Test --distpath "$Project\dist" --workpath "$Project\build" --specpath "$Project\build" "$Project\app.py"
if ($LASTEXITCODE -ne 0) { throw 'Build EXE thất bại' }
