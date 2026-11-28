from __future__ import annotations

import time

import pytest

from soundbook.db import connect, replace_chapters
from soundbook.models import ChapterDraft


def _draft(idx: int, title: str = "") -> ChapterDraft:
    return ChapterDraft(
        idx=idx,
        title=title or f"第{idx + 1}章",
        paragraphs=("正文。" * 20,),
        strategy="nav",
        start_key=f"OEBPS/Text/ch{idx + 1}.xhtml|0",
        end_key=None,
    )


def _insert_segment(db, book_id: str, chapter_idx: int, seg_idx: int,
                    status: str = "done") -> None:
    db.execute(
        """
        INSERT INTO segments (book_id, chapter_idx, seg_idx, text, text_sha256,
                              audio_key, synth_fp, audio_path, n_samples, status,
                              updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (book_id, chapter_idx, seg_idx, "正文。", "sha", f"key-{chapter_idx}-{seg_idx}",
         "fp", f"/cache/{chapter_idx}-{seg_idx}.flac", 100, status, time.time()),
    )


@pytest.fixture()
def db():
    connection = connect(":memory:")
    yield connection
    connection.close()


def test_replace_chapters_prunes_segments_of_removed_chapters(db):
    book_id = "book"
    replace_chapters(db, book_id, [_draft(0), _draft(1), _draft(2)])
    for idx in range(3):
        _insert_segment(db, book_id, idx, 0)
    db.commit()

    # A later chaptering run produced fewer chapters (e.g. dedupe/merge).
    replace_chapters(db, book_id, [_draft(0), _draft(1)])

    rows = db.execute(
        "SELECT chapter_idx FROM segments WHERE book_id=? ORDER BY chapter_idx",
        (book_id,)).fetchall()
    assert [r["chapter_idx"] for r in rows] == [0, 1]


def test_replace_chapters_keeps_segments_of_surviving_chapters(db):
    book_id = "book"
    replace_chapters(db, book_id, [_draft(0), _draft(1)])
    _insert_segment(db, book_id, 0, 0)
    _insert_segment(db, book_id, 1, 0)
    db.commit()

    replace_chapters(db, book_id, [_draft(0), _draft(1, "改了标题")])

    assert db.execute(
        "SELECT COUNT(*) AS n FROM segments WHERE book_id=?", (book_id,)
    ).fetchone()["n"] == 2
