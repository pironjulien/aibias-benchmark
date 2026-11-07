# Contributing

## Environment

- Python 3.13 or newer (`pyproject.toml`), no runtime dependency;
- PowerShell 7 to run `test.ps1`, and [gitleaks](https://github.com/gitleaks/gitleaks) on the PATH (required by the
  secret scan);
- ruff and mypy are installed by `test.ps1` itself, pinned with hashes (`requirements-dev.txt`), in a virtual
  environment outside the repository.

## Rules

1. Open an issue or a pull request against `main`. A change is accepted only when `./test.ps1` passes: the CI
   (`.github/workflows/test.yml`) runs that same script on Python 3.13 and 3.14 on every push and pull request.
2. **Every new feature and every bug fix comes with its test** in `tests/` (`unittest`, with fake model answers: no
   test calls a provider). A fix starts with a test that fails without it.
3. A change to the questions, personas or models keeps `python -m aibias check` green (run by `test.ps1`).
4. Never commit an API key, a token or a private run: keys are read from `~/.aibias/api-keys` (or `AIBIAS_SECRETS`),
   never printed nor stored in runs. `test.ps1` scans the whole Git history and the files with gitleaks and the
   providers' key patterns.
5. Code passes ruff and mypy. Commit messages and `CHANGELOG.md` entries (Keep a Changelog, under `[Unreleased]`) are
   written in English.

## Checks

```powershell
./test.ps1    # unit tests, data validation, ruff, mypy, secret scan; offline once the pinned dev tools are installed
git diff --check
```

## Version

The version is in `pyproject.toml` (PEP 440 form) and `aibias.__version__`, raised at each release with its
`CHANGELOG.md` section.
