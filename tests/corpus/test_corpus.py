"""Optional: evaluate chaptering against a local corpus of real EPUBs.

Usage:
    SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus

Ground truth (optional): place a ``<book-stem>.boundaries`` file next to each
EPUB, one ``<zip-relative-href>|<block-index>`` per line, listing the *true*
chapter starts. Example::

    OEBPS/Text/ch1.xhtml|0
    OEBPS/Text/ch2.xhtml|3

``SOUNDBOOK_CORPUS_TOLERANCE`` (block-index window, default 1) and
``SOUNDBOOK_CORPUS_MIN_F1`` (default 0.90, use 0.75 for web novels) tune the gate.

Never runs in CI. Does not write to the user's real SOUNDBOOK_HOME.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from soundbook import PIPELINE_VERSION
from soundbook.config import ChapteringPolicy
from soundbook.ingest.chaptering import choose_strategy
from soundbook.ingest.loader import UnusableBook, load_book
from soundbook.ingest.metrics import boundary_f1

pytestmark = pytest.mark.corpus

CORPUS = os.environ.get("SOUNDBOOK_CORPUS")


def _books() -> list[Path]:
    if not CORPUS:
        return []
    root = Path(CORPUS)
    return sorted(root.rglob("*.epub"))


@pytest.mark.skipif(not _books(), reason="SOUNDBOOK_CORPUS not set or empty")
def test_corpus_loads_without_uncaught_exceptions():
    failures: list[str] = []
    usable = 0
    for path in _books():
        try:
            book = load_book(path)
        except UnusableBook:
            continue  # expected for DRM / image-only books
        except Exception as exc:  # noqa: BLE001 - this is the circuit breaker
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        usable += 1
        strategy, drafts = choose_strategy(book, ChapteringPolicy())
        assert drafts, f"{path.name}: strategy {strategy} produced no chapters"
    assert not failures, "\n".join(failures[:20])
    assert usable > 0


def _gold_for(path: Path) -> list[str]:
    gold = path.with_suffix(".boundaries")
    if not gold.is_file():
        return []
    lines = gold.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip().startswith("# pipeline "):
        version = lines[0].strip().removeprefix("# pipeline ").strip()
        if version != PIPELINE_VERSION:
            pytest.skip(f"{path.name}: gold pipeline {version} != current {PIPELINE_VERSION}")
    boundaries = []
    for line in lines:
        key = line.partition("#")[0].strip()
        if key:
            boundaries.append(key)
    return boundaries


@pytest.mark.skipif(not any(_gold_for(p) for p in _books()),
                    reason="no .boundaries ground-truth files in the corpus")
def test_corpus_boundary_f1_meets_gate():
    tolerance = int(os.environ.get("SOUNDBOOK_CORPUS_TOLERANCE", "1"))
    min_f1 = float(os.environ.get("SOUNDBOOK_CORPUS_MIN_F1", "0.90"))
    scores: dict[str, float] = {}
    for path in _books():
        gold = _gold_for(path)
        if not gold:
            continue
        try:
            book = load_book(path)
        except UnusableBook:
            continue
        strategy, drafts = choose_strategy(book, ChapteringPolicy())
        f1 = boundary_f1([d.start_key for d in drafts], gold, tolerance_blocks=tolerance)
        scores[path.name] = f1
        warnings = sum(r.reason.startswith("anchor_") for d in drafts for r in d.rejected)
        print(f"{path.name}: strategy={strategy} predicted={len(drafts)} gold={len(gold)} "
              f"F1={f1:.3f} anchor_warnings={warnings}")
    worst = min(scores.items(), key=lambda kv: kv[1])
    assert worst[1] >= min_f1, (
        f"worst book {worst[0]} F1={worst[1]:.3f} < {min_f1}; all scores: {scores}")
