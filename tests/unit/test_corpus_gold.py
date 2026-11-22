from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from soundbook import PIPELINE_VERSION


_CORPUS_TEST = Path(__file__).parents[1] / "corpus" / "test_corpus.py"
_spec = importlib.util.spec_from_file_location("corpus_gold_under_test", _CORPUS_TEST)
assert _spec is not None and _spec.loader is not None
corpus_gold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus_gold)


def test_gold_accepts_matching_pipeline_and_inline_comments(tmp_path):
    book = tmp_path / "book.epub"
    book.touch()
    book.with_suffix(".boundaries").write_text(
        f"# pipeline {PIPELINE_VERSION}\n"
        "OEBPS/Text/ch1.xhtml|0 # 第一章\n"
        "OEBPS/Text/ch2.xhtml|3# 第二章\n"
        "# another comment\n",
        encoding="utf-8",
    )
    assert corpus_gold._gold_for(book) == [
        "OEBPS/Text/ch1.xhtml|0",
        "OEBPS/Text/ch2.xhtml|3",
    ]


def test_gold_skips_different_pipeline_version(tmp_path):
    book = tmp_path / "book.epub"
    book.touch()
    book.with_suffix(".boundaries").write_text(
        "# pipeline 0.0.0\nOEBPS/Text/ch1.xhtml|0\n", encoding="utf-8"
    )
    with pytest.raises(pytest.skip.Exception, match="gold pipeline 0.0.0"):
        corpus_gold._gold_for(book)


def test_gold_without_version_is_current_version(tmp_path):
    book = tmp_path / "book.epub"
    book.touch()
    book.with_suffix(".boundaries").write_text(
        "OEBPS/Text/ch1.xhtml|0\n", encoding="utf-8"
    )
    assert corpus_gold._gold_for(book) == ["OEBPS/Text/ch1.xhtml|0"]
