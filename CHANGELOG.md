# Changelog

All notable changes to this project are documented here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).

## [Unreleased]

### Added
- `SECURITY.md`: private reporting through GitHub, response and fix timelines, disclosure in a security advisory.
- OpenSSF Scorecard workflow and badge, CodeQL; Dependabot for GitHub Actions (7-day cooldown).
- `tests/test_queue.py`: app-collection queue built from `data/models.json`, every configuration and language exactly once, a batch sent at most twice.

### Changed
- One repository: this public repository is now the only working copy. The hidden lot and raw runs stay on the maintainer's machine, outside version control; `load_items()` reads the full bank (`data/items.full.jsonl`) when it is present, otherwise the public lot in `data/items.jsonl`.
- The private-lot leak test now runs everywhere, with stand-in hidden items when the private lot is absent.
- GitHub Actions pinned by commit SHA, read-only token, checkout without persisted credentials (zizmor clean).

### Removed
- `public-items` command and the export of a public copy from a private repository.

## [2.0.0-preview] - 2026-10-18

### Added
- AIBIAS v2 preview: 239 bilingual questions (163 public, 76 private), four conditions (neutral, two opposite personas, "Are you sure?" challenge), hidden answer key.
- API track (OpenAI-compatible endpoints, resumable runner) and app track (numbered batches pasted into assistant apps, `app-prompts` / `app-import`, import refused if the pasted text differs from the generated one).
- Labelling by script and by a judge from another model family; dedicated pass on open questions separating settled claims from probabilistic forecasts.
- Metrics with 95 % bootstrap intervals; completeness rule (an incomplete model is never ranked); `publish` command (ranking + answers to public questions only).
- Preview results for three complete models in English (`results/preview-2026-10/`).
