"""Paragraph cleaning: eight steps, list in → list out, idempotent (spec §7).

Idempotence is a contract, not an accident: ``clean(clean(x)) == clean(x)`` is
covered by ``tests/unit/test_clean.py::test_idempotent_on_samples``, which is
parametrized over the fixture paragraphs and a messy sample.  Anything that
cannot be made idempotent does not belong here.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from soundbook.config import CleanPolicy

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00ad"), None)
_ASCII_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "　": " "})

_RE_SPACES = re.compile(r"[ \t\r\f\v]+")
_RE_PAGE_NUMBER = re.compile(r"^[-—–\s]*\d{1,4}[-—–\s]*$")
_RE_FOOTNOTE_MARK = re.compile(r"[\[【(（]\s*(?:注\s*)?\d{1,3}\s*[\]】)）]")
_RE_SUPERSCRIPT = re.compile(r"[\u00b9\u00b2\u00b3\u2070\u2074-\u2079]+")
_RE_DOTS = re.compile(r"[.·]{3,}")
_RE_ELLIPSIS = re.compile(r"…{3,}")
_RE_REPEAT_PUNCT = re.compile(r"([，。！？；：、])\1+")
_RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([，。！？；：、！？])")
_RE_BOILERPLATE = re.compile(
    r"^(?:本书由.{0,30}(?:整理|制作|提供)|更多(?:精彩|好看).{0,10}(?:小说|书)|"
    r"请记住(?:本站|本书|网址)|最新网址|手机版阅读|加入书签|上一章|下一章|"
    r"章节(?:错误|内容)|(?:www|http)\S*\.\S+|本章未完|点击下一页|返回目录)"
)

_NORMALIZE_STEPS = (
    _RE_FOOTNOTE_MARK,
    _RE_SUPERSCRIPT,
)


def _basic(text: str) -> str:
    text = text.translate(_ZERO_WIDTH)
    text = text.translate(_ASCII_QUOTES)
    text = _RE_SPACES.sub(" ", text)
    return text.strip()


def _strip_marks(text: str) -> str:
    for pattern in _NORMALIZE_STEPS:
        text = pattern.sub("", text)
    text = _RE_REPEAT_PUNCT.sub(r"\1", text)  # ！！！ → ！
    text = _RE_DOTS.sub("……", text)
    text = _RE_ELLIPSIS.sub("……", text)
    return text


def _normalize_punctuation(text: str) -> str:
    text = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = text.replace("!?", "？").replace("?!", "？")
    if text.endswith(","):
        text = text[:-1] + "，"
    return text.strip()


def is_page_number(text: str, policy: CleanPolicy) -> bool:
    return len(text) <= policy.page_number_max_chars and bool(_RE_PAGE_NUMBER.match(text))


def is_boilerplate(text: str) -> bool:
    return bool(_RE_BOILERPLATE.match(text))


def repeated_headers(paragraphs: Iterable[str], policy: CleanPolicy) -> frozenset[str]:
    """Short lines that recur across the book: running headers/footers.

    Computed over the whole book (a per-chapter view cannot see the repeat),
    but the result is just a set, so cleaning itself stays pure.
    """

    counts: Counter[str] = Counter()
    for text in paragraphs:
        if 0 < len(text) <= policy.header_max_chars:
            counts[text] += 1
    return frozenset(t for t, n in counts.items() if n >= policy.header_min_repeats)


def clean_paragraphs(
    paragraphs: Iterable[str],
    policy: CleanPolicy | None = None,
    *,
    drop: frozenset[str] = frozenset(),
) -> list[str]:
    """Run the eight steps. ``drop`` is the book-level repeated-header set."""

    policy = policy or CleanPolicy()
    out: list[str] = []
    previous: str | None = None
    for raw in paragraphs:
        if raw is None:
            continue
        # 1–2. whitespace, zero-width characters, full-width spaces
        text = _basic(raw)
        if not text:
            continue
        # 3. page numbers and rule lines
        if is_page_number(text, policy):
            continue
        # 4. footnote marker residue (the marker block itself never reaches here)
        if policy.strip_footnote_markers:
            text = _strip_marks(text).strip()
            if not text:
                continue
        # 5. running headers/footers seen elsewhere in the book
        if text in drop:
            continue
        # 6. advertising/boilerplate lines
        if is_boilerplate(text):
            continue
        # 7. punctuation normalisation
        if policy.normalize_punctuation:
            text = _normalize_punctuation(text)
        if not text:
            continue
        # 8. drop consecutive duplicates (OCR/HTML artefacts)
        if text == previous:
            continue
        out.append(text)
        previous = text
    return out


def warnings_for_chapter(chars: int, n_blocks: int, policy: CleanPolicy) -> str | None:
    """The C5 detector: prose hiding in ``<div>``/``<br>`` tails."""

    if n_blocks >= policy.warning_min_blocks and chars < policy.warning_min_chars:
        return (f"suspicious chapter: {n_blocks} blocks but only {chars} characters; "
                "prose may be in <div>/<br> tails (see docs/limitations.md)")
    return None
