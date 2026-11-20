from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from soundbook.cli import cli

pytestmark = pytest.mark.e2e

LONG = ("这一章的内容足够长，不会被当成前言或后记，因此一定会被合成。"
        "山风穿过松林，发出低沉的声响，像是有人在远处低声说话。" * 12)


def _invoke(args, home):
    runner = CliRunner()
    return runner.invoke(cli, args,
                         env={"SOUNDBOOK_HOME": str(home / "home"),
                              "SOUNDBOOK_CACHE_DIR": str(home / "cache")},
                         catch_exceptions=False)


def _unresolved_book(home):
    """4 chapters; the nav entry for ch3 carries a fragment no path can place."""
    from helpers import Chapter, make_epub

    chapters = [Chapter(f"第{i + 1}章 山与海", [LONG, LONG]) for i in range(4)]
    return make_epub(
        home / "anchor.epub", chapters,
        nav_entries=[("第1章", "Text/ch1.xhtml"),
                     ("第2章", "Text/ch2.xhtml"),
                     ("不存在的标题", "Text/ch3.xhtml#nope"),
                     ("第4章", "Text/ch4.xhtml")])


def test_inspect_text_reports_anchor_warnings_not_rejections(home):
    book = _unresolved_book(home)
    result = _invoke(["inspect", str(book)], home)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert any(line.strip().startswith("warnings") for line in lines), result.output
    assert "anchor_unresolved" in result.output
    assert "cut at document start" in result.output
    # a degraded cut is not a vetoed strategy: it must not appear on `rejected`
    for line in lines:
        if line.strip().startswith("rejected"):
            assert "anchor_" not in line, line


def test_inspect_json_keeps_anchor_records_in_rejected_and_warnings(home):
    book = _unresolved_book(home)
    result = _invoke(["inspect", "--json", str(book)], home)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "nav"
    flagged = [c for c in payload["chapters"]
               if any(w.startswith("anchor_") for w in c["warnings"])]
    assert len(flagged) == 1
    chapter = flagged[0]
    assert any(r["reason"] == "anchor_unresolved" for r in chapter["rejected"])
    assert chapter["start_key"].endswith("ch3.xhtml|0")
    clean = [c for c in payload["chapters"] if c is not chapter]
    assert all(not any(w.startswith("anchor_") for w in c["warnings"]) for c in clean)
