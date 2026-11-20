# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`PIPELINE_VERSION` is tracked separately from the package version: it only changes when
parsing, cleaning or segmentation semantics change, because it is part of the cache key
(see ADR-007).

## [0.1.1] - 2026-11-20

Engineering hygiene only: no runtime behaviour change, no cache invalidation.
`PIPELINE_VERSION` stays at `0.1.0`.

### Added

- `CHANGELOG.md` (this file).
- `.github/workflows/release.yml`: tag-triggered release with PyPI Trusted Publishing
  (OIDC). One `build` job produces `dist/`; `testpypi` and `pypi` upload the same
  artifacts, and the `pypi` job requires manual approval.
- ADR-021: release via Trusted Publishing instead of a long-lived API token.
- A parametrized idempotence test over `tests/helpers.CHINESE_PARAGRAPHS` and the existing
  messy-text sample: `clean(clean(x)) == clean(x)`.

### Changed

- `pyproject.toml`: `license = "Apache-2.0"` plus `license-files = ["LICENSE"]` (PEP 639,
  replaces the deprecated `license = { text = ... }`); build requirement raised to
  `setuptools>=77`; added `[project.urls]` (Homepage, Source, Issues, Changelog) and
  classifiers, so the PyPI page links back to the repository.
- Docs: `docs/limitations.md` now states that Kokoro was exercised end to end in the
  Python 3.12 container; `docs/benchmarks.md` records the actual build/run commands of
  the Kokoro image, and `README.md` no longer calls `Dockerfile.kokoro` a reconstructed
  recipe.
- `README.md`: the `pytest -m corpus` line explains that the marker is reserved for 0.2.0
  and needs `SOUNDBOOK_CORPUS_DIR`; no test is selected today.
- `src/soundbook/ingest/clean.py`: docstring points at the parametrized idempotence test
  instead of a nonexistent corpus property test.

### Verified

- The Kokoro image builds from the committed `Dockerfile.kokoro` and runs a two-chapter
  fixture book end to end (see `docs/benchmarks.md`).

## [0.1.0] - 2026-11-20

First release.

### Added

- CLI `epub2m4b` with `run`, `inspect`, `voices`, `status`, `doctor`.
- Chaptering: nav → nav+hybrid → outline → spine, with a vetoer that records why a
  strategy was rejected (`inspect --json`).
- Three-level anchor resolution: `dom_ids` index → lxml second pass → heading-text
  fallback. Fallbacks are surfaced as chapter `warnings` in both `inspect` and `run`.
- Resumable synthesis: segment audio is content-addressed by
  `sha256(tts_input_text ‖ synth_fingerprint)`; Ctrl-C / SIGKILL then rerun never redoes
  finished segments.
- Chapter timeline computed from integer sample counts, verified against ffprobe within
  150 ms.
- Graceful degradation: DRM / image-only books exit 3; silent loudness measurement turns
  loudnorm off with a warning; failed segments exit 2, and `--allow-incomplete` packages
  what finished.
- TTS backends: `fake`, `openai_compat`, local `kokoro` (0.9.4). `epub2m4b voices` lists
  voices without downloading the model.
- Docker: `Dockerfile` (core) and `Dockerfile.kokoro` (Kokoro on Python 3.12).
- CI on Python 3.10 / 3.12 / 3.13.

### Known limitations

- `kokoro==0.9.4` requires Python < 3.13; newer system Pythons need the Docker image.
- Real Kokoro has only a small 2-chapter × 4-segment observation, no RTF benchmark; see
  `docs/benchmarks.md`.
- Multiple book sources inside one EPUB and complex CSS pagination are not specifically
  handled.

[0.1.1]: https://github.com/whoamiWo/book2sound/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/whoamiWo/book2sound/releases/tag/v0.1.0
