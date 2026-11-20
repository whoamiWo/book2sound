from __future__ import annotations

from soundbook.ingest.anchors import resolve_anchor
from soundbook.ingest.loader import Document, DocBlock, load_book
from helpers import CHINESE_PARAGRAPHS, make_epub, simple_book


def _doc(payload: bytes = b"") -> Document:
    blocks = tuple(
        DocBlock(idx=i, kind="paragraph", text=text)
        for i, text in enumerate(CHINESE_PARAGRAPHS[:4])
    )
    return Document(index=0, href="Text/ch1.xhtml", blocks=blocks, payload=payload)


def test_path_a_via_dom_ids():
    blocks = (
        DocBlock(idx=0, kind="paragraph", text=CHINESE_PARAGRAPHS[0]),
        DocBlock(idx=1, kind="paragraph", text=CHINESE_PARAGRAPHS[1]),
        DocBlock(idx=2, kind="paragraph", text=CHINESE_PARAGRAPHS[2],
                 dom_ids=("mid",)),
    )
    doc = Document(index=0, href="x", blocks=blocks)
    assert resolve_anchor(doc, "mid") == 2


def test_path_b_resolves_anchor_from_raw_payload():
    """An id epubx never claims (on a bare wrapper element) is found via lxml."""
    payload = (
        "<html><body>"
        f"<p>{CHINESE_PARAGRAPHS[0]}</p>"
        f"<p>{CHINESE_PARAGRAPHS[1]}</p>"
        f"<p><span id=\"mid\">{CHINESE_PARAGRAPHS[2]}</span></p>"
        f"<p>{CHINESE_PARAGRAPHS[3]}</p>"
        "</body></html>"
    ).encode()
    doc = _doc(payload)
    assert resolve_anchor(doc, "mid", payload=doc.payload) == 2


def test_path_b_needs_payload():
    payload = b"<html><body><p id=\"mid\">text</p></body></html>"
    doc = _doc()
    # without payload there is no path B
    assert resolve_anchor(doc, "mid") is None
    doc = _doc(payload)
    assert resolve_anchor(doc, "mid", payload=None) is None


def test_unknown_anchor_returns_none():
    doc = _doc(b"<html><body><p id=\"other\">text</p></body></html>")
    assert resolve_anchor(doc, "missing", payload=doc.payload) is None


def _short_prefix_doc() -> Document:
    blocks = (
        DocBlock(idx=0, kind="paragraph", text="序"),
        DocBlock(idx=1, kind="paragraph", text=CHINESE_PARAGRAPHS[1]),
        DocBlock(idx=2, kind="paragraph", text=CHINESE_PARAGRAPHS[2]),
    )
    return Document(index=0, href="x", blocks=blocks)


def test_path_b_short_block_prefix_is_not_prefix_matched():
    """A one-character block must not absorb an anchor whose text merely starts with it."""
    doc = _short_prefix_doc()
    payload = (
        "<html><body><p>序</p>"
        f"<p>{CHINESE_PARAGRAPHS[1]}</p>"
        f"<p><span id=\"t\">序章 {CHINESE_PARAGRAPHS[3]}</span></p>"
        "</body></html>"
    ).encode()
    # 'wanted' starts with the lone '序' block text, but the shorter side has 1 char.
    assert resolve_anchor(doc, "t", payload=payload) is None


def test_path_b_long_prefix_still_aligns():
    doc = _short_prefix_doc()
    payload = (
        "<html><body><p>序</p>"
        f"<p>{CHINESE_PARAGRAPHS[1]}</p>"
        f"<p><span id=\"m\">{CHINESE_PARAGRAPHS[2]}</span></p>"
        "</body></html>"
    ).encode()
    assert resolve_anchor(doc, "m", payload=payload) == 2


def test_lxml_anchors_is_cached_per_payload():
    from soundbook.ingest.anchors import lxml_anchors

    payload = b"<html><body><p id=\"a\">text here</p></body></html>"
    lxml_anchors.cache_clear()
    first = lxml_anchors(payload)
    assert lxml_anchors(payload) is first
    assert lxml_anchors.cache_info().hits >= 1


def test_loader_stores_chapter_payload(tmp_path):
    book = load_book(simple_book(tmp_path / "b.epub"))
    assert all(doc.payload.startswith(b"<?xml") for doc in book.documents)


def test_fragment_anchor_not_resolved_to_doc_start(tmp_path):
    """Chaptering must cut at the anchor block, never fall back to block 0."""
    from soundbook.config import ChapteringPolicy
    from soundbook.ingest.chaptering import choose_strategy
    from helpers import Chapter

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
    assert drafts[1].end_key == drafts[2].start_key
