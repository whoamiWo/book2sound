"""Front/back matter classification (spec §6.4).

Position + keyword + length, in that order of confidence: a short first
chapter titled 目录 is front matter; a 4000-character 序 is not.
"""

from __future__ import annotations

from soundbook.config import ChapteringPolicy
from soundbook.models import ChapterDraft

FRONT_KEYWORDS = (
    "目录", "扉页", "版权", "内容简介", "内容提要", "作者简介", "出版说明",
    "前言", "序言", "序章", "自序", "译者序", "推荐序", "引言", "楔子",
    "cover", "title page", "contents", "copyright", "preface", "foreword",
)

BACK_KEYWORDS = (
    "后记", "附录", "致谢", "参考文献", "版权页", "番外", "完本感言",
    "afterword", "appendix", "acknowledg", "references", "colophon",
)

#: Below this, a chapter in the matter windows is treated as a stub.
STUB_CHARS = 300


def _matches(title: str, keywords: tuple[str, ...]) -> bool:
    lowered = title.strip().lower()
    return any(keyword in lowered for keyword in keywords)


def classify_skippable(drafts: list[ChapterDraft], policy: ChapteringPolicy) -> None:
    n = len(drafts)
    if n <= 2:
        return
    for draft in drafts:
        front = draft.idx < policy.front_matter_window
        back = draft.idx >= n - policy.back_matter_window
        if front and (_matches(draft.title, FRONT_KEYWORDS) or draft.char_count < STUB_CHARS):
            draft.skippable = True
        elif back and (_matches(draft.title, BACK_KEYWORDS) or draft.char_count < STUB_CHARS):
            draft.skippable = True
