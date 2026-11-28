from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner

from soundbook.cli import cli

pytestmark = pytest.mark.e2e

need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                 reason="ffmpeg not installed")


def _invoke(args, home):
    runner = CliRunner()
    return runner.invoke(cli, args,
                         env={"SOUNDBOOK_HOME": str(home / "home"),
                              "SOUNDBOOK_CACHE_DIR": str(home / "cache")},
                         catch_exceptions=False)


class FlakyBackend:
    """Fake backend that always fails on a chosen paragraph."""

    def __init__(self, config=None) -> None:
        from soundbook.tts.fake import FakeBackend

        self._inner = FakeBackend(config)
        self.config = self._inner.config

    def info(self):
        return self._inner.info()

    def synth(self, text: str) -> bytes:
        if "引爆" in text:
            raise RuntimeError("synthetic engine failure")
        return self._inner.synth(text)


@need_ffmpeg
def test_segment_failure_marks_terminal_and_exits_2(home, monkeypatch):
    from helpers import Chapter, make_epub

    chapters = [
        Chapter(f"第{i + 1}章 测试",
                [f"第{i + 1}章正文第一段，这里写一些足够长的内容来避免被当成辅文。" * 12,
                 f"第{i + 1}章正文第二段，继续写足够长的内容以避免辅文判定。" * 12])
        for i in range(4)
    ]
    chapters[2].paragraphs[0] = "这一章会引爆引擎，合成必然失败，这里再加一些字让它足够长。" * 12
    book = make_epub(home / "flaky.epub", chapters)
    out = home / "flaky.m4b"

    monkeypatch.setattr("soundbook.tts.base.make_backend",
                        lambda name, config: FlakyBackend(config))

    result = _invoke(["run", str(book), "--tts", "fake", "-o", str(out),
                      "--max-retries", "1"], home)
    assert result.exit_code == 2, result.output
    assert "failed" in result.output
    assert not out.exists(), "without --allow-incomplete no M4B may be produced"

    # DB: exactly the failing segments are terminal, everything else is done.
    from soundbook.config import db_path
    from soundbook.db import connect
    from soundbook.util.hashing import sha256_file

    db = connect(db_path())
    book_id = sha256_file(book)
    rows = db.execute(
        "SELECT chapter_idx, seg_idx, status, error FROM segments WHERE book_id=? "
        "AND status='failed'", (book_id,)).fetchall()
    assert rows, "expected failed rows"
    assert all(r["chapter_idx"] == 2 for r in rows)
    assert all("synthetic engine failure" in r["error"] for r in rows)
    status = db.execute("SELECT status FROM books WHERE book_id=?",
                        (book_id,)).fetchone()["status"]
    assert status == "failed"
    db.close()


@need_ffmpeg
def test_allow_incomplete_packages_partial_book_and_still_exits_2(home, monkeypatch):
    from helpers import Chapter, make_epub

    chapters = [
        Chapter(f"第{i + 1}章 测试",
                [f"第{i + 1}章正文第一段，这里写一些足够长的内容来避免被当成辅文。" * 12,
                 f"第{i + 1}章正文第二段，继续写足够长的内容以避免辅文判定。" * 12])
        for i in range(4)
    ]
    chapters[1].paragraphs[1] = "这里也会引爆引擎，依然失败，这里再加一些字让它足够长。" * 12
    book = make_epub(home / "partial.epub", chapters)
    out = home / "partial.m4b"

    monkeypatch.setattr("soundbook.tts.base.make_backend",
                        lambda name, config: FlakyBackend(config))

    result = _invoke(["run", str(book), "--tts", "fake", "-o", str(out),
                      "--max-retries", "1", "--allow-incomplete"], home)
    assert result.exit_code == 2, result.output
    assert out.is_file(), "--allow-incomplete must still package the finished segments"
    assert "incomplete" in result.output

    from soundbook.assemble.m4b import probe_chapters

    probed = probe_chapters(out)
    # chapter 1 is fully done, chapter 2 lost its second paragraph but keeps
    # its title + first paragraph; all 4 chapters still have a timeline entry.
    assert len(probed) == 4


@need_ffmpeg
def test_failed_segment_is_retried_on_next_run(home, monkeypatch):
    """A transient failure must not poison the cache: next run succeeds."""

    from helpers import Chapter, make_epub

    chapters = [
        Chapter(f"第{i + 1}章 测试",
                [f"第{i + 1}章正文，这里写一些足够长的内容来避免被当成辅文。" * 12])
        for i in range(3)
    ]
    chapters[0].paragraphs[0] = "开头就引爆引擎，第一次必然失败，这里再加一些字让它足够长。" * 12
    book = make_epub(home / "retry.epub", chapters)
    out = home / "retry.m4b"

    monkeypatch.setattr("soundbook.tts.base.make_backend",
                        lambda name, config: FlakyBackend(config))
    first = _invoke(["run", str(book), "--tts", "fake", "-o", str(out),
                     "--max-retries", "1"], home)
    assert first.exit_code == 2

    # "Engine fixed": restore the real backend and rerun — everything completes.
    monkeypatch.undo()
    second = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert second.exit_code == 0, second.output
    assert out.is_file()

    from soundbook.db import connect
    from soundbook.util.hashing import sha256_file

    # monkeypatch.undo() restored the real env, so name this test's home
    # explicitly instead of asking config for the (now global) db path.
    db = connect(home / "home" / "state.sqlite")
    book_id = sha256_file(book)
    failed = db.execute(
        "SELECT COUNT(*) AS n FROM segments WHERE book_id=? AND status='failed'",
        (book_id,)).fetchone()["n"]
    assert failed == 0
    db.close()
