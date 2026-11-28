"""Disk preflight (spec §10).

Estimates are explicitly estimates: ``BYTES_PER_CHAR_FLAC`` must be replaced by
a measured value from ``docs/benchmarks.md`` before it is quoted anywhere.
"""

from __future__ import annotations

import shutil
from pathlib import Path

BYTES_PER_CHAR_FLAC = 5_800  # midpoint of 5.2–6.3 KiB, measured ratio pending
BYTES_PER_CHAR_AAC = 8_000 / 4.5


class InsufficientSpace(RuntimeError):
    pass


def free_bytes(path: str | Path) -> int:
    probe = Path(path)
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free


def estimate_remaining(chars_pending: int, chars_total: int) -> int:
    flac = int(chars_pending * BYTES_PER_CHAR_FLAC)
    aac = int(chars_total * BYTES_PER_CHAR_AAC)
    return flac + aac


def check_space(path: str | Path, chars_pending: int, chars_total: int) -> None:
    needed = int(1.3 * estimate_remaining(chars_pending, chars_total))
    available = free_bytes(path)
    if available < needed:
        raise InsufficientSpace(
            f"disk space: need {needed / 1e9:.2f} GB, have {available / 1e9:.2f} GB at {path}"
        )
