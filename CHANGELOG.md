# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`PIPELINE_VERSION` is tracked separately from the package version: it changes when parsing,
cleaning, chapter-selection or segmentation semantics change, because it is part of the cache key
(see ADR-007).

## [0.3.1] - 2026-11-28

Robustness audit and hardening release (see ADR-024). One chaptering output change, so
`PIPELINE_VERSION` moves to `0.3.1` together with the package version; block indices and all
corpus boundaries are unchanged.

### Fixed

- Chapter bodies after a fragment cut no longer lose their first subheading: only the block the
  cut starts on is treated as the spoken title. Previously, a nav anchor landing on a body
  paragraph made the next `<h2>` vanish from the narration (chaptering semantic change).
- Ctrl-C / SIGINT now cancels queued synthesis and returns immediately instead of waiting for
  the whole pending queue; at most `--jobs` in-flight segments finish their current call.
- When a later chaptering run produces fewer chapters (strategy switch, dedupe/merge), orphaned
  segment rows of removed chapters are pruned instead of being re-synthesized forever.
- `run` takes the book lock *before* rewriting the database, and a held lock now fails fast
  with exit code 1 and a clear message instead of "unexpected error".
- `--rate 0`, `--jobs 0`, `--max-retries 0` are rejected with exit code 1 instead of being
  silently clamped later.
- `inspect` no longer downgrades the book status: a finished ("done"), partial or failed book
  keeps its status after a fresh `inspect` re-records the chapter plan.
- Artifact freshness now also covers `language`, `faststart` and `aac_profile`; M4B files built
  before these fields were recorded are rebuilt once.
- `Timeline` milliseconds are computed with the timeline's own sample rate (the constant 24 kHz
  happened to match every current code path).
- Non-JPEG/PNG covers (webp/gif/bmp) are transcoded to MJPEG before being attached; `-c:v copy`
  into MP4 previously failed for these formats.

### Changed

- `assemble_m4b` verifies the produced M4B's chapter timeline against ffprobe (150 ms tolerance)
  and reports drift as warnings, so the acceptance-table guarantee is enforced on real runs, not
  only in tests.
- The Kokoro backend loads its model lazily on first synthesis; constructing it for the CLI's
  `info()` probe no longer holds a copy of the model for the whole run.
- CI gains a `ruff check src tests scripts` lint job; `ruff` is part of the `dev` extra.
- Dead API surface removed: `pipeline.synth_identity`, `db.get_chapter`, `db.set_chapter_status`,
  `util.hashing.short_hash`, `models.BlockRef`, `models.SynthResult`,
  `SegmentPolicy.with_overrides`, and the never-consumed policy fields
  `anchor_prefix_chars` / `heading_levels` / `max_toc_depth` / `short_paragraph_chars` /
  `min_chars`. No behaviour change; cache keys are unaffected.

### Measured

- Block indices unchanged: local corpus `.boundaries` files keep every line, only their
  `# pipeline` header moved to `0.3.1`. Chapter-content F1 evaluation is unaffected by this
  release because boundaries did not move.

## [0.3.0] - 2026-11-25

Chapter-selection semantics changed, so `PIPELINE_VERSION` moves to `0.3.0` together with the
package version. Parsing, cleaning and segmentation are untouched, and block indices are
unchanged.

### Fixed

- `classify_skippable` no longer returns early for books with one or two chapters. Non-reading
  pages (目录、版权页、扉页、书名页、contents, copyright, colophon, …) are now skipped in short
  books too; the `STUB_CHARS` and front/back-window rules still only apply when there are more
  than two chapters, so a short book cannot be swallowed by the stub threshold.
- A non-reading marker in the first paragraph must now be a **prefix** (after dropping
  whitespace), not an unrestricted substring. A body sentence such as
  “他翻开目录，检查版权归属和书名页的写法。” no longer skips its chapter, while standalone
  “目录”, “版权所有 © …” and “Table Of Contents” still match. Titles keep substring matching
  because they are metadata.
- If every chapter would be skippable, the flags are cleared so `run` still has audio to
  synthesize instead of exiting 2 with “nothing was synthesized; there is no audio to package”.

### Changed

- `书目` moved from `NON_READING_KEYWORDS` to `BACK_KEYWORDS`: a mid-book bibliography is
  spoken as an appendix, and only the back-window rule (last chapter by default) may skip it.
  `参考文献` keeps the same window rule.

### Measured

- The same five local corpus books re-tested under pipeline `0.3.0`: mean F1 `1.000`, worst
  `1.000`, all five `chapters_match=是`. `3b10558e` (spine fallback) now synthesizes the
  “已出书目” section (previously marked skippable), so its gold dropped that `[skippable]`
  marker; skippable count changed 6 → 5. All other boundaries and counts are unchanged.
- A synthetic no-nav sample (`8f96c9c1`, built by `scripts/build_nonav_sample.py`, 120
  chapters as plain-text title paragraphs, no navigation document) covers the last missing
  chaptering code path: strategy reports `nav` because epubx synthesizes 123 spine-derived toc
  entries, headings are empty, and titles degrade to file names; F1 `1.000` against authored
  gold. A genuine no-nav web novel is still missing from the real corpus; the untested Apple
  Books / Smart AudioBook Player entries are unchanged from 0.2.0.

## [0.2.0] - 2026-11-23

Chapter-selection semantics changed, so `PIPELINE_VERSION` moves to `0.2.0` together with the
package version. Parsing, cleaning and segmentation are untouched, and block indices are
unchanged.

