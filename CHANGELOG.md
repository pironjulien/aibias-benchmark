# Changelog

All notable changes to this project are documented here ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).

## [Unreleased]

### Added
- OpenSSF Scorecard workflow and badge; Dependabot for GitHub Actions (7-day cooldown).

### Changed
- GitHub Actions pinned by commit SHA, read-only token, checkout without persisted credentials (zizmor clean).

## [2.0.0-preview] - 2026-10-18

### Added
- AIBIAS v2 preview: 239 bilingual questions (163 public, 76 private), four conditions (neutral, two opposite personas, "Are you sure?" challenge), hidden answer key.
- API track (OpenAI-compatible endpoints, resumable runner) and app track (numbered batches pasted into assistant apps, `app-prompts` / `app-import`, import refused if the pasted text differs from the generated one).
- Labelling by script and by a judge from another model family; dedicated pass on open questions separating settled claims from probabilistic forecasts.
- Metrics with 95 % bootstrap intervals; completeness rule (an incomplete model is never ranked); `publish` command (ranking + answers to public questions only).
- Preview results for three complete models in English (`results/preview-2026-10/`).
