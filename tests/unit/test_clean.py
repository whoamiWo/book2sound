from __future__ import annotations

import pytest

from soundbook.config import CleanPolicy
from soundbook.ingest.clean import (
    clean_paragraphs,
    is_boilerplate,
    is_page_number,
    repeated_headers,
    warnings_for_chapter,
)
from helpers import CHINESE_PARAGRAPHS

POLICY = CleanPolicy()

MESSY_SAMPLE = [
    "  第一章　风雪夜归人  ",
    "　　凌冽的寒风穿过山谷，　卷起漫天碎雪。",
    "他握紧了手中的刀……",
    "“你来晚了。”",
    "请记住本站网址",
    "123",
    "他继续向前走。",
]


def _clean(paras, drop=frozenset()):
    return clean_paragraphs(paras, POLICY, drop=drop)


def test_idempotent_on_messy_text():
    once = _clean(MESSY_SAMPLE)
    twice = _clean(once)
    assert once == twice
    assert "123" not in once
    assert "请记住本站网址" not in once


@pytest.mark.parametrize(
    "sample",
    [[paragraph] for paragraph in CHINESE_PARAGRAPHS] + [MESSY_SAMPLE],
    ids=[f"chinese-{i}" for i in range(len(CHINESE_PARAGRAPHS))] + ["messy"],
)
def test_idempotent_on_samples(sample):
    once = _clean(sample)
    assert _clean(once) == once


def test_whitespace_and_fullwidth_collapsed():
    assert _clean(["　　他　　走  到 山 顶 。"]) == ["他 走 到 山 顶。"]


def test_page_number_detection():
    assert is_page_number("123", POLICY)
    assert is_page_number("- 12 -", POLICY)
    assert not is_page_number("一九八四年", POLICY)
    assert not is_page_number("他数到了三百。", POLICY)


def test_boilerplate_detection():
    assert is_boilerplate("请记住本站网址")
    assert is_boilerplate("上一章")
    assert is_boilerplate("www.example.com 看最新章节")
    assert not is_boilerplate("他转身走进风雪里。")


def test_repeated_headers_removed_after_threshold():
    paras = []
    for i in range(5):
        paras += ["苍山外史", f"第{i}页的故事内容。"]
    headers = repeated_headers(paras, POLICY)
    assert "苍山外史" in headers
    cleaned = _clean(paras, drop=headers)
    assert "苍山外史" not in cleaned
    assert any("第0页" in p for p in cleaned)


def test_single_occurrence_header_kept():
    paras = ["只在开头出现一次", "正文一。", "正文二。"]
    headers = repeated_headers(paras, POLICY)
    assert not headers
    assert _clean(paras, drop=headers) == paras


def test_footnote_markers_stripped():
    assert _clean(["他指出这一点[注1]，却又摇头。"]) == ["他指出这一点，却又摇头。"]
    assert _clean(["他说¹：不对。"]) == ["他说：不对。"]


def test_repeat_punctuation_collapsed():
    assert _clean(["啊！！！", "原来。。。"]) == ["啊！", "原来。"]


def test_ellipsis_merged():
    assert _clean(["他沉默了......"]) == ["他沉默了……"]
    assert _clean(["他沉默…………"]) == ["他沉默……"]


def test_consecutive_duplicates_dropped():
    assert _clean(["他走了。", "他走了。", "她没有说话。"]) == ["他走了。", "她没有说话。"]


def test_warning_probe_for_suspicious_short_chapter():
    assert warnings_for_chapter(chars=50, n_blocks=10, policy=POLICY) is not None
    assert warnings_for_chapter(chars=5000, n_blocks=10, policy=POLICY) is None
    assert warnings_for_chapter(chars=50, n_blocks=2, policy=POLICY) is None
