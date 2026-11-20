"""Orchestration: parse → chapter → clean → segment → synthesise → assemble.

The main thread owns SQLite; synthesis workers only produce PCM + FLAC and
report back (plan stage 2 step 10, stage 3 step 16/18).  ``inspect`` and ``run``
share :func:`prepare`, so a later ``run`` cannot invent a different chaptering
than the one ``inspect`` already wrote to the database (§3.7).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from soundbook.assemble.m4b import AssembleResult, assemble_m4b
from soundbook.config import Policies, audio_key as make_audio_key
from soundbook.config import cache_dir, work_dir
from soundbook.db import (
    book_complete,
    mark_done,
    mark_failed,
    pending_segments,
    reconcile_segments,
    replace_chapters,
    save_artifact,
    set_book_meta,
    upsert_book,
)
from soundbook.ingest.chaptering import choose_strategy
from soundbook.ingest.classify import classify_skippable
from soundbook.ingest.clean import clean_paragraphs, repeated_headers, warnings_for_chapter
from soundbook.ingest.loader import ParsedBook, load_book
from soundbook.models import ChapterDraft, SegmentDraft
from soundbook.segment.segmenter import segment_chapter
from soundbook.tts.base import synth_fingerprint_for
from soundbook.util.audio import flac_total_samples, pcm_to_flac
from soundbook.util.disk import check_space


ANCHOR_REASON_PREFIX = "anchor_"


def anchor_warnings(draft: ChapterDraft) -> list[str]:
    """Format ADR-015 path C records as human-readable chapter warnings."""

    out: list[str] = []
    for rej in draft.rejected:
        if not rej.reason.startswith(ANCHOR_REASON_PREFIX):
            continue
        m = rej.metrics
        text = f"{rej.reason}: {m.get('label', '')} ({m.get('href', '')}#{m.get('anchor', '')})"
        if rej.reason == "anchor_unresolved":
            text += ", cut at document start"
        out.append(text)
    return out


@dataclass
class ChapterPlan:
    draft: ChapterDraft
    cleaned: list[str]
    segments: list[SegmentDraft]
    warnings: list[str] = field(default_factory=list)


@dataclass
class Prepared:
    book: ParsedBook
    strategy: str
    chapters: list[ChapterPlan]

    @property
    def n_segments(self) -> int:
        return sum(len(c.segments) for c in self.chapters)


def prepare(
    db: sqlite3.Connection,
    path: str | Path,
    policies: Policies,
    *,
    include_skippable: bool = False,
    write_segments: bool = True,
    synth_fp: str | None = None,
) -> Prepared:
    book = load_book(path)
    upsert_book(db, book.info, status="parsing")
    set_book_meta(db, book.info.book_id, status="parsing")

    strategy, drafts = choose_strategy(book, policies.chaptering)
    classify_skippable(drafts, policies.chaptering)
    replace_chapters(db, book.info.book_id, drafts)

    all_paragraphs = [p for draft in drafts for p in draft.paragraphs]
    drops = repeated_headers(all_paragraphs, policies.clean)

    plans: list[ChapterPlan] = []
    for draft in drafts:
        cleaned = clean_paragraphs(draft.paragraphs, policies.clean, drop=drops)
        segments: list[SegmentDraft] = []
        if include_skippable or not draft.skippable:
            segments = segment_chapter(draft, policies.segment, cleaned_paragraphs=cleaned)
        warnings: list[str] = []
        warning = warnings_for_chapter(draft.char_count, len(draft.paragraphs), policies.clean)
        if warning:
            warnings.append(warning)
        warnings.extend(anchor_warnings(draft))
        plans.append(ChapterPlan(draft=draft, cleaned=cleaned, segments=segments,
                                 warnings=warnings))

    if write_segments and synth_fp is not None:
        for plan in plans:
            reconcile_segments(db, book.info.book_id, plan.draft.idx, plan.segments,
                               synth_fp, make_audio_key)
    set_book_meta(db, book.info.book_id, strategy=strategy, n_chapters=len(drafts),
                  status="ready")
    db.commit()
    return Prepared(book=book, strategy=strategy, chapters=plans)


def verify_cached_segments(db: sqlite3.Connection, book_id: str) -> int:
    """Reset ``done`` rows whose FLAC vanished or lost samples (§3.6)."""

    reset = 0
    for row in db.execute(
        "SELECT chapter_idx, seg_idx, audio_path, n_samples FROM segments "
        "WHERE book_id=? AND status='done'", (book_id,)).fetchall():
        path = row["audio_path"]
        ok = bool(path) and Path(path).is_file()
        if ok:
            try:
                ok = flac_total_samples(path) == row["n_samples"]
            except Exception:
                ok = False
        if not ok:
            db.execute(
                "UPDATE segments SET status='pending', audio_path=NULL, n_samples=NULL "
                "WHERE book_id=? AND chapter_idx=? AND seg_idx=?",
                (book_id, row["chapter_idx"], row["seg_idx"]),
            )
            reset += 1
    db.commit()
    return reset


@dataclass
class SynthReport:
    total: int = 0
    done: int = 0
    cached: int = 0
    failed: list[tuple[int, int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def synthesize(
    db: sqlite3.Connection,
    book_id: str,
    *,
    backend_factory: Callable[[], object],
    synth_fp: str,
    jobs: int = 1,
    max_retries: int = 3,
    progress: Callable[[int, int], None] | None = None,
) -> SynthReport:
    rows = pending_segments(db, book_id)
    report = SynthReport(total=len(rows))
    if not rows:
        return report

    chars_pending = sum(len(r["text"]) for r in rows)
    chars_total = db.execute(
        "SELECT COALESCE(SUM(LENGTH(text)),0) AS n FROM segments WHERE book_id=?",
        (book_id,)).fetchone()["n"]
    check_space(cache_dir(), chars_pending, chars_total)

    local = threading.local()

    def backend():
        if not hasattr(local, "instance"):
            local.instance = backend_factory()
        return local.instance

    def work(row) -> dict:
        key = make_audio_key(row["text"], synth_fp)
        target = cache_dir() / key[:2] / f"{key}.flac"
        # A cached FLAC from an earlier run is reused verbatim: switching back
        # to a previous voice must cost zero synthesis (plan §5).
        if target.is_file():
            try:
                cached = flac_total_samples(target)
            except Exception:  # noqa: BLE001 - corrupted cache: overwrite it
                cached = None
            if cached:
                return {"row": row, "key": key, "path": str(target),
                        "n_samples": cached, "error": None, "cached": True}
        last_error = "unknown error"
        for attempt in range(max_retries):
            try:
                pcm = backend().synth(row["text"])
                expected = len(pcm) // 2
                if expected <= 0:
                    raise RuntimeError("backend returned no audio")
                pcm_to_flac(pcm, target, expected_samples=expected)
                got = flac_total_samples(target)
                if got != expected:
                    raise RuntimeError(f"FLAC sample mismatch: {got} != {expected}")
                return {"row": row, "key": key, "path": str(target),
                        "n_samples": expected, "error": None, "cached": False}
            except Exception as exc:  # noqa: BLE001 - reported, then retried
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt + 1 < max_retries:
                    time.sleep(min(2.0, 0.25 * (2 ** attempt)))
        return {"row": row, "key": key, "path": None, "n_samples": None,
                "error": last_error, "cached": False}

    try:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            futures = [pool.submit(work, row) for row in rows]
            for future in as_completed(futures):
                result = future.result()
                row = result["row"]
                if result["error"]:
                    mark_failed(db, book_id, row["chapter_idx"], row["seg_idx"],
                                result["error"], terminal=True)
                    report.failed.append((row["chapter_idx"], row["seg_idx"],
                                          result["error"]))
                else:
                    mark_done(db, book_id, row["chapter_idx"], row["seg_idx"],
                              result["key"], result["path"], result["n_samples"])
                    report.done += 1
                    if result.get("cached"):
                        report.cached += 1
                db.commit()
                if progress:
                    progress(report.done + len(report.failed), report.total)
    except KeyboardInterrupt:  # pragma: no cover - CLI maps this to 130
        raise
    return report


def write_cover(book: ParsedBook, directory: str | Path) -> tuple[str, str] | None:
    """Persist the cover bytes next to the work files; return (path, sha256)."""

    if not book.cover_bytes:
        return None
    suffix = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get((book.cover_media_type or "").lower(), ".img")
    path = Path(directory) / f"cover{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.stat().st_size != len(book.cover_bytes):
        path.write_bytes(book.cover_bytes)
    return str(path), book.info.cover_sha256 or ""


def build_artifact(
    db: sqlite3.Connection,
    book: ParsedBook,
    *,
    policies: Policies,
    output: str | Path,
    allow_loudnorm: bool,
) -> AssembleResult:
    cover = write_cover(book, work_dir())
    result = assemble_m4b(
        db,
        book.info.book_id,
        title=book.info.title,
        output=output,
        work_dir=work_dir(),
        audio=policies.audio,
        cover_path=cover[0] if cover else None,
        cover_sha256=cover[1] if cover else None,
        allow_loudnorm=allow_loudnorm,
    )
    save_artifact(
        db,
        book.info.book_id,
        output_path=result.path,
        fingerprint=result.fingerprint,
        duration_ms=result.duration_ms,
        chapter_count=result.chapter_count,
        build_opts={
            "bitrate": policies.audio.bitrate,
            "sample_rate": policies.audio.sample_rate,
            "channels": policies.audio.channels,
            "language": policies.audio.language,
            "faststart": policies.audio.faststart,
            "loudnorm": policies.audio.loudnorm,
            "loudnorm_i": policies.audio.loudnorm_i,
            "loudnorm_tp": policies.audio.loudnorm_tp,
            "loudnorm_lra": policies.audio.loudnorm_lra,
            "cover_sha256": cover[1] if cover else None,
            "loudnorm_used": result.loudnorm_used,
            "content_sig": content_signature(db, book.info.book_id),
        },
    )
    db.commit()
    return result


def content_signature(db: sqlite3.Connection, book_id: str) -> str:
    """What the finished file contains, cheap to compute: ordered keys+samples."""

    import hashlib

    digest = hashlib.sha256()
    for row in db.execute(
        "SELECT chapter_idx, seg_idx, audio_key, n_samples, pause_after_ms "
        "FROM segments WHERE book_id=? AND status='done' ORDER BY chapter_idx, seg_idx",
        (book_id,)):
        digest.update(
            f"{row['chapter_idx']}|{row['seg_idx']}|{row['audio_key']}"
            f"|{row['n_samples']}|{row['pause_after_ms']}\n".encode("utf-8"))
    return digest.hexdigest()


def all_done(db: sqlite3.Connection, book_id: str) -> bool:
    return book_complete(db, book_id)


def synth_identity(backend, config) -> tuple[str, str]:
    info = backend.info()
    return synth_fingerprint_for(info, config), info.voice
