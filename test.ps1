# Offline check: unit tests, data validation, secret scan. Exit 0 when everything passes.
param([switch]$Full)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $PSScriptRoot
try {
    python -m unittest discover -s tests -t . ; if ($LASTEXITCODE) { throw 'unit tests failed' }
    python -m aibias check ; if ($LASTEXITCODE) { throw 'data check failed' }
    $pattern = '(sk-[A-Za-z0-9_-]{20,}|sk-or-v1-[a-f0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|Bearer [A-Za-z0-9._-]{20,})'
    $hits = git ls-files -co --exclude-standard | Where-Object { Test-Path $_ -PathType Leaf } |
        Select-String -Pattern $pattern -List
    if ($hits) { $hits | ForEach-Object { Write-Host "secret? $($_.Path):$($_.LineNumber)" }; throw 'possible secret in tracked files' }
    Write-Host 'test.ps1: OK'
} finally { Pop-Location }
