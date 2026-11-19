from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner

from soundbook.cli import cli

pytestmark = pytest.mark.e2e

need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                 reason="ffmpeg not installed")

LONG = ("这一章的内容足够长，不会被当成前言或后记，因此一定会被合成。"
        "山风穿过松林，发出低沉的声响，像是有人在远处低声说话。" * 12)


def _invoke(args, home):
    runner = CliRunner()
    return runner.invoke(cli, args,
                         env={"SOUNDBOOK_HOME": str(home / "home"),
                              "SOUNDBOOK_CACHE_DIR": str(home / "cache")},
                         catch_exceptions=False)


@need_ffmpeg
def test_unicode_space_and_colon_paths(home):
    """Chinese names, spaces and colons must survive argv, ffmpeg and ffmeta."""

    from helpers import Chapter, make_epub

    book = make_epub(
        home / "中文 目录: 第一辑" / "风雪 夜归人：测试版.epub",
        [Chapter(f"第{i + 1}章 山与海", [LONG, LONG]) for i in range(4)],
    )
    out = home / "输出 目录: 成品" / "我的 有声书：第一卷.m4b"

    result = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert result.exit_code == 0, result.output
    assert out.is_file()

    from soundbook.assemble.m4b import probe_chapters

    chapters = probe_chapters(out)
    assert len(chapters) == 4
    assert chapters[0]["tags"]["title"].startswith("第1章")


@need_ffmpeg
def test_book_path_with_apostrophe(home):
    from helpers import Chapter, make_epub

    book = make_epub(home / "O'Brien 的书.epub",
                     [Chapter("第一章 起点", [LONG, LONG]) for _ in range(3)])
    out = home / "O'Brien 成品.m4b"
    result = _invoke(["run", str(book), "--tts", "fake", "-o", str(out)], home)
    assert result.exit_code == 0, result.output
    assert out.is_file()
