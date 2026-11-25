"""Front/back matter classification (spec §6.4).

Two kinds of evidence:

- *Non-reading pages* (``NON_READING_KEYWORDS``): 目录、版权页、扉页、cover,
  contents & co. are never spoken, so they are skipped regardless of position,
  including in books with only one or two chapters. A title hit is a substring
  match (titles are metadata); a first-paragraph hit must be a *prefix*, so a
  body sentence that merely mentions 目录/版权 does not skip the chapter.
- *Position-gated keywords* (``FRONT_KEYWORDS`` / ``BACK_KEYWORDS``): these
  retain the existing front/back-window behavior; their title alone does not
  skip a chapter outside those windows. Short chapters are still treated as
  stubs when they fall inside a matter window, but only when the book has more
  than two chapters: otherwise ``STUB_CHARS`` could swallow a whole short book.

If every chapter would be skipped, the flags are cleared. Synthesizing one
extra chapter is preferable to ``run`` exiting 2 with "nothing was
synthesized; there is no audio to package" (see ADR-023).
"""

from __future__ import annotations

from soundbook.config import ChapteringPolicy
from soundbook.models import ChapterDraft

#: Pages that are never chapters, matched anywhere in the book.
NON_READING_KEYWORDS = (
    "目录", "扉页", "版权", "书名页", "cover", "title page", "contents",
    "table of contents", "copyright", "colophon",
)

#: Front-matter chapters: only skipped inside the front window or as stubs.
FRONT_KEYWORDS = (
    "内容简介", "内容提要", "作者简介", "出版说明", "前言", "序言", "序章", "自序",
    "译者序", "推荐序", "引言", "楔子", "preface", "foreword",
)

#: Back-matter chapters: only skipped inside the back window or as stubs.
BACK_KEYWORDS = (
    "后记", "附录", "致谢", "书目", "参考文献", "番外", "完本感言",
    "afterword", "appendix", "acknowledg", "references",
)

#: Below this, a chapter in the matter windows is treated as a stub.
STUB_CHARS = 300


def _squash(text: str) -> str:
    """Drop all whitespace and case so markers match across layout quirks."""

    return "".join(text.split()).lower()


def _title_probe(draft: ChapterDraft) -> str:
    return _squash(draft.title)


def _marker_probe(draft: ChapterDraft) -> str:
    """The first paragraph: in spine fallback it carries the page marker."""

    first = draft.paragraphs[0] if draft.paragraphs else ""
    return _squash(first)


def _matches(probe: str, keywords: tuple[str, ...], *, at_start: bool = False) -> bool:
    if at_start:
        return any(probe.startswith(_squash(keyword)) for keyword in keywords)
    return any(_squash(keyword) in probe for keyword in keywords)


def classify_skippable(drafts: list[ChapterDraft], policy: ChapteringPolicy) -> None:
    n = len(drafts)
    for draft in drafts:
        front = draft.idx < policy.front_matter_window
        back = draft.idx >= n - policy.back_matter_window
        if (_matches(_title_probe(draft), NON_READING_KEYWORDS)
                or _matches(_marker_probe(draft), NON_READING_KEYWORDS, at_start=True)):
            draft.skippable = True
        elif n > 2 and front and (_matches(_title_probe(draft), FRONT_KEYWORDS)
                                  or draft.char_count < STUB_CHARS):
            draft.skippable = True
        elif n > 2 and back and (_matches(_title_probe(draft), BACK_KEYWORDS)
                                 or draft.char_count < STUB_CHARS):
            draft.skippable = True

    # Never skip the whole book (ADR-023): prefer one extra spoken chapter over
    # an empty result and the CLI's "nothing was synthesized" exit code 2.
    if drafts and all(draft.skippable for draft in drafts):
        for draft in drafts:
            draft.skippable = False
