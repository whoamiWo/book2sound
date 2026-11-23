from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from soundbook import PIPELINE_VERSION
from soundbook.models import ChapterDraft


_CORPUS_TEST = Path(__file__).parents[1] / "corpus" / "test_corpus.py"
_spec = importlib.util.spec_from_file_location("corpus_gold_under_test", _CORPUS_TEST)
assert _spec is not None and _spec.loader is not None
corpus_gold = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus_gold)


def _book(tmp_path: Path, name: str, gold: str | None = None) -> Path:
    book = tmp_path / name
    book.touch()
    if gold is not None:
        book.with_suffix(".boundaries").write_text(gold, encoding="utf-8")
    return book


def _draft(idx: int, start_key: str, *, skippable: bool = False) -> ChapterDraft:
    return ChapterDraft(
        idx=idx,
        title=f"第{idx + 1}章",
        paragraphs=("正文",),
        strategy="nav",
        start_key=start_key,
        end_key=None,
        skippable=skippable,
    )


def _install_corpus(
    monkeypatch: pytest.MonkeyPatch,
    books: list[Path],
    drafts: list[ChapterDraft],
    *,
    f1: float = 1.0,
) -> None:
    monkeypatch.setattr(corpus_gold, "_books", lambda: books)
    monkeypatch.setattr(corpus_gold, "load_book", lambda _path: object())
    monkeypatch.setattr(corpus_gold, "choose_strategy", lambda *_args: ("nav", list(drafts)))
    monkeypatch.setattr(corpus_gold, "classify_skippable", lambda *_args: None)
    monkeypatch.setattr(corpus_gold, "boundary_f1", lambda *_args, **_kwargs: f1)
    monkeypatch.delenv("SOUNDBOOK_CORPUS_TOLERANCE", raising=False)
    monkeypatch.delenv("SOUNDBOOK_CORPUS_MIN_F1", raising=False)


def test_gold_accepts_matching_pipeline_and_inline_comments(tmp_path):
    book = _book(
        tmp_path,
        "book.epub",
        f"# pipeline {PIPELINE_VERSION}\n"
        "OEBPS/Text/ch1.xhtml|0 # 第一章\n"
        "OEBPS/Text/ch2.xhtml|3# 第二章\n"
        "# another comment\n",
    )
    assert corpus_gold._gold_for(book) == ([
        "OEBPS/Text/ch1.xhtml|0",
        "OEBPS/Text/ch2.xhtml|3",
    ], None)


def test_gold_reports_different_pipeline_version_without_raising(tmp_path):
    book = _book(
        tmp_path,
        "book.epub",
        "# pipeline 0.0.0\nOEBPS/Text/ch1.xhtml|0\n",
    )
    boundaries, reason = corpus_gold._gold_for(book)
    assert boundaries == []
    assert reason == f"gold pipeline 0.0.0 != current {PIPELINE_VERSION}"


def test_gold_without_version_is_current_version(tmp_path):
    book = _book(tmp_path, "book.epub", "OEBPS/Text/ch1.xhtml|0\n")
    assert corpus_gold._gold_for(book) == (["OEBPS/Text/ch1.xhtml|0"], None)


def test_missing_gold_is_reported_not_raised(tmp_path):
    book = _book(tmp_path, "book.epub")
    assert corpus_gold._gold_for(book) == ([], "no .boundaries file")


def test_empty_gold_is_distinct_from_missing_gold(tmp_path):
    book = _book(tmp_path, "book.epub", f"# pipeline {PIPELINE_VERSION}\n# no boundaries yet\n")
    assert corpus_gold._gold_for(book) == ([], None)


def test_skippable_marker_is_excluded_from_gold_boundaries(tmp_path):
    book = _book(
        tmp_path,
        "book.epub",
        f"# pipeline {PIPELINE_VERSION}\n"
        "OEBPS/Text/contents.xhtml|0 # 目录 [skippable]\n"
        "OEBPS/Text/ch1.xhtml|0 # 第一章\n",
    )
    assert corpus_gold._gold_for(book) == (["OEBPS/Text/ch1.xhtml|0"], None)


