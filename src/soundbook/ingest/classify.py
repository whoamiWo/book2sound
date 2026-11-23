"""Front/back matter classification (spec §6.4).

Two kinds of evidence:

- *Non-reading pages* (``NON_READING_KEYWORDS``): 目录、版权页、扉页、cover,
  contents & co. are never spoken, so a keyword hit in the title or first
  paragraph skips the chapter regardless of position. This is the documented
  rule that 版权页/目录页 do not count as chapters (docs/corpus.md).
- *Position-gated keywords* (``FRONT_KEYWORDS`` / ``BACK_KEYWORDS``): these
  retain the existing front/back-window behavior; their title alone does not
  skip a chapter outside those windows. Short chapters are still treated as
  stubs when they fall inside a matter window.
"""

from __future__ import annotations

from soundbook.config import ChapteringPolicy
from soundbook.models import ChapterDraft

#: Pages that are never chapters, matched anywhere in the book.
NON_READING_KEYWORDS = (
    "目录", "扉页", "版权", "书名页", "cover", "title page", "contents",
    "copyright", "colophon", "书目",
)

#: Front-matter chapters: only skipped inside the front window or as stubs.
FRONT_KEYWORDS = (
    "内容简介", "内容提要", "作者简介", "出版说明", "前言", "序言", "序章", "自序",
    "译者序", "推荐序", "引言", "楔子", "preface", "foreword",
)

#: Back-matter chapters: only skipped inside the back window or as stubs.
BACK_KEYWORDS = (
    "后记", "附录", "致谢", "参考文献", "番外", "完本感言",
    "afterword", "appendix", "acknowledg", "references",
)

#: Below this, a chapter in the matter windows is treated as a stub.
STUB_CHARS = 300


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.strip().lower()
    return any(keyword in lowered for keyword in keywords)


def _probe(draft: ChapterDraft) -> str:
    """Title plus first paragraph: spine titles can be bare file names."""

    first = draft.paragraphs[0] if draft.paragraphs else ""
    return f"{draft.title}\n{first}"


def classify_skippable(drafts: list[ChapterDraft], policy: ChapteringPolicy) -> None:
    n = len(drafts)
    if n <= 2:
        return
    for draft in drafts:
        probe = _probe(draft)
        front = draft.idx < policy.front_matter_window
        back = draft.idx >= n - policy.back_matter_window
        if _matches(probe, NON_READING_KEYWORDS):
            draft.skippable = True
        elif front and (_matches(draft.title, FRONT_KEYWORDS) or draft.char_count < STUB_CHARS):
            draft.skippable = True
        elif back and (_matches(draft.title, BACK_KEYWORDS) or draft.char_count < STUB_CHARS):
            draft.skippable = True
