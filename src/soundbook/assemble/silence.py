"""Silence files are ordinary FLACs in the concat list (spec §10).

One 24 kHz mono FLAC per distinct pause duration; writing them lazily keeps a
three-pause book with 3000 segments from creating 3000 files.
"""

from __future__ import annotations

from pathlib import Path

from soundbook.util.audio import write_silence_flac

SAMPLE_RATE = 24_000


def samples_for_ms(ms: int, sample_rate: int = SAMPLE_RATE) -> int:
    return int(round(sample_rate * ms / 1000))


def ensure_silence(work_dir: str | Path, ms: int, *,
                   sample_rate: int = SAMPLE_RATE) -> tuple[Path, int]:
    path = Path(work_dir) / f"silence-{sample_rate}-{ms}ms.flac"
    n_samples = samples_for_ms(ms, sample_rate)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{ms}.tmp.flac")
        write_silence_flac(tmp, n_samples, sample_rate=sample_rate)
        tmp.replace(path)
    return path, n_samples