def test_mixed_versions_skip_only_the_stale_book(
    tmp_path, monkeypatch, capsys
):
    stale = _book(tmp_path, "stale.epub", "# pipeline 0.0.0\nOEBPS/Text/ch1.xhtml|0\n")
    current = _book(
        tmp_path,
        "current.epub",
        f"# pipeline {PIPELINE_VERSION}\nOEBPS/Text/ch1.xhtml|0\n",
    )
    _install_corpus(
        monkeypatch,
        [stale, current],
        [_draft(0, "OEBPS/Text/ch1.xhtml|0")],
    )

    corpus_gold.test_corpus_boundary_f1_meets_gate()

    output = capsys.readouterr().out
    assert "stale.epub: skipped (gold pipeline 0.0.0" in output
    assert "current.epub: strategy=nav" in output
    assert "summary: books=1" in output


def test_all_stale_versions_skip_whole_test(tmp_path, monkeypatch):
    stale = [
        _book(tmp_path, f"stale{idx}.epub", "# pipeline 0.0.0\nOEBPS/Text/ch1.xhtml|0\n")
        for idx in range(2)
    ]
    _install_corpus(monkeypatch, stale, [_draft(0, "OEBPS/Text/ch1.xhtml|0")])

    with pytest.raises(pytest.skip.Exception, match="no scoreable gold files"):
        corpus_gold.test_corpus_boundary_f1_meets_gate()


def test_no_gold_files_skip_whole_test(tmp_path, monkeypatch):
    _install_corpus(
        monkeypatch,
        [_book(tmp_path, "unannotated.epub")],
        [_draft(0, "OEBPS/Text/ch1.xhtml|0")],
    )

    with pytest.raises(pytest.skip.Exception, match="no scoreable gold files"):
        corpus_gold.test_corpus_boundary_f1_meets_gate()


def test_empty_gold_file_fails(tmp_path, monkeypatch):
    book = _book(tmp_path, "empty.epub", f"# pipeline {PIPELINE_VERSION}\n# only a comment\n")
    _install_corpus(monkeypatch, [book], [_draft(0, "OEBPS/Text/ch1.xhtml|0")])

    with pytest.raises(pytest.fail.Exception, match="gold file has no chapter boundaries"):
        corpus_gold.test_corpus_boundary_f1_meets_gate()


def test_unset_min_f1_only_prints_and_set_min_f1_enforces(
    tmp_path, monkeypatch, capsys
):
    book = _book(
        tmp_path,
        "book.epub",
        f"# pipeline {PIPELINE_VERSION}\nOEBPS/Text/ch1.xhtml|0\n",
    )
    _install_corpus(monkeypatch, [book], [_draft(0, "OEBPS/Text/ch1.xhtml|0")], f1=0.0)

    corpus_gold.test_corpus_boundary_f1_meets_gate()
    assert "gate: disabled" in capsys.readouterr().out

    monkeypatch.setenv("SOUNDBOOK_CORPUS_MIN_F1", "0.9")
    with pytest.raises(AssertionError, match="worst book book.epub"):
        corpus_gold.test_corpus_boundary_f1_meets_gate()


def test_skippable_chapters_are_classified_and_excluded(
    tmp_path, monkeypatch, capsys
):
    book = _book(
        tmp_path,
        "book.epub",
        f"# pipeline {PIPELINE_VERSION}\nOEBPS/Text/body.xhtml|0\n",
    )
    drafts = [
        _draft(0, "OEBPS/Text/body.xhtml|0"),
        _draft(1, "OEBPS/Text/copyright.xhtml|0"),
    ]
    calls: list[str] = []
    predicted: list[str] = []

    monkeypatch.setattr(corpus_gold, "_books", lambda: [book])
    monkeypatch.setattr(corpus_gold, "load_book", lambda _path: object())

    def choose(_book, _policy):
        calls.append("choose")
        return "nav", drafts

    def classify(items, _policy):
        calls.append("classify")
        items[1].skippable = True

    def score(items, _gold, *, tolerance_blocks):
        predicted.extend(items)
        return 1.0

    monkeypatch.setattr(corpus_gold, "choose_strategy", choose)
    monkeypatch.setattr(corpus_gold, "classify_skippable", classify)
    monkeypatch.setattr(corpus_gold, "boundary_f1", score)
    monkeypatch.delenv("SOUNDBOOK_CORPUS_MIN_F1", raising=False)

    corpus_gold.test_corpus_boundary_f1_meets_gate()

    assert calls == ["choose", "classify"]
    assert predicted == ["OEBPS/Text/body.xhtml|0"]
    output = capsys.readouterr().out
    assert "skippable=1 gold=1" in output