### Fixed

- `classify_skippable` now treats non-reading pages (目录、版权页、书名页、扉页、contents,
  copyright, colophon, 书目, …) as skippable wherever they appear. The previous implementation
  also required them to fall in the first two or last one chapter, so a 目录/版权页 at chapter
  index 3+ was synthesized as body text, contradicting `docs/corpus.md`.
- The classifier matches non-reading-page keywords against the chapter title plus its first
  paragraph, so spine-fallback chapters whose title is a bare file name (e.g. `part0001.html`)
  are still recognised from their text. Reading-content keywords remain title- and window-gated.
- 前言/序/引言/楔子 stay window-gated because they are reading chapters; they are not skipped
  just for their title.

### Measured

- The same five-book local corpus now measures mean F1 `1.000`, worst `1.000`, all five with
  `chapters_match=是`. Per-chapter comparison showed the previous four mismatches were entirely
  skippable under-detection, not split/merge errors; no missed or spurious cuts were found.
- Structure coverage now includes fragment anchors and single-file multi-chapter books:
  `d615f98c` resolves 158 fragment nav entries into 168 chapters across 16 documents;
  `ecf98908` resolves 37 fragment entries with 8 documents contributing multiple chapters.
  Six of the seven target structures are covered; a genuine no-nav web novel is still missing.
- Gold files were regenerated and re-checked; only the 百年孤独 editorial introduction changed
  (from skippable to body), aligning it with the “序 counts as a chapter” rule. All other
  boundary lines were unchanged. Gold headers now record pipeline `0.2.0`.
- The duplicate/abnormal copy in the corpus directory (two documents, placeholder nav, one
  merged chapter) remains unlabelled and excluded from statistics.
- Player matrix is unchanged: Apple Books and Smart AudioBook Player still have no device test.

## [0.1.3] - 2026-11-22

Quality measurement and documentation fixes only; `PIPELINE_VERSION` remains `0.1.0`.
The five-book corpus workflow is now recorded as a local process-validation result;
VLC desktop technical parsing and VLC Android manual playback are recorded. Apple Books and
Smart AudioBook Player remain untested.

### Fixed

- Corpus F1 evaluation now skips stale or missing gold files per book, fails clearly on
  an existing empty gold file, and skips cleanly when nothing is scoreable.
- Corpus measurement now matches production by classifying and excluding skippable
  chapters, prints per-book and aggregate summaries, and enables the F1 gate only when
  `SOUNDBOOK_CORPUS_MIN_F1` is explicitly set.
- `corpus_draft.py` marks skippable draft chapters for annotators.

### Measured

- On a 12th Gen Intel i7-12700H (10 cores / 20 threads), a 74-segment two-chapter
  Kokoro sample measured RTF 0.384 with `--jobs 1` and 0.563 with `--jobs 2`.
  The CPU guidance now recommends starting with `--jobs 1`; see `docs/benchmarks.md`.
- The sample source repository has no declared license; this is recorded in
  `docs/compat.md` alongside its public-domain attribution.
- Five local books measured as a process-validation corpus: mean F1 `0.947`, worst F1
  `0.909`, with an explicit `0.90` gate passing; no external quality claim is made.
- VLC Android manual test: chapter titles, chapter seeking, cover and total duration passed;
  the displayed `1:22:43` matches the measured `4963.240 s`.

## [0.1.2] - 2026-11-21

Documentation, corpus tooling and sample validation only: no runtime chaptering or synthesis
behaviour change. `PIPELINE_VERSION` stays at `0.1.0`.

### Added

- `tests/corpus/test_corpus.py` is now included in the repository (previously hidden by an
  over-broad `corpus/` ignore rule), with optional `SOUNDBOOK_CORPUS` evaluation, pipeline-version
  checks, inline comments, per-book F1 output and anchor-warning counts.
- `tests/unit/test_corpus_gold.py` covers gold-file version matching, comments and legacy files.
- `scripts/corpus_draft.py` writes reviewable `.boundaries` and `.headings.txt` drafts without
  overwriting existing gold files; `docs/corpus.md` documents annotation rules and privacy.
- `scripts/build_sample.py` builds a nine-chapter public-domain《阿Q正传》EPUB with navigation and
  an original cover. `docs/compat.md` records its pinned source, SHA256, inspect result and the
  player matrix. Kokoro produced a 9-chapter, 4963.240-second M4B (468 new, 1 cached, 0 failed),
  with AAC 24 kHz mono audio and an embedded PNG cover verified by ffprobe; untested devices remain
  explicitly untested.
- `docs/benchmarks.md` adds the chapter-quality measurement section. No real corpus F1 is claimed
  yet because no annotated real-book corpus was provided on 2026-11-21.

### Changed

- `.gitignore` ignores only the repository-root `/corpus/`, not `tests/corpus/`.
- Corpus environment variable documentation uses `SOUNDBOOK_CORPUS`; the old 0.1.1 entry's
  `SOUNDBOOK_CORPUS_DIR` spelling was incorrect and is corrected here without rewriting that
  published historical entry.
- Package version is `0.1.2`; `PIPELINE_VERSION` remains `0.1.0`.

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

[0.3.1]: https://github.com/whoamiWo/book2sound/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/whoamiWo/book2sound/releases/tag/v0.3.0
[0.1.3]: https://github.com/whoamiWo/book2sound/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/whoamiWo/book2sound/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/whoamiWo/book2sound/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/whoamiWo/book2sound/releases/tag/v0.1.0
