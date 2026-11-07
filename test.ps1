# Offline check: unit tests, data validation, secret scan (gitleaks + provider patterns). Exit 0 when everything passes.
param([switch]$Full)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $PSScriptRoot
try {
    python -m unittest discover -s tests -t . ; if ($LASTEXITCODE) { throw 'unit tests failed' }
    python -m aibias check ; if ($LASTEXITCODE) { throw 'data check failed' }
    # Secrets: gitleaks on the whole Git history, then on the files (tracked or new); required, locally and in CI.
    $gitleaks = (Get-Command gitleaks -ErrorAction SilentlyContinue)
    if (-not $gitleaks) { throw 'gitleaks not found: install it (winget install Gitleaks.Gitleaks).' }
    & $gitleaks.Source git --redact --no-banner --exit-code 1 . ; if ($LASTEXITCODE) { throw 'gitleaks: secret in the Git history' }
    & $gitleaks.Source dir --redact --no-banner --exit-code 1 . ; if ($LASTEXITCODE) { throw 'gitleaks: secret in the files' }
    # Extra patterns of the providers this benchmark calls (OpenRouter, OpenAI, Google), on the working files.
    $pattern = '(sk-[A-Za-z0-9_-]{20,}|sk-or-v1-[a-f0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|Bearer [A-Za-z0-9._-]{20,})'
    $hits = git ls-files -co --exclude-standard | Where-Object { Test-Path $_ -PathType Leaf } |
        Select-String -Pattern $pattern -List
    if ($hits) { $hits | ForEach-Object { Write-Host "secret? $($_.Path):$($_.LineNumber)" }; throw 'possible secret in tracked files' }
    Write-Host 'test.ps1: OK'
} finally { Pop-Location }
