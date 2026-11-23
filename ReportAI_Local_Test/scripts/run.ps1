$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
& "$Project\.venv\Scripts\python.exe" "$Project\app.py"
