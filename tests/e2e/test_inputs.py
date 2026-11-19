from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner

from soundbook.cli import cli

pytestmark = pytest.mark.e2e

need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                 reason="ffmpeg not installed")

LONG = ("这是一段足够长的正文，用来确保章节不会被误判为辅文。"
        "风雪中他独自前行，脚下的积雪发出咯吱咯吱的声响。" * 12)


def _invoke(args, home):
    runner = CliRunner()
    return runner.invoke(cli, args,
                         env={"SOUNDBOOK_HOME": str(home / "home"),
                              "SOUNDBOOK_CACHE_DIR": str(home / "cache")},
                         catch_exceptions=False)


@need_ffmpeg
def test_real_drm_exits_3(home):
    from helpers import REAL_DRM, Chapter, make_epub

    book = make_epub(home / "drm.epub",
                     [Chapter("第一章 加密", [LONG, LONG])],
                     encryption_xml=REAL_DRM)
    result = _invoke(["inspect", str(book)], home)
    assert result.exit_code == 3, result.output

    result = _invoke(["run", str(book), "--tts", "fake"], home)
    assert result.exit_code == 3, result.output


@need_ffmpeg
def test_font_obfuscation_is_usable(home):
    from helpers import FONT_ENCRYPTION, Chapter, make_epub

    book = make_epub(home / "fonts.epub",
                     [Chapter(f"第{i + 1}章 字体混淆", [LONG, LONG]) for i in range(4)],
                     encryption_xml=FONT_ENCRYPTION)
    inspect = _invoke(["inspect", str(book), "--json"], home)
    assert inspect.exit_code == 0, inspect.output

    import json

    payload = json.loads(inspect.output)
    assert payload["obfuscated_fonts"], "font obfuscation must be reported"

    out = home / "fonts.m4b"
    result = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert result.exit_code == 0, result.output
    assert out.is_file()


@need_ffmpeg
def test_image_only_book_exits_3(home):
    from helpers import Chapter, make_epub

    book = make_epub(home / "scan.epub",
                     [Chapter("扫描页", ["ignored"]) for _ in range(3)],
                     image_only=True)
    result = _invoke(["inspect", str(book)], home)
    assert result.exit_code == 3, result.output


@need_ffmpeg
def test_not_an_epub_exits_3(home):
    bogus = home / "not-a-book.epub"
    bogus.write_text("this is not a zip file", encoding="utf-8")
    result = _invoke(["inspect", str(bogus)], home)
    assert result.exit_code == 3, result.output
