$ErrorActionPreference = 'Stop'
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
& "$Project\.venv\Scripts\python.exe" "$Project\scripts\benchmark.py"
if ($LASTEXITCODE -ne 0) { throw 'Benchmark chưa hoàn tất' }
