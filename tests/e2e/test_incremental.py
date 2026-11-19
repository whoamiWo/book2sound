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


def _edit_chapter(path, *, chapter: int, old: str, new: str) -> None:
    """Rewrite one chapter inside the EPUB, preserving everything else."""

    import zipfile

    from helpers import _xhtml  # type: ignore[attr-defined]

    src = path
    tmp = path.with_suffix(".tmp.epub")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == f"OEBPS/Text/ch{chapter}.xhtml":
                text = data.decode("utf-8")
                assert old in text, "expected the original paragraph in the chapter"
                data = text.replace(old, new).encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(src)


@need_ffmpeg
def test_single_chapter_edit_recomputes_only_that_chapter(home, monkeypatch):
    """Plan §4: a text change must invalidate only the affected segments."""

    from helpers import Chapter, make_epub

    chapters = [
        Chapter(f"第{i + 1}章 雪", [f"第{i + 1}章第一段，风雪很大。" * 4,
                                   f"第{i + 1}章第二段，山路很滑。" * 4])
        for i in range(5)
    ]
    book = make_epub(home / "edit.epub", chapters)
    out = home / "edit.m4b"

    calls: list[str] = []
    from soundbook.tts.fake import FakeBackend

    original_synth = FakeBackend.synth

    def counting_synth(self, text):
        calls.append(text)
        return original_synth(self, text)

    monkeypatch.setattr(FakeBackend, "synth", counting_synth)

    first = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert first.exit_code == 0, first.output
    first_count = len(calls)
    assert first_count > 0

    calls.clear()
    second = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert second.exit_code == 0, second.output
    assert calls == [], f"cached run must not synthesize, got {len(calls)} calls"

    # Edit chapter 3 only: the book_id changes, so the whole book is re-parsed,
    # but only chapter 3's segments get new audio keys.
    _edit_chapter(book, chapter=3,
                  old="第3章第一段，风雪很大。" * 4,
                  new="第3章第一段，雪已经停了。" * 4)
    calls.clear()
    third = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert third.exit_code == 0, third.output
    assert 0 < len(calls) < first_count, (
        f"expected only chapter 3 to be re-synthesized, got {len(calls)} of {first_count}")
    assert all("第3章" in text or "雪已经停了" in text for text in calls), (
        "synthesis calls must be confined to the edited chapter")
