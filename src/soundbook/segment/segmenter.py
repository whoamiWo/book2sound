"""Pure segmentation (spec §8 / ADR-012).

Input: cleaned paragraphs and a title.  Output: a tuple of
:class:`~soundbook.models.SegmentDraft`.  No clocks, no files, no randomness —
the same input always yields byte-identical output.
"""

from __future__ import annotations

from soundbook.config import SegmentPolicy
from soundbook.models import ChapterDraft, SegmentDraft

ENDERS = frozenset("。！？!?…")
CLOSERS = frozenset("”’」』）)】》〉…")
SOFT_BREAKS = frozenset("，、：；,;:")


def _split_sentences(text: str) -> list[str]:
    """Split on sentence enders, keeping trailing closers with the sentence."""

    out: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        buf.append(char)
        i += 1
        if char in ENDERS:
            while i < n and (text[i] in ENDERS or text[i] in CLOSERS):
                buf.append(text[i])
                i += 1
            sentence = "".join(buf).strip()
            if sentence:
                out.append(sentence)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _hard_split(sentence: str, hard_max: int) -> list[str]:
    """Break a sentence longer than ``hard_max`` at soft punctuation, else cut."""

    if len(sentence) <= hard_max:
        return [sentence]
    out: list[str] = []
    rest = sentence
    while len(rest) > hard_max:
        window = rest[:hard_max]
        cut = max((window.rfind(ch) for ch in SOFT_BREAKS), default=-1)
        if cut < hard_max // 3:
            cut = hard_max - 1
        piece = rest[: cut + 1].strip()
        if piece:
            out.append(piece)
        rest = rest[cut + 1:].lstrip()
    if rest:
        out.append(rest)
    return out


def _pack(sentences: list[str], target: int, hard_max: int) -> list[str]:
    segments: list[str] = []
    buf = ""
    for sentence in sentences:
        for piece in _hard_split(sentence, hard_max):
            if not buf:
                buf = piece
            elif len(buf) + len(piece) <= target:
                buf += piece
            else:
                segments.append(buf)
                buf = piece
    if buf:
        segments.append(buf)
    return segments


def segment_paragraphs(
    chapter_idx: int,
    title: str | None,
    paragraphs: tuple[str, ...] | list[str],
    policy: SegmentPolicy | None = None,
) -> list[SegmentDraft]:
    policy = policy or SegmentPolicy()
    drafts: list[SegmentDraft] = []

    if policy.speak_titles and title and title.strip():
        drafts.append(
            SegmentDraft(
                chapter_idx=chapter_idx,
                seg_idx=-1,
                text=" ".join(title.split()),
                pause_after_ms=policy.paragraph_pause_ms,
                is_title=True,
            )
        )

    body: list[SegmentDraft] = []
    index = 0
    for paragraph in paragraphs:
        text = paragraph.strip()
        if not text:
            continue
        pieces = _pack(_split_sentences(text), policy.target_chars, policy.hard_max_chars)
        for last in range(len(pieces)):
            body.append(
                SegmentDraft(
                    chapter_idx=chapter_idx,
                    seg_idx=index,
                    text=pieces[last],
                    pause_after_ms=policy.sentence_pause_ms,
                    is_title=False,
                )
            )
            index += 1
        if body:
            body[-1] = SegmentDraft(
                chapter_idx=chapter_idx,
                seg_idx=body[-1].seg_idx,
                text=body[-1].text,
                pause_after_ms=policy.paragraph_pause_ms,
                is_title=False,
            )

    if body:
        last = body[-1]
        body[-1] = SegmentDraft(
            chapter_idx=chapter_idx,
            seg_idx=last.seg_idx,
            text=last.text,
            pause_after_ms=policy.chapter_pause_ms,
            is_title=False,
        )
    return drafts + body


def segment_chapter(
    chapter: ChapterDraft,
    policy: SegmentPolicy | None = None,
    *,
    cleaned_paragraphs: list[str] | None = None,
) -> list[SegmentDraft]:
    paragraphs = cleaned_paragraphs if cleaned_paragraphs is not None else list(chapter.paragraphs)
    return segment_paragraphs(chapter.idx, chapter.title, paragraphs, policy)
