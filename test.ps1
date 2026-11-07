# Check: unit tests, data validation, ruff and mypy, secret scan (gitleaks + provider patterns). Exit 0 when everything
# passes. Offline once the pinned dev tools are installed (first run only).
param([switch]$Full)
# Nexus pre-push gate: on a Nexus workstation the run goes through ~\.nexus\git\Invoke-NexusTest.ps1 (NexusInfra), which
# records the tested tree when it passes; the pre-push hook refuses a pushed tree that has not passed this script.
if (-not $env:NEXUS_TEST_EMPREINTE -and (Test-Path -LiteralPath "$HOME\.nexus\git\Invoke-NexusTest.ps1")) { & "$HOME\.nexus\git\Invoke-NexusTest.ps1" -Script $PSCommandPath -Parametres $PSBoundParameters -Arguments $args; exit $LASTEXITCODE }
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location $PSScriptRoot
try {
    python -m unittest discover -s tests -t . ; if ($LASTEXITCODE) { throw 'unit tests failed' }
    python -m aibias check ; if ($LASTEXITCODE) { throw 'data check failed' }
    # Lint and types: ruff and mypy pinned with hashes (requirements-dev.txt), in a virtual environment outside the
    # repository, rebuilt only when the pins or the Python version change.
    $pins = (Get-FileHash requirements-dev.txt).Hash.Substring(0, 12).ToLower()
    $pyVersion = python -c "import sys; print(f'{sys.version_info[0]}{sys.version_info[1]}')"
    $venv = Join-Path $HOME ".nexus\tests\aibias-benchmark\venv-py$pyVersion-$pins"
    $py = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        $partial = "$venv.partial"
        python -m venv --clear $partial ; if ($LASTEXITCODE) { throw 'venv creation failed' }
        & (Join-Path $partial 'Scripts\python.exe') -m pip install --quiet --disable-pip-version-check --require-hashes --only-binary ':all:' -r requirements-dev.txt
        if ($LASTEXITCODE) { throw 'dev tools install failed (requirements-dev.txt)' }
        Move-Item -LiteralPath $partial -Destination $venv
    }
    & $py -m ruff check --no-cache . ; if ($LASTEXITCODE) { throw 'ruff failed' }
    & $py -m mypy --cache-dir (Join-Path $venv 'mypy-cache') ; if ($LASTEXITCODE) { throw 'mypy failed' }
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
