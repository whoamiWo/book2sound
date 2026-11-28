"""Timeline, concat list and ffmetadata (spec §10, ADR-017).

Timestamps are integer sample counts accumulated in order; milliseconds are
produced once, at the end, by ``round(1000 * total / sample_rate)``.  The
1200 ms pause that precedes a title belongs to the *previous* chapter: it is
the trailing silence after that chapter's last body segment, so chapter
``START`` is the first sample of the title audio (or of the first body segment
when titles are not spoken).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from soundbook.assemble.silence import ensure_silence
from soundbook.models import ChapterSpan, TimelineEntry

SAMPLE_RATE = 24_000


@dataclass
class Timeline:
    entries: list[TimelineEntry]
    spans: list[ChapterSpan]
    sample_rate: int = SAMPLE_RATE

    @property
    def total_samples(self) -> int:
        return sum(e.n_samples for e in self.entries)

    @property
    def total_ms(self) -> int:
        return int(round(1000 * self.total_samples / self.sample_rate))


def _ms(samples: int, sample_rate: int) -> int:
    return int(round(1000 * samples / sample_rate))


def build_timeline(db: sqlite3.Connection, book_id: str, work_dir: str,
                   *, sample_rate: int = SAMPLE_RATE) -> Timeline:
    rows = db.execute(
        """
        SELECT s.*, c.title AS chapter_title
        FROM segments s JOIN chapters c
          ON c.book_id = s.book_id AND c.chapter_idx = s.chapter_idx
        WHERE s.book_id=? AND s.status='done'
        ORDER BY s.chapter_idx, s.seg_idx
        """,
        (book_id,),
    ).fetchall()

    silences: dict[int, tuple[str, int]] = {}

    def silence(ms: int) -> tuple[str, int]:
        if ms not in silences:
            path, n = ensure_silence(work_dir, ms, sample_rate=sample_rate)
            silences[ms] = (str(path), n)
        return silences[ms]

    entries: list[TimelineEntry] = []
    spans: list[ChapterSpan] = []
    cum = 0
    current: int | None = None
    current_title = ""
    span_start = 0

    def ms(samples: int) -> int:
        return _ms(samples, sample_rate)

    for row in rows:
        if row["chapter_idx"] != current:
            if current is not None:
                spans.append(ChapterSpan(chapter_idx=current, title=current_title,
                                         start_ms=ms(span_start), end_ms=ms(cum)))
            current = row["chapter_idx"]
            current_title = row["chapter_title"] or ""
            span_start = cum
        entries.append(TimelineEntry(path=row["audio_path"], n_samples=row["n_samples"],
                                     kind="title" if row["seg_idx"] == -1 else "body",
                                     chapter_idx=current))
        cum += int(row["n_samples"])
        sil_path, sil_n = silence(int(row["pause_after_ms"] or 0))
        if sil_n > 0:
            entries.append(TimelineEntry(path=sil_path, n_samples=sil_n, kind="silence",
                                         chapter_idx=current))
            cum += sil_n
    if current is not None:
        spans.append(ChapterSpan(chapter_idx=current, title=current_title,
                                 start_ms=ms(span_start), end_ms=ms(cum)))
    return Timeline(entries=entries, spans=spans, sample_rate=sample_rate)


def build_concat_list(entries: list[TimelineEntry]) -> str:
    """Only ``file`` lines, absolute paths, shell-style ``'\\''`` escaping."""

    lines: list[str] = []
    for entry in entries:
        escaped = entry.path.replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def build_ffmeta(spans: list[ChapterSpan], *, title: str, artist: str = "epub2m4b",
                 language: str = "zho") -> str:
    def esc(value: str) -> str:
        return (value.replace("\\", "\\\\").replace("\n", "\\n")
                .replace("=", "\\=").replace(";", "\\;").replace("#", "\\#"))

    lines = [";FFMETADATA1", f"title={esc(title)}", f"artist={esc(artist)}",
             f"album={esc(title)}", f"language={language}"]
    for span in spans:
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={span.start_ms}",
            f"END={span.end_ms}",
            f"title={esc(span.title)}",
        ]
    return "\n".join(lines) + "\n"
