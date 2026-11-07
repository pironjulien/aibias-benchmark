# Changelog

All notable changes to this project are documented here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).

## [Unreleased]

### Added
- `pyproject.toml` (`requires-python >= 3.13`, no runtime dependency) with ruff and mypy settings; `test.ps1` runs
  `ruff check` and `mypy` from `requirements-dev.txt` (hash-pinned, installed in a virtual environment outside the
  repository). CI tests Python 3.13 and 3.14; Dependabot watches the dev tools (7-day cooldown).
- `tests/test_queue.py`: app-collection queue built from `data/models.json`, every configuration and language exactly once, a batch sent at most twice.

### Changed
- One repository: this public repository is now the only working copy. The hidden lot and raw runs stay on the maintainer's machine, outside version control; `load_items()` reads the full bank (`data/items.full.jsonl`) when it is present, otherwise the public lot in `data/items.jsonl`.
- The private-lot leak test now runs everywhere, with stand-in hidden items when the private lot is absent.
- GitHub Actions pinned by commit SHA, read-only token, checkout without persisted credentials (zizmor clean).
- The `run_queue.sh` check moved out of the public tests, next to the private app-collection tools it tests: it was
  always skipped in CI. `test.ps1` runs it when those tools are present.
- `pyproject.toml` and `aibias.__version__` carry the last release, `2.0.0rc0` (PEP 440 form of `v2.0.0-preview`),
  instead of `0.0.0` and `2.0.0-dev`.

### Fixed
- Lint findings: `zip()` calls on equal-length sequences are `strict=True`, adjacent-pair checks use
  `itertools.pairwise`, `datetime.UTC`, no lambda assignment, unused loop variable renamed.
- The `run_queue.sh` check runs the script with Git Bash on Windows; the first `bash` on PATH was WSL's, which cannot read Windows paths.

### Security
- `SECURITY.md`: private reporting through GitHub, response and fix timelines, disclosure in a security advisory.
- OpenSSF Scorecard workflow and badge; Dependabot for GitHub Actions (7-day cooldown).
- CodeQL runs from `.github/workflows/codeql.yml` (actions and Python, default queries) instead of the default setup, so OpenSSF Scorecard credits SAST for commits pushed without pull requests.
- `test.ps1` scans the whole Git history and the files with gitleaks (required); CI installs gitleaks 8.30.1 with a checksum check and checks out the full history. The provider patterns stay as an extra check.

### Removed
- `public-items` command and the export of a public copy from a private repository.

## [2.0.0-preview] - 2026-10-18

### Added
- AIBIAS v2 preview: 239 bilingual questions (163 public, 76 private), four conditions (neutral, two opposite personas, "Are you sure?" challenge), hidden answer key.
- API track (OpenAI-compatible endpoints, resumable runner) and app track (numbered batches pasted into assistant apps, `app-prompts` / `app-import`, import refused if the pasted text differs from the generated one).
- Labelling by script and by a judge from another model family; dedicated pass on open questions separating settled claims from probabilistic forecasts.
- Metrics with 95 % bootstrap intervals; completeness rule (an incomplete model is never ranked); `publish` command (ranking + answers to public questions only).
- Preview results for three complete models in English (`results/preview-2026-10/`).
