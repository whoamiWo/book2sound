"""Optional: evaluate chaptering against a local corpus of real EPUBs.

Usage:
    SOUNDBOOK_CORPUS=/path/to/epubs pytest -m corpus -s

Ground truth (optional): place a ``<book-stem>.boundaries`` file next to each
EPUB, one ``<zip-relative-href>|<block-index>`` per line, listing the *true*
chapter starts. Example::

    OEBPS/Text/ch1.xhtml|0
    OEBPS/Text/ch2.xhtml|3

``SOUNDBOOK_CORPUS_TOLERANCE`` (block-index window, default 1) tunes matching.
``SOUNDBOOK_CORPUS_MIN_F1`` is optional: when set, the worst score must meet it;
when unset, scores are printed without enforcing a gate.

Never runs in CI. Does not write to the user's real SOUNDBOOK_HOME.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import pytest

from soundbook import PIPELINE_VERSION
from soundbook.config import ChapteringPolicy
from soundbook.ingest.chaptering import choose_strategy
from soundbook.ingest.classify import classify_skippable
from soundbook.ingest.loader import UnusableBook, load_book
from soundbook.ingest.metrics import boundary_f1

pytestmark = pytest.mark.corpus

CORPUS = os.environ.get("SOUNDBOOK_CORPUS")


def _books() -> list[Path]:
    if not CORPUS:
        return []
    root = Path(CORPUS)
    return sorted(root.rglob("*.epub"))


def test_corpus_loads_without_uncaught_exceptions():
    books = _books()
    if not books:
        pytest.skip("SOUNDBOOK_CORPUS not set or empty")
    failures: list[str] = []
    usable = 0
    for path in books:
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


def _gold_for(path: Path) -> tuple[list[str], str | None]:
    """Return ``(boundaries, skip_reason)``; never skip during collection."""

    gold = path.with_suffix(".boundaries")
    if not gold.is_file():
        return [], "no .boundaries file"
    lines = gold.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip().startswith("# pipeline "):
        version = lines[0].strip().removeprefix("# pipeline ").strip()
        if version != PIPELINE_VERSION:
            return [], f"gold pipeline {version} != current {PIPELINE_VERSION}"
    boundaries = []
    for line in lines:
        key, marker, comment = line.partition("#")
        if marker and "[skippable]" in comment:
            continue
        key = key.strip()
        if key:
            boundaries.append(key)
    return boundaries, None


def test_corpus_boundary_f1_meets_gate():
    books = _books()
    if not books:
        pytest.skip("SOUNDBOOK_CORPUS not set or empty")
    tolerance = int(os.environ.get("SOUNDBOOK_CORPUS_TOLERANCE", "1"))
    results: list[dict] = []
    for path in books:
        gold_path = path.with_suffix(".boundaries")
        gold, skip_reason = _gold_for(path)
        if skip_reason:
            print(f"{path.name}: skipped ({skip_reason})")
            continue
        if not gold:
            pytest.fail(f"{gold_path}: gold file has no chapter boundaries after comments")
        try:
            book = load_book(path)
        except UnusableBook as exc:
            print(f"{path.name}: skipped (unusable: {exc})")
            continue
        policy = ChapteringPolicy()
        strategy, drafts = choose_strategy(book, policy)
        classify_skippable(drafts, policy)
        predicted = [d.start_key for d in drafts if not d.skippable]
        skippable = sum(d.skippable for d in drafts)
        f1 = boundary_f1(predicted, gold, tolerance_blocks=tolerance)
        warnings = sum(r.reason.startswith("anchor_") for d in drafts for r in d.rejected)
        results.append({
            "name": path.name,
            "strategy": strategy,
            "predicted": len(predicted),
            "skippable": skippable,
            "gold": len(gold),
            "f1": f1,
            "anchor_warnings": warnings,
        })
        chapters_match = len(predicted) == len(gold)
        print(f"{path.name}: strategy={strategy} predicted={len(predicted)} "
              f"skippable={skippable} gold={len(gold)} chapters_match={chapters_match} "
              f"F1={f1:.3f} anchor_warnings={warnings}")

    if not results:
        pytest.skip("no scoreable gold files")

    scores = {r["name"]: r["f1"] for r in results}
    strategies = Counter(r["strategy"] for r in results)
    strategy_text = ", ".join(f"{name}={count}" for name, count in sorted(strategies.items()))
    values = list(scores.values())
    print(f"summary: books={len(values)} mean_F1={sum(values) / len(values):.3f} "
          f"min_F1={min(values):.3f} strategies={strategy_text}")
    worst_name, worst_f1 = min(scores.items(), key=lambda item: item[1])

    min_f1_raw = os.environ.get("SOUNDBOOK_CORPUS_MIN_F1")
    if min_f1_raw:
        min_f1 = float(min_f1_raw)
        assert worst_f1 >= min_f1, (
            f"worst book {worst_name} F1={worst_f1:.3f} < {min_f1}; all scores: {scores}")
        print(f"gate: worst {worst_name} F1={worst_f1:.3f} >= {min_f1}")
    else:
        print("gate: disabled (set SOUNDBOOK_CORPUS_MIN_F1 to enforce a minimum)")
