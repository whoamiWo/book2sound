from __future__ import annotations

from soundbook.config import ChapteringPolicy
from soundbook.ingest.chaptering import choose_strategy
from soundbook.ingest.classify import classify_skippable
from soundbook.ingest.loader import load_book
from helpers import Chapter, CHINESE_PARAGRAPHS, make_epub, simple_book


def test_nav_strategy_on_clean_book(tmp_path):
    book = load_book(simple_book(tmp_path / "b.epub"))
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    assert strategy == "nav"
    assert len(drafts) == 5
    assert drafts[0].title == "第1章 风雪夜归人"
    assert drafts[0].start_key.startswith("OEBPS/Text/ch1.xhtml|")


def test_start_keys_are_monotonic_and_cover_book(tmp_path):
    book = load_book(simple_book(tmp_path / "b.epub"))
    _, drafts = choose_strategy(book, ChapteringPolicy())
    keys = [d.start_key for d in drafts]
    assert keys == sorted(keys, key=lambda k: key_order(k))
    assert len(set(keys)) == len(keys)
    assert drafts[0].end_key == drafts[1].start_key


def key_order(key: str):
    href, block = key.rsplit("|", 1)
    return (href, int(block))


def test_fragment_nav_cuts_inside_document(tmp_path):
    chapters = [Chapter(f"第{i + 1}章 标题", CHINESE_PARAGRAPHS[:6]) for i in range(4)]
    chapters[1].anchor = "half"
    chapters[1].anchor_paragraph = 3
    make_epub(tmp_path / "f.epub", chapters,
              nav_entries=[("第1章", "Text/ch1.xhtml"),
                           ("第2章", "Text/ch2.xhtml"),
                           ("第2章后半", "Text/ch2.xhtml#half"),
                           ("第3章", "Text/ch3.xhtml"),
                           ("第4章", "Text/ch4.xhtml")])
    book = load_book(tmp_path / "f.epub")
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    assert strategy == "nav"
    assert len(drafts) == 5
    assert drafts[2].start_key == "OEBPS/Text/ch2.xhtml|4"  # p#half after dedupe
    assert drafts[2].title == "第2章后半"
    assert drafts[1].end_key == drafts[2].start_key


def test_no_nav_falls_back(tmp_path):
    chapters = [Chapter(f"第{i + 1}章", CHINESE_PARAGRAPHS[:6]) for i in range(4)]
    make_epub(tmp_path / "nonav.epub", chapters, nav_entries=[])
    book = load_book(tmp_path / "nonav.epub")
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    assert strategy in {"nav", "outline", "spine"}
    assert len(drafts) == 4
    # epubx synthesizes spine hrefs when there is no nav: those labels must be
    # replaced by the document headings, not "ch1.xhtml".
    assert all(".xhtml" not in d.title for d in drafts)


def test_dominant_chapter_vetoes_nav(tmp_path):
    chapters = [
        Chapter("第1章 短", CHINESE_PARAGRAPHS[:1]),
        Chapter("第2章 长", CHINESE_PARAGRAPHS * 80),
    ]
    make_epub(tmp_path / "dom.epub", chapters)
    book = load_book(tmp_path / "dom.epub")
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    reasons = {r.reason for d in drafts for r in d.rejected}
    assert "dominant_chapter" in reasons
    assert strategy in {"nav", "outline", "spine"}


def test_front_matter_flagged(tmp_path):
    chapters = [
        Chapter("目录", CHINESE_PARAGRAPHS[:2]),
        Chapter("序言", CHINESE_PARAGRAPHS[:2]),
    ] + [Chapter(f"第{i}章", CHINESE_PARAGRAPHS * 6) for i in range(2, 12)]
    make_epub(tmp_path / "fm.epub", chapters)
    book = load_book(tmp_path / "fm.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    classify_skippable(drafts, ChapteringPolicy())
    assert drafts[0].skippable is True   # 目录
    assert drafts[1].skippable is True   # 序言
    assert not any(d.skippable for d in drafts[2:])
