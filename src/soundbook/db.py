"""SQLite state: the schema from spec §5, plus reconciliation.

Concurrency model (plan stage 2 step 10): the main thread owns the database.
Workers never write; they return PCM and the main thread commits.  Book-level
mutual exclusion comes from a ``filelock`` taken by the CLI, not from SQLite.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from soundbook.models import BookInfo, ChapterDraft, SegmentDraft

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    book_id       TEXT PRIMARY KEY,
    path          TEXT NOT NULL,
    title         TEXT NOT NULL,
    language      TEXT,
    n_spine       INTEGER NOT NULL DEFAULT 0,
    n_chapters    INTEGER NOT NULL DEFAULT 0,
    strategy      TEXT,
    cover_sha256  TEXT,
    status        TEXT NOT NULL DEFAULT 'parsing',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    book_id       TEXT NOT NULL,
    chapter_idx   INTEGER NOT NULL,
    title         TEXT NOT NULL,
    strategy      TEXT NOT NULL,
    start_key     TEXT NOT NULL,
    end_key       TEXT,
    char_count    INTEGER NOT NULL,
    text_sha256   TEXT NOT NULL,
    skippable     INTEGER NOT NULL DEFAULT 0,
    rejected_json TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'pending',
    PRIMARY KEY (book_id, chapter_idx)
);
CREATE TABLE IF NOT EXISTS segments (
    book_id       TEXT NOT NULL,
    chapter_idx   INTEGER NOT NULL,
    seg_idx       INTEGER NOT NULL,
    text          TEXT NOT NULL,
    text_sha256   TEXT NOT NULL,
    audio_key     TEXT NOT NULL,
    synth_fp      TEXT NOT NULL,
    audio_path    TEXT,
    n_samples     INTEGER,
    pause_after_ms INTEGER NOT NULL DEFAULT 220,
    status        TEXT NOT NULL DEFAULT 'pending',
    attempts      INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    updated_at    REAL NOT NULL,
    PRIMARY KEY (book_id, chapter_idx, seg_idx)
);
CREATE TABLE IF NOT EXISTS artifacts (
    book_id       TEXT PRIMARY KEY,
    output_path   TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,
    duration_ms   INTEGER NOT NULL,
    chapter_count INTEGER NOT NULL,
    build_opts    TEXT NOT NULL DEFAULT '{}',
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_status
    ON segments (book_id, status, chapter_idx, seg_idx);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=30.0)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    return db


def upsert_book(db: sqlite3.Connection, info: BookInfo, *, status: str) -> None:
    now = time.time()
    db.execute(
        """
        INSERT INTO books (book_id, path, title, language, n_spine, cover_sha256,
                           status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(book_id) DO UPDATE SET
            path=excluded.path, title=excluded.title, language=excluded.language,
            n_spine=excluded.n_spine, cover_sha256=excluded.cover_sha256,
            updated_at=excluded.updated_at
        """,
        (info.book_id, info.path, info.title, info.language, info.n_spine,
         info.cover_sha256, status, now, now),
    )


def set_book_meta(db: sqlite3.Connection, book_id: str, *, strategy: str | None = None,
                  n_chapters: int | None = None, status: str | None = None) -> None:
    row = db.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    if row is None:
        return
    db.execute(
        "UPDATE books SET strategy=?, n_chapters=?, status=?, updated_at=? WHERE book_id=?",
        (
            strategy if strategy is not None else row["strategy"],
            n_chapters if n_chapters is not None else row["n_chapters"],
            status if status is not None else row["status"],
            time.time(),
            book_id,
        ),
    )


def replace_chapters(db: sqlite3.Connection, book_id: str,
                     drafts: list[ChapterDraft]) -> None:
    db.execute("DELETE FROM chapters WHERE book_id=?", (book_id,))
    for d in drafts:
        db.execute(
            """
            INSERT INTO chapters (book_id, chapter_idx, title, strategy, start_key,
                                  end_key, char_count, text_sha256, skippable,
                                  rejected_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (book_id, d.idx, d.title, d.strategy, d.start_key, d.end_key,
             d.char_count, d.text_sha256, int(d.skippable),
             json.dumps([r.as_dict() for r in d.rejected], ensure_ascii=False)),
        )
    db.execute(
        "UPDATE books SET n_chapters=?, updated_at=? WHERE book_id=?",
        (len(drafts), time.time(), book_id),
    )
    # Chapters that vanished (e.g. strategy switch shrinking the book) leave
    # orphaned segment rows that would otherwise be re-synthesized forever.
    # Their FLAC stays in the content-addressed cache, so deleting the rows
    # costs nothing if the same text comes back.
    db.execute(
        """
        DELETE FROM segments WHERE book_id=? AND chapter_idx NOT IN
            (SELECT chapter_idx FROM chapters WHERE book_id=?)
        """,
        (book_id, book_id),
    )


def get_chapters(db: sqlite3.Connection, book_id: str) -> list[sqlite3.Row]:
    return list(db.execute(
        "SELECT * FROM chapters WHERE book_id=? ORDER BY chapter_idx", (book_id,)))


def reconcile_segments(
    db: sqlite3.Connection,
    book_id: str,
    chapter_idx: int,
    drafts: list[SegmentDraft],
    synth_fp: str,
    key_fn,
) -> dict[str, int]:
    """Align the ``segments`` table with a fresh segmentation of one chapter.

    A segment row survives only when both its position and its text are
    unchanged; surviving rows keep ``done`` state and their FLAC unless the
    synth fingerprint changed.  Returns counts for reporting.
    """

    stats = {"kept": 0, "added": 0, "rekeyed": 0, "dropped": 0}
    existing = {
        row["seg_idx"]: row
        for row in db.execute(
            "SELECT * FROM segments WHERE book_id=? AND chapter_idx=?",
            (book_id, chapter_idx))
    }
    seen: set[int] = set()
    now = time.time()
    from soundbook.util.hashing import sha256_bytes

    for draft in drafts:
        text_sha = sha256_bytes(draft.text.encode("utf-8"))
        audio_key = key_fn(draft.text, synth_fp)
        seen.add(draft.seg_idx)
        row = existing.get(draft.seg_idx)
        if row is None:
            db.execute(
                """
                INSERT INTO segments (book_id, chapter_idx, seg_idx, text, text_sha256,
                                      audio_key, synth_fp, pause_after_ms, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (book_id, chapter_idx, draft.seg_idx, draft.text, text_sha,
                 audio_key, synth_fp, draft.pause_after_ms, now),
            )
            stats["added"] += 1
            continue
        if row["text_sha256"] == text_sha and row["synth_fp"] == synth_fp \
                and row["audio_key"] == audio_key \
                and row["pause_after_ms"] == draft.pause_after_ms:
            stats["kept"] += 1
            continue
        # Same position, changed text or voice: re-synthesize only this segment.
        db.execute(
            """
            UPDATE segments SET text=?, text_sha256=?, audio_key=?, synth_fp=?,
                   pause_after_ms=?, audio_path=NULL, n_samples=NULL,
                   status='pending', error=NULL, updated_at=?
            WHERE book_id=? AND chapter_idx=? AND seg_idx=?
            """,
            (draft.text, text_sha, audio_key, synth_fp, draft.pause_after_ms, now,
             book_id, chapter_idx, draft.seg_idx),
        )
        stats["rekeyed"] += 1
    for seg_idx in existing:
        if seg_idx not in seen:
            db.execute(
                "DELETE FROM segments WHERE book_id=? AND chapter_idx=? AND seg_idx=?",
                (book_id, chapter_idx, seg_idx),
            )
            stats["dropped"] += 1
    return stats


def pending_segments(db: sqlite3.Connection, book_id: str,
                     limit: int | None = None) -> list[sqlite3.Row]:
    # ``failed`` is retryable on the next run (spec §5: failed segments are the
    # minimal retry unit). A fresh ``prepare()`` only resets rows whose text or
    # synth fingerprint changed, so previously failed rows are picked up here.
    sql = ("SELECT * FROM segments WHERE book_id=? AND status IN ('pending','failed') "
           "ORDER BY chapter_idx, seg_idx")
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return list(db.execute(sql, (book_id,)))


def mark_done(db: sqlite3.Connection, book_id: str, chapter_idx: int, seg_idx: int,
              audio_key: str, audio_path: str, n_samples: int) -> None:
    db.execute(
        """
        UPDATE segments SET status='done', audio_key=?, audio_path=?, n_samples=?,
               error=NULL, attempts=attempts+1, updated_at=?
        WHERE book_id=? AND chapter_idx=? AND seg_idx=?
        """,
        (audio_key, audio_path, n_samples, time.time(), book_id, chapter_idx, seg_idx),
    )


def mark_failed(db: sqlite3.Connection, book_id: str, chapter_idx: int, seg_idx: int,
                error: str, *, terminal: bool) -> None:
    db.execute(
        """
        UPDATE segments SET status=?, error=?, attempts=attempts+1, updated_at=?
        WHERE book_id=? AND chapter_idx=? AND seg_idx=?
        """,
        ("failed" if terminal else "pending", error, time.time(),
         book_id, chapter_idx, seg_idx),
    )


def segment_counts(db: sqlite3.Connection, book_id: str) -> dict[str, int]:
    rows = db.execute(
        "SELECT status, COUNT(*) AS n FROM segments WHERE book_id=? GROUP BY status",
        (book_id,)).fetchall()
    return {row["status"]: row["n"] for row in rows}


def done_segments(db: sqlite3.Connection, book_id: str) -> list[sqlite3.Row]:
    return list(db.execute(
        """
        SELECT * FROM segments WHERE book_id=? AND status='done'
        ORDER BY chapter_idx, seg_idx
        """,
        (book_id,)))


def book_complete(db: sqlite3.Connection, book_id: str) -> bool:
    row = db.execute(
        "SELECT COUNT(*) AS n FROM segments WHERE book_id=? AND status!='done'",
        (book_id,)).fetchone()
    return row["n"] == 0 and db.execute(
        "SELECT COUNT(*) AS n FROM segments WHERE book_id=?", (book_id,)).fetchone()["n"] > 0


def failed_segments(db: sqlite3.Connection, book_id: str) -> list[sqlite3.Row]:
    return list(db.execute(
        "SELECT * FROM segments WHERE book_id=? AND status='failed' ORDER BY chapter_idx, seg_idx",
        (book_id,)))


def save_artifact(db: sqlite3.Connection, book_id: str, *, output_path: str,
                  fingerprint: str, duration_ms: int, chapter_count: int,
                  build_opts: dict) -> None:
    db.execute(
        """
        INSERT INTO artifacts (book_id, output_path, fingerprint, duration_ms,
                               chapter_count, build_opts, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(book_id) DO UPDATE SET
            output_path=excluded.output_path, fingerprint=excluded.fingerprint,
            duration_ms=excluded.duration_ms, chapter_count=excluded.chapter_count,
            build_opts=excluded.build_opts, created_at=excluded.created_at
        """,
        (book_id, output_path, fingerprint, duration_ms, chapter_count,
         json.dumps(build_opts, sort_keys=True, ensure_ascii=False), time.time()),
    )


def get_artifact(db: sqlite3.Connection, book_id: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM artifacts WHERE book_id=?", (book_id,)).fetchone()
