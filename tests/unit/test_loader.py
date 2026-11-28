from __future__ import annotations

import pytest
from helpers import (
    CHINESE_PARAGRAPHS,
    FONT_ENCRYPTION,
    REAL_DRM,
    Chapter,
    make_epub,
    simple_book,
)

from soundbook.ingest.loader import UnusableBook, load_book


def test_simple_book_loads(tmp_path):
    book = load_book(simple_book(tmp_path / "b.epub"))
    assert book.info.n_spine == 5
    assert len(book.documents) == 5
    assert len(book.nav) == 5
    assert book.info.title == "测试之书"
    assert book.info.language == "zh-CN"
    assert book.documents[0].blocks  # blocks are not empty


def test_font_obfuscation_is_readable(tmp_path):
    book = load_book(make_epub(
        tmp_path / "font.epub",
        [Chapter(f"第{i}章", CHINESE_PARAGRAPHS[:3]) for i in range(3)],
        encryption_xml=FONT_ENCRYPTION,
    ))
    assert book.info.obfuscated_fonts
    assert book.info.unsupported is None


def test_real_drm_is_unusable(tmp_path):
    with pytest.raises(UnusableBook) as excinfo:
        load_book(make_epub(
            tmp_path / "drm.epub",
            [Chapter("第1章", CHINESE_PARAGRAPHS[:3])],
            encryption_xml=REAL_DRM,
        ))
    assert excinfo.value.exit_code == 3
    assert "drm" in str(excinfo.value).lower() or "DRM" in str(excinfo.value)


def test_image_only_book_is_unusable(tmp_path):
    with pytest.raises(UnusableBook):
        load_book(make_epub(
            tmp_path / "img.epub",
            [Chapter(f"第{i}章", ["x"]) for i in range(3)],
            image_only=True,
        ))


def test_nav_anchor_maps_to_block(tmp_path):
    chapters = [
        Chapter(f"第{i + 1}章", CHINESE_PARAGRAPHS[:6]) for i in range(4)
    ]
    chapters[2].anchor = "mid"
    chapters[2].anchor_paragraph = 3
    make_epub(tmp_path / "a.epub", chapters,
              nav_entries=[("第1章", "Text/ch1.xhtml"),
                           ("第2章", "Text/ch2.xhtml"),
                           ("第3章 中段", "Text/ch3.xhtml#mid"),
                           ("第4章", "Text/ch4.xhtml")])
    book = load_book(tmp_path / "a.epub")
    entry = [n for n in book.nav if n.anchor == "mid"][0]
    assert entry.label == "第3章 中段"
    from soundbook.ingest.chaptering import _resolve_entry

    resolved = _resolve_entry(book, entry)
    assert resolved is not None
    pos, reason, match = resolved
    assert pos.doc == 2
    assert pos.block >= 3
    assert reason is None  # resolved by path A, no degradation record
    assert match is None
