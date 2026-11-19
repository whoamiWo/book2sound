from __future__ import annotations

from soundbook.config import SegmentPolicy
from soundbook.segment.segmenter import segment_paragraphs

PARAS = [
    "凌冽的寒风穿过山谷。卷起漫天碎雪，打在人的脸上生疼。",
    "他握紧了手中的刀。一步一步向山顶走去，脚步沉稳而坚定。",
    "山道两侧是深不见底的悬崖！偶尔有碎石滚落，久久听不到回声。",
]


def _segment(paras=PARAS, title="第1章 风雪"):
    return segment_paragraphs(0, title, paras, SegmentPolicy())


def test_deterministic():
    first = [(s.seg_idx, s.text, s.pause_after_ms) for s in _segment()]
    second = [(s.seg_idx, s.text, s.pause_after_ms) for s in _segment()]
    assert first == second


def test_title_is_seg_idx_minus_one_and_pause_500():
    title = _segment()[0]
    assert title.is_title
    assert title.seg_idx == -1
    assert title.text == "第1章 风雪"
    assert title.pause_after_ms == 500


def test_body_segments_numbered_from_zero():
    body = [s for s in _segment() if not s.is_title]
    assert [s.seg_idx for s in body] == list(range(len(body)))


def test_hierarchy_of_pauses():
    body = [s for s in _segment() if not s.is_title]
    assert body[-1].pause_after_ms == 1200
    assert all(s.pause_after_ms == 500 for s in body[:-1])
    # a paragraph longer than target_chars splits mid-paragraph: pause 220
    long_para = ("他向前走。" * 30)  # 150 chars > 90
    split = [s for s in segment_paragraphs(0, None, [long_para], SegmentPolicy())
             if not s.is_title]
    assert len(split) > 1
    assert split[0].pause_after_ms == 220


def test_body_text_covers_all_non_punctuation_characters():
    joined = "".join(s.text for s in _segment() if not s.is_title)
    for para in PARAS:
        for char in para:
            if char in "。，！？":
                continue
            assert char in joined


def test_long_sentence_split_under_hard_max():
    policy = SegmentPolicy()
    monster = "字" * 50 + "，" + "段" * 200 + "。" + "尾" * 400 + "。"
    body = [s for s in segment_paragraphs(0, None, [monster], policy) if not s.is_title]
    assert len(body) > 1
    for seg in body:
        assert len(seg.text) <= policy.hard_max_chars + 2  # +2 stray punctuation


def test_short_paragraphs_are_separate_but_packed_within_a_paragraph():
    body = [s for s in segment_paragraphs(
        0, None, ["短句。"] * 8, SegmentPolicy()) if not s.is_title]
    assert len(body) == 8  # paragraphs are never merged
    packed = [s for s in segment_paragraphs(
        0, None, ["短句。" * 8], SegmentPolicy()) if not s.is_title]
    assert len(packed) == 1  # one 32-char paragraph packs into one segment


def test_no_title_when_none():
    segments = segment_paragraphs(0, None, ["正文。"], SegmentPolicy())
    assert all(not s.is_title for s in segments)


def test_no_title_when_speak_titles_off():
    policy = SegmentPolicy(speak_titles=False)
    segments = segment_paragraphs(0, "第1章", ["正文。"], policy)
    assert all(not s.is_title for s in segments)


def test_empty_paragraphs_yield_nothing():
    assert segment_paragraphs(0, "", ["  ", ""], SegmentPolicy()) == []
