"""Chapter-boundary quality metric (spec §6).

A boundary is encoded exactly like ``ChapterDraft.start_key``: ``"<href>|<block>"``
where ``href`` is the zip-relative spine path and ``block`` is the block index
inside that document. Two boundaries match when the href is identical and the
block indices differ by at most ``tolerance_blocks``.

``boundary_f1`` is the harmonic mean of precision and recall over boundary sets.
It is a *pure* function so it can be used both by the corpus test (predicted
chaptering vs a hand-checked ground truth) and by unit tests.
"""

from __future__ import annotations

from collections.abc import Iterable


def parse_key(key: str) -> tuple[str, int]:
    href, block = key.rsplit("|", 1)
    return href, int(block)


def boundary_f1(predicted: Iterable[str], gold: Iterable[str], *,
                tolerance_blocks: int = 0) -> float:
    """F1 of predicted vs gold chapter starts, matching within a block window."""

    gold_keys = [parse_key(k) for k in gold]
    pred_keys = [parse_key(k) for k in predicted]
    if not gold_keys and not pred_keys:
        return 1.0
    if not gold_keys or not pred_keys:
        return 0.0

    used = [False] * len(gold_keys)
    matched = 0
    for href, block in pred_keys:
        for idx, (g_href, g_block) in enumerate(gold_keys):
            if used[idx] or g_href != href:
                continue
            if abs(g_block - block) <= tolerance_blocks:
                used[idx] = True
                matched += 1
                break
    if matched == 0:
        return 0.0
    precision = matched / len(pred_keys)
    recall = matched / len(gold_keys)
    return 2 * precision * recall / (precision + recall)
