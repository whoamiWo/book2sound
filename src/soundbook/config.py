"""Policies, fingerprints and on-disk locations.

Everything that influences output is a frozen dataclass here and is folded into
one of the two fingerprints:

* ``synth_fingerprint`` — what decides *the bytes of one segment*
  (ADR-007/ADR-013). It never contains ``pipeline_version``: changing the
  cleaner or the segmenter must not re-synthesize text that did not change.
* ``text_fingerprint`` — what decides *how the book is cut up*.  Diagnostics
  only; invalidation is driven per chapter by ``chapters.text_sha256``.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from soundbook import AUDIO_FORMAT_VERSION, PIPELINE_VERSION


# --------------------------------------------------------------------------
# policies
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChapteringPolicy:
    """Thresholds of the vetoer and of the nav/outline/spine strategies."""

    max_share: float = 0.45
    median_chars_floor: int = 300
    median_chars_min_chapters: int = 20
    single_chapter_max_chars: int = 20_000
    min_nav_entries: int = 3
    anchor_prefix_chars: int = 20
    heading_levels: tuple[int, ...] = (1, 2, 3)
    max_toc_depth: int = 6
    front_matter_window: int = 2
    back_matter_window: int = 1


@dataclass(frozen=True)
class CleanPolicy:
    header_min_repeats: int = 3
    header_max_chars: int = 30
    page_number_max_chars: int = 12
    short_paragraph_chars: int = 5
    strip_footnote_markers: bool = True
    normalize_punctuation: bool = True
    warning_min_chars: int = 200
    warning_min_blocks: int = 5


@dataclass(frozen=True)
class SegmentPolicy:
    """Pure segmentation parameters (ADR-012). Never read at runtime."""

    target_chars: int = 90
    hard_max_chars: int = 300
    min_chars: int = 1
    sentence_pause_ms: int = 220
    paragraph_pause_ms: int = 500
    chapter_pause_ms: int = 1200
    speak_titles: bool = True

    def with_overrides(self, **kwargs: Any) -> "SegmentPolicy":
        return replace(self, **{k: v for k, v in kwargs.items() if v is not None})


@dataclass(frozen=True)
class AudioPolicy:
    sample_rate: int = 24_000
    channels: int = 1
    sample_width: int = 2  # bytes; 16-bit PCM
    bitrate: str = "64k"
    loudnorm: bool = True
    loudnorm_i: float = -18.0
    loudnorm_tp: float = -1.5
    loudnorm_lra: float = 11.0
    aac_profile: str = "aac_low"
    language: str = "zho"
    faststart: bool = True

    @property
    def bytes_per_second(self) -> int:
        return self.sample_rate * self.channels * self.sample_width


@dataclass(frozen=True)
class TTSConfig:
    backend: str = "fake"
    voice: str | None = None
    rate: float = 1.0
    model_tag: str | None = None
    endpoint: str | None = None
    jobs: int = 1
    max_retries: int = 3
    timeout_s: float = 120.0


@dataclass(frozen=True)
class Policies:
    chaptering: ChapteringPolicy = field(default_factory=ChapteringPolicy)
    clean: CleanPolicy = field(default_factory=CleanPolicy)
    segment: SegmentPolicy = field(default_factory=SegmentPolicy)
    audio: AudioPolicy = field(default_factory=AudioPolicy)


# --------------------------------------------------------------------------
# fingerprints
# --------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Deterministic JSON used inside every hash in this project."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def synth_fingerprint(
    *,
    backend: str,
    model_id: str,
    model_version: str,
    voice: str,
    rate: float,
    sample_rate: int,
    audio_format_version: str = AUDIO_FORMAT_VERSION,
) -> str:
    """Hash of everything that decides the audio bytes of one segment."""

    return _hash_json(
        {
            "backend": backend,
            "model_id": model_id,
            "model_version": model_version,
            "voice": voice,
            "rate": round(float(rate), 4),
            "sample_rate": sample_rate,
            "audio_format_version": audio_format_version,
        }
    )


def audio_key(text: str, synth_fp: str) -> str:
    """Content address of one synthesized segment (ADR-013)."""

    return hashlib.sha256(text.encode("utf-8") + b"\x00" + synth_fp.encode("ascii")).hexdigest()


def text_fingerprint(policies: Policies) -> str:
    """Diagnostic hash of parse/clean/segment semantics."""

    return _hash_json(
        {
            "pipeline_version": PIPELINE_VERSION,
            "clean": asdict(policies.clean),
            "chaptering": asdict(policies.chaptering),
            "segment": asdict(policies.segment),
        }
    )


def artifact_fingerprint(
    *,
    audio_keys: list[str],
    audio: AudioPolicy,
    loudnorm_params: dict[str, Any] | None,
    cover_sha256: str | None,
    silence_ms: tuple[int, ...],
    n_samples: list[int],
) -> str:
    """Everything that decides the bytes of the finished M4B (plan §3.5)."""

    return _hash_json(
        {
            "audio_keys": audio_keys,
            "bitrate": audio.bitrate,
            "codec": "aac",
            "sample_rate": audio.sample_rate,
            "channels": audio.channels,
            "language": audio.language,
            "faststart": audio.faststart,
            "loudnorm": loudnorm_params,
            "cover_sha256": cover_sha256,
            "silence_ms": list(silence_ms),
            "n_samples": n_samples,
        }
    )


# --------------------------------------------------------------------------
# locations
# --------------------------------------------------------------------------


def home_dir() -> Path:
    return Path(os.environ.get("SOUNDBOOK_HOME", "~/.local/share/soundbook")).expanduser()


def cache_dir() -> Path:
    return Path(os.environ.get("SOUNDBOOK_CACHE_DIR", "~/.cache/soundbook/audio")).expanduser()


def db_path() -> Path:
    return home_dir() / "state.sqlite"


def locks_dir() -> Path:
    return home_dir() / "locks"


def work_dir() -> Path:
    """Scratch space for concat lists, ffmeta and loudnorm measurements."""

    return home_dir() / "work"


def ensure_dirs() -> None:
    for path in (home_dir(), cache_dir(), locks_dir(), work_dir()):
        path.mkdir(parents=True, exist_ok=True)


def audio_path(key: str) -> Path:
    return cache_dir() / key[:2] / f"{key}.flac"
