from __future__ import annotations

import time
from pathlib import Path

import pytest

from soundbook.assemble.concat import Timeline, build_timeline
from soundbook.assemble.silence import samples_for_ms
from soundbook.db import connect, replace_chapters
from soundbook.models import ChapterDraft, TimelineEntry


def _draft(idx: int) -> ChapterDraft:
    return ChapterDraft(
        idx=idx,
        title=f"第{idx + 1}章",
        paragraphs=("正文。" * 20,),
        strategy="nav",
        start_key=f"OEBPS/Text/ch{idx + 1}.xhtml|0",
        end_key=None,
    )


def _insert_segment(db, book_id: str, chapter_idx: int, seg_idx: int,
                    n_samples: int, pause_after_ms: int) -> None:
    db.execute(
        """
        INSERT INTO segments (book_id, chapter_idx, seg_idx, text, text_sha256,
                              audio_key, synth_fp, audio_path, n_samples,
                              pause_after_ms, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'done', ?)
        """,
        (book_id, chapter_idx, seg_idx, "正文。", "sha", f"k-{chapter_idx}-{seg_idx}",
         "fp", f"/cache/{chapter_idx}-{seg_idx}.flac", n_samples,
         pause_after_ms, time.time()),
    )


def _timeline_db(chapters: int = 2) -> tuple:
    db = connect(":memory:")
    book_id = "book"
    replace_chapters(db, book_id, [_draft(i) for i in range(chapters)])
    for idx in range(chapters):
        _insert_segment(db, book_id, idx, -1, 4_800, 0)
        _insert_segment(db, book_id, idx, 0, 24_000, 0)
    db.commit()
    return db, book_id


@pytest.fixture()
def no_silence(monkeypatch):
    def fake_ensure_silence(work_dir, ms, *, sample_rate=24_000):
        return Path(work_dir) / f"silence-{ms}.flac", samples_for_ms(ms, sample_rate)

    monkeypatch.setattr("soundbook.assemble.concat.ensure_silence", fake_ensure_silence)


def test_total_ms_uses_the_timeline_sample_rate(tmp_path, no_silence):
    db, book_id = _timeline_db()
    try:
        timeline = build_timeline(db, book_id, str(tmp_path), sample_rate=48_000)
    finally:
        db.close()

    # 2 chapters × (4800 title + 24000 body) = 57,600 samples @ 48 kHz = 1200 ms
    assert timeline.sample_rate == 48_000
    assert timeline.total_samples == 57_600
    assert timeline.total_ms == 1_200
    assert timeline.spans[-1].end_ms == 1_200


def test_chapter_pause_belongs_to_the_previous_span(tmp_path, no_silence):
    db, book_id = _timeline_db(chapters=1)
    db.execute("UPDATE segments SET pause_after_ms=1200 WHERE book_id=? AND seg_idx=0",
               (book_id,))
    db.commit()
    try:
        timeline = build_timeline(db, book_id, str(tmp_path), sample_rate=24_000)
    finally:
        db.close()

    # title 4800 + body 24000 + 1200 ms (28800 samples) = 57600 → 2400 ms
    assert timeline.total_ms == 2_400
    assert timeline.spans[0].start_ms == 0
    assert timeline.spans[0].end_ms == 2_400


def test_timeline_default_rate_is_24k():
    entry = TimelineEntry(path="/x.flac", n_samples=24_000, kind="body")
    assert Timeline(entries=[entry], spans=[]).total_ms == 1_000
