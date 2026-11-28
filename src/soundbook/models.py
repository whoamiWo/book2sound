"""Plain data types shared between the layers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BookInfo:
    """Metadata of one opened EPUB, independent of epubx's own objects."""

    book_id: str
    path: str
    title: str
    language: str | None
    n_spine: int
    n_toc: int
    unsupported: str | None = None
    obfuscated_fonts: tuple[str, ...] = ()
    cover_sha256: str | None = None


@dataclass(frozen=True)
class Rejection:
    strategy: str
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"strategy": self.strategy, "reason": self.reason, "metrics": dict(self.metrics)}


@dataclass
class ChapterDraft:
    """A chapter boundary plus the raw paragraph stream it owns."""

    idx: int
    title: str
    paragraphs: tuple[str, ...]
    strategy: str
    start_key: str
    end_key: str | None
    rejected: tuple[Rejection, ...] = ()
    skippable: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(p for p in self.paragraphs if p)

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SegmentDraft:
    """Pure output of the segmenter; no I/O, no state."""

    chapter_idx: int
    seg_idx: int  # -1 = spoken title, 0..n-1 = body
    text: str
    pause_after_ms: int
    is_title: bool = False


@dataclass(frozen=True)
class EngineInfo:
    name: str
    model_id: str
    model_version: str
    sample_rate: int
    voice: str


@dataclass(frozen=True)
class TimelineEntry:
    """One item of the concat list; silence is a real FLAC file too."""

    path: str
    n_samples: int
    kind: str  # "title" | "body" | "silence"
    chapter_idx: int | None = None


@dataclass(frozen=True)
class ChapterSpan:
    chapter_idx: int
    title: str
    start_ms: int
    end_ms: int
