$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
if (-not (Test-Path "$Project\.venv\Scripts\python.exe")) { python -m venv "$Project\.venv" }
$env:TEMP = "$Project\tmp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
& "$Project\.venv\Scripts\python.exe" -m pip install -r "$Project\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'Cài đặt thư viện thất bại' }
Write-Host 'Hoàn tất. Ollama phải được cài riêng từ https://ollama.com/download/windows'
