from __future__ import annotations

from helpers import CHINESE_PARAGRAPHS, Chapter, make_epub, simple_book

from soundbook.config import ChapteringPolicy
from soundbook.ingest.chaptering import choose_strategy
from soundbook.ingest.classify import classify_skippable
from soundbook.ingest.loader import load_book


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


def test_non_reading_pages_skipped_outside_front_window(tmp_path):
    # Regression: 目录/版权页 often sit just past idx 2; the old position gate
    # let them be synthesized even though docs/corpus.md says they do not count.
    body = CHINESE_PARAGRAPHS * 3
    titles = [f"第{i + 1}章" for i in range(12)]
    titles[3] = "目录"
    titles[4] = "版权页"
    titles[5] = "前言 作者的话"
    chapters = [Chapter(title, body) for title in titles]
    make_epub(tmp_path / "late-fm.epub", chapters)
    book = load_book(tmp_path / "late-fm.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    classify_skippable(drafts, ChapteringPolicy())
    assert drafts[3].skippable is True    # 目录 at idx 3
    assert drafts[4].skippable is True    # 版权页 at idx 4
    assert drafts[5].skippable is False   # 前言 is content, not a non-reading page
    assert not any(d.skippable for d in drafts[6:])


def test_non_reading_page_matched_from_first_paragraph(tmp_path):
    # Spine fallback uses the file name as the title; the structural marker is
    # only in the text ("版权页"), so the classifier must inspect it too.
    body = CHINESE_PARAGRAPHS * 3
    chapters = [Chapter(f"第{i + 1}章", body) for i in range(12)]
    chapters[3] = Chapter("", ["版权页", *body])
    make_epub(tmp_path / "spine-cr.epub", chapters, nav_entries=[])
    book = load_book(tmp_path / "spine-cr.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    assert drafts[3].title == "ch4.xhtml"  # no heading text, falls back to href
    classify_skippable(drafts, ChapteringPolicy())
    assert drafts[3].skippable is True


def test_short_book_non_reading_marker_is_skipped(tmp_path):
    # Two chapters stay below min_nav_entries=3, so chaptering falls back to
    # spine and the empty <h1> leaves the file name as the title.
    body = CHINESE_PARAGRAPHS * 3
    chapters = [Chapter("", ["目录", *body]), Chapter("", body)]
    make_epub(tmp_path / "short-toc.epub", chapters, nav_entries=[])
    book = load_book(tmp_path / "short-toc.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    assert len(drafts) == 2
    assert drafts[0].title == "ch1.xhtml"
    classify_skippable(drafts, ChapteringPolicy())
    assert drafts[0].skippable is True
    assert drafts[1].skippable is False


def test_short_book_does_not_skip_on_stub_rule(tmp_path):
    # The n <= 2 guard exists so a short book is not swallowed by STUB_CHARS;
    # dropping it wholesale must not regress into "every chapter is a stub".
    chapters = [Chapter("第1章", ["测" * 100]), Chapter("第2章", ["试" * 100])]
    make_epub(tmp_path / "short-body.epub", chapters)
    book = load_book(tmp_path / "short-body.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    classify_skippable(drafts, ChapteringPolicy())
    assert [d.skippable for d in drafts] == [False, False]


def test_body_paragraph_mentioning_keywords_is_not_skipped(tmp_path):
    # "他翻开目录，检查版权归属和书名页的写法。" merely mentions the markers;
    # only a first paragraph that *starts* with one is a non-reading page.
    body = CHINESE_PARAGRAPHS * 3
    chapters = [Chapter(f"第{i + 1}章", body) for i in range(12)]
    chapters[2] = Chapter("第三章", ["他翻开目录，检查版权归属和书名页的写法。", *body])
    make_epub(tmp_path / "mention.epub", chapters)
    book = load_book(tmp_path / "mention.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    classify_skippable(drafts, ChapteringPolicy())
    assert drafts[2].skippable is False


def test_bibliography_is_readable_in_the_middle(tmp_path):
    # 书目 is appendix-like content the user may want spoken; only the back
    # window rule may skip it, so a mid-book 书目 reads as body.
    body = CHINESE_PARAGRAPHS * 3
    chapters = [Chapter(f"第{i + 1}章", body) for i in range(12)]
    chapters[5] = Chapter("书目", body)
    chapters[11] = Chapter("参考文献", body)
    make_epub(tmp_path / "biblio.epub", chapters)
    book = load_book(tmp_path / "biblio.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    classify_skippable(drafts, ChapteringPolicy())
    assert drafts[5].skippable is False
    assert drafts[11].skippable is True


def test_all_skippable_book_keeps_audio(tmp_path):
    # Both chapters are non-reading pages; clearing every flag is better than
    # exiting with "nothing was synthesized; there is no audio to package".
    body = CHINESE_PARAGRAPHS * 3
    chapters = [Chapter("", ["版权页", *body]), Chapter("", ["版权页", *body])]
    make_epub(tmp_path / "all-front.epub", chapters, nav_entries=[])
    book = load_book(tmp_path / "all-front.epub")
    _, drafts = choose_strategy(book, ChapteringPolicy())
    classify_skippable(drafts, ChapteringPolicy())
    assert len(drafts) == 2
    assert not all(d.skippable for d in drafts)
    assert any(not d.skippable for d in drafts)


def _path_c_drafts(tmp_path, nav_entries, *, headings=()):
    chapters = [Chapter(f"第{i + 1}章 标题", CHINESE_PARAGRAPHS[:6]) for i in range(4)]
    chapters[1].headings = list(headings)
    make_epub(tmp_path / "c.epub", chapters, nav_entries=nav_entries)
    book = load_book(tmp_path / "c.epub")
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    assert strategy == "nav"
    keys = [d.start_key for d in drafts]
    assert keys == sorted(keys, key=key_order)
    assert len(set(keys)) == len(keys)
    return drafts


def _rejection(draft, reason):
    return next((r for r in draft.rejected if r.reason == reason), None)


def test_path_c_exact_heading_match(tmp_path):
    drafts = _path_c_drafts(
        tmp_path,
        [("第1章", "Text/ch1.xhtml"), ("第2章", "Text/ch2.xhtml"),
         ("第三节 初入江湖", "Text/ch2.xhtml#nope"),
         ("第3章", "Text/ch3.xhtml"), ("第4章", "Text/ch4.xhtml")],
        headings=["第三节 初入江湖"])
    assert len(drafts) == 5
    cut = drafts[2]
    assert cut.start_key == "OEBPS/Text/ch2.xhtml|2"  # the h2 block, not doc start
    assert cut.title == "第三节 初入江湖"
    rej = _rejection(cut, "anchor_text_fallback")
    assert rej is not None
    assert rej.metrics["match"] == "exact"
    assert rej.metrics["anchor"] == "nope"
    assert _rejection(cut, "anchor_unresolved") is None


def test_path_c_unresolved_keeps_doc_start_and_records_it(tmp_path):
    drafts = _path_c_drafts(
        tmp_path,
        [("第1章", "Text/ch1.xhtml"), ("第2章", "Text/ch2.xhtml"),
         ("不存在的标题", "Text/ch3.xhtml#nope"),
         ("第4章", "Text/ch4.xhtml")])
    assert len(drafts) == 4
    cut = drafts[2]
    assert cut.start_key == "OEBPS/Text/ch3.xhtml|0"
    rej = _rejection(cut, "anchor_unresolved")
    assert rej is not None
    assert rej.metrics["match"] == "doc_start"
    assert rej.metrics["href"] == "OEBPS/Text/ch3.xhtml"
    assert _rejection(cut, "anchor_text_fallback") is None


def test_path_c_reason_survives_position_dedupe(tmp_path):
    """Trap A: a candidate dropped by `flat <= flat_starts[-1]` keeps its reason."""
    from soundbook.ingest.chaptering import _build_drafts, _Candidate, _Pos

    chapters = [Chapter(f"第{i + 1}章 标题", CHINESE_PARAGRAPHS[:6]) for i in range(3)]
    make_epub(tmp_path / "d.epub", chapters)
    book = load_book(tmp_path / "d.epub")
    cands = [
        _Candidate(pos=_Pos(0, 0), label="第1章", depth=0, source="nav"),
        _Candidate(pos=_Pos(1, 0), label="第2章", depth=0, source="nav"),
        # same flat position as the previous one -> dropped by dedupe
        _Candidate(pos=_Pos(1, 0), label="丢失", depth=0, source="nav",
                   reason="anchor_unresolved", anchor="x", match="doc_start"),
        _Candidate(pos=_Pos(2, 0), label="第3章", depth=0, source="nav"),
    ]
    drafts = _build_drafts(book, cands, "nav")
    assert len(drafts) == 3
    reasons = [(d.idx, r.reason) for d in drafts for r in d.rejected]
    assert reasons == [(2, "anchor_unresolved")]  # moved to the next kept chapter


def test_path_c_reason_survives_empty_chapter_filter(tmp_path):
    """Trap C: a zero-char chapter is dropped, its reason moves to a neighbour."""
    from soundbook.ingest.chaptering import _build_drafts, _Candidate, _Pos

    chapters = [Chapter(f"第{i + 1}章 标题", CHINESE_PARAGRAPHS[:6]) for i in range(3)]
    make_epub(tmp_path / "e.epub", chapters)
    book = load_book(tmp_path / "e.epub")
    # ch1's h1 alone is a heading-only span (the title is spoken separately),
    # so cuts at (0, 0) and (0, 1) yield a zero-char first chapter.
    cands = [
        _Candidate(pos=_Pos(0, 0), label="第1章", depth=0, source="nav",
                   reason="anchor_text_fallback", anchor="y", match="exact"),
        _Candidate(pos=_Pos(0, 1), label="正文", depth=0, source="nav"),
        _Candidate(pos=_Pos(1, 0), label="第2章", depth=0, source="nav"),
    ]
    drafts = _build_drafts(book, cands, "nav")
    assert len(drafts) == 2  # the empty chapter was dropped
    assert [r.reason for r in drafts[0].rejected] == ["anchor_text_fallback"]
    assert drafts[1].rejected == ()


def test_choose_strategy_merges_veto_with_path_c_reasons(tmp_path):
    """Trap B: veto reasons are appended to, not replacing, path C records."""
    chapters = [
        Chapter("第1章 短", CHINESE_PARAGRAPHS[:1]),
        Chapter("第2章 长", CHINESE_PARAGRAPHS * 80),
        Chapter("第3章", CHINESE_PARAGRAPHS[:2]),
    ]
    make_epub(tmp_path / "m.epub", chapters,
              nav_entries=[("第1章", "Text/ch1.xhtml"),
                           ("不存在的标题", "Text/ch2.xhtml#nope"),
                           ("第3章", "Text/ch3.xhtml")])
    book = load_book(tmp_path / "m.epub")
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    reasons = {r.reason for d in drafts for r in d.rejected}
    assert "dominant_chapter" in reasons
    assert strategy in {"nav+hybrid", "outline", "spine"}  # nav itself was vetoed


def test_veto_rejections_are_appended_to_path_c_records(tmp_path, monkeypatch):
    """Trap B, deterministic: nav is vetoed, nav+hybrid wins and keeps both records."""
    import soundbook.ingest.chaptering as ch
    from soundbook.models import Rejection

    chapters = [Chapter(f"第{i + 1}章 标题", CHINESE_PARAGRAPHS[:6]) for i in range(4)]
    make_epub(tmp_path / "t.epub", chapters,
              nav_entries=[("第1章", "Text/ch1.xhtml"),
                           ("不存在的标题", "Text/ch2.xhtml#nope"),
                           ("第3章", "Text/ch3.xhtml"),
                           ("第4章", "Text/ch4.xhtml")])
    book = load_book(tmp_path / "t.epub")

    real_hybrid = ch._hybrid_candidates

    def fake_hybrid(b):
        merged = real_hybrid(b)
        extra = ch._Candidate(pos=ch._Pos(3, 1), label="额外", depth=1, source="outline")
        return sorted([*merged, extra], key=lambda c: (c.pos.doc, c.pos.block))

    calls = {"n": 0}

    def fake_veto(drafts, policy):
        calls["n"] += 1
        if calls["n"] == 1:
            return [Rejection("?", "dominant_chapter", {})]
        return []

    monkeypatch.setattr(ch, "_hybrid_candidates", fake_hybrid)
    monkeypatch.setattr(ch, "_veto", fake_veto)
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    assert strategy == "nav+hybrid"
    carrier = next(d for d in drafts
                   if any(r.reason == "anchor_unresolved" for r in d.rejected))
    reasons = [r.reason for r in carrier.rejected]
    assert "dominant_chapter" in reasons  # veto reason appended, not overwritten
    assert reasons.count("anchor_unresolved") == 1


def test_path_c_normalizes_label_before_matching(tmp_path):
    # The loader collapses U+3000 to a plain space; heading has none, so the
    # fallback must drop all whitespace on both sides.
    drafts = _path_c_drafts(
        tmp_path,
        [("第1章", "Text/ch1.xhtml"), ("第2章", "Text/ch2.xhtml"),
         ("\u3000第三节\u3000初入江湖\u3000", "Text/ch2.xhtml#nope"),
         ("第3章", "Text/ch3.xhtml"), ("第4章", "Text/ch4.xhtml")],
        headings=["第三节初入江湖"])
    assert len(drafts) == 5
    assert drafts[2].start_key == "OEBPS/Text/ch2.xhtml|2"
    rej = _rejection(drafts[2], "anchor_text_fallback")
    assert rej is not None
    assert rej.metrics["match"] == "exact"


def test_cut_at_body_block_keeps_later_subheadings(tmp_path):
    """A fragment anchor landing on a body paragraph must not eat the h2 after it.

    Only the block the cut starts on can be the spoken title; the first
    heading *inside* the chapter span is body content, not a title.
    """

    chapters = [Chapter(f"第{i + 1}章", CHINESE_PARAGRAPHS[:6]) for i in range(4)]
    chapters[0].anchor = "mid"
    chapters[0].anchor_paragraph = 0  # id on the first <p>, before the <h2>
    chapters[0].headings = ["第一节 江湖"]
    make_epub(tmp_path / "sub.epub", chapters,
              nav_entries=[("第1章", "Text/ch1.xhtml"),
                           ("第一节 江湖", "Text/ch1.xhtml#mid"),
                           ("第2章", "Text/ch2.xhtml"),
                           ("第3章", "Text/ch3.xhtml"),
                           ("第4章", "Text/ch4.xhtml")])
    book = load_book(tmp_path / "sub.epub")
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    assert strategy == "nav"
    cut = next(d for d in drafts if d.start_key.endswith("ch1.xhtml|1"))
    assert "第一节 江湖" in cut.paragraphs
