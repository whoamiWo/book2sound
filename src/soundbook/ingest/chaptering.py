"""Three-level chaptering with a vetoer (spec §6, plan stage 2).

Strategy ladder:  ``nav`` → ``nav+hybrid`` (nav spans filled with outline
headings) → ``outline`` → ``spine``.  Every rejected strategy leaves a
:class:`~soundbook.models.Rejection` on each produced chapter so `inspect` can
explain *why* the book did not use its own table of contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from soundbook.config import ChapteringPolicy
from soundbook.ingest.anchors import resolve_anchor
from soundbook.ingest.loader import NavEntry, ParsedBook
from soundbook.models import ChapterDraft, Rejection


@dataclass(frozen=True)
class _Pos:
    doc: int  # index into book.documents
    block: int  # block idx within that document

    def key(self, book: ParsedBook) -> str:
        return f"{book.documents[self.doc].href}|{self.block}"


@dataclass(frozen=True)
class _Candidate:
    pos: _Pos
    label: str
    depth: int
    source: str  # "nav" | "outline" | "spine"


def _flatten_positions(book: ParsedBook) -> list[_Pos]:
    positions: list[_Pos] = []
    for doc_i, doc in enumerate(book.documents):
        for block in doc.blocks:
            positions.append(_Pos(doc=doc_i, block=block.idx))
    return positions


def _doc_start(book: ParsedBook, doc_i: int) -> _Pos | None:
    doc = book.documents[doc_i]
    return _Pos(doc=doc_i, block=doc.blocks[0].idx) if doc.blocks else None


def _resolve_entry(book: ParsedBook, entry: NavEntry) -> _Pos | None:
    if not entry.href:
        return None
    doc_i = book.doc_index(entry.href)
    if doc_i is None:
        return None
    doc = book.documents[doc_i]
    if entry.anchor:
        idx = resolve_anchor(doc, entry.anchor, payload=doc.payload or None)
        if idx is not None:
            return _Pos(doc=doc_i, block=idx)
    return _doc_start(book, doc_i)


def _candidates(book: ParsedBook, entries: tuple[NavEntry, ...], source: str) -> list[_Candidate]:
    """Resolve entries to positions; same position keeps the deeper entry."""

    by_pos: dict[tuple[int, int], _Candidate] = {}
    for entry in entries:
        pos = _resolve_entry(book, entry)
        if pos is None:
            continue
        key = (pos.doc, pos.block)
        prev = by_pos.get(key)
        if prev is None or entry.depth > prev.depth:
            by_pos[key] = _Candidate(pos=pos, label=entry.label, depth=entry.depth, source=source)
    return [by_pos[k] for k in sorted(by_pos)]


def _hybrid_candidates(book: ParsedBook) -> list[_Candidate]:
    """Nav positions, with outline headings filling spans the nav left bare."""

    nav = _candidates(book, book.nav, "nav")
    outline = _candidates(book, book.outline, "outline")
    nav_pos = {(c.pos.doc, c.pos.block) for c in nav}
    merged = list(nav)
    for cand in outline:
        if (cand.pos.doc, cand.pos.block) not in nav_pos:
            merged.append(cand)
    return sorted(merged, key=lambda c: (c.pos.doc, c.pos.block))


def _spine_candidates(book: ParsedBook) -> list[_Candidate]:
    out: list[_Candidate] = []
    for doc_i, doc in enumerate(book.documents):
        if not doc.blocks:
            continue
        heading = next((b for b in doc.blocks if b.is_heading and b.text), None)
        label = heading.text if heading else doc.href.rsplit("/", 1)[-1]
        out.append(_Candidate(pos=_Pos(doc=doc_i, block=doc.blocks[0].idx),
                              label=label, depth=0, source="spine"))
    return out


def _looks_like_href(label: str) -> bool:
    lowered = label.strip().lower()
    return ("/" in lowered or lowered.endswith((".xhtml", ".html", ".htm", ".xml")))


def _title_for(book: ParsedBook, cand: _Candidate, index: int, zh: bool) -> str:
    label = cand.label.strip()
    if label and not _looks_like_href(label):
        return label
    doc = book.documents[cand.pos.doc]
    heading = next((b.text for b in doc.blocks if b.is_heading and b.text), "")
    if heading:
        return heading
    if label:
        return label
    return f"第{index + 1}章" if zh else f"Chapter {index + 1}"


def _build_drafts(book: ParsedBook, candidates: list[_Candidate],
                  strategy: str) -> list[ChapterDraft]:
    """Cut the global block stream at candidate positions."""

    positions = _flatten_positions(book)
    pos_to_flat: dict[tuple[int, int], int] = {(p.doc, p.block): i
                                               for i, p in enumerate(positions)}
    flat_starts: list[int] = []
    keep: list[_Candidate] = []
    for cand in candidates:
        flat = pos_to_flat.get((cand.pos.doc, cand.pos.block))
        if flat is None:
            continue
        if flat_starts and flat <= flat_starts[-1]:
            continue
        flat_starts.append(flat)
        keep.append(cand)
    if not flat_starts or flat_starts[0] != 0:
        flat_starts.insert(0, 0)
        first = positions[0]
        doc = book.documents[first.doc]
        heading = doc.block(first.block)
        label = heading.text if heading and heading.is_heading else ""
        keep.insert(0, _Candidate(pos=first, label=label, depth=0, source="implicit"))

    drafts: list[ChapterDraft] = []
    n = len(keep)
    zh = (book.info.language or "").lower().startswith(("zh", "cmn", "yue"))
    for i, (cand, flat) in enumerate(zip(keep, flat_starts)):
        end_flat = flat_starts[i + 1] if i + 1 < n else len(positions)
        span = positions[flat:end_flat]
        paragraphs: list[str] = []
        first_dropped = False
        for p in span:
            block = book.documents[p.doc].block(p.block)
            if block is None:
                continue
            if not first_dropped and block.is_heading:
                first_dropped = True  # the chapter title, spoken separately
                continue
            paragraphs.append(block.text)
        start_key = cand.pos.key(book)
        end_key_str = None
        if i + 1 < n:
            nxt = keep[i + 1].pos
            end_key_str = f"{book.documents[nxt.doc].href}|{nxt.block}"
        title = _title_for(book, cand, i, zh)
        drafts.append(ChapterDraft(
            idx=i, title=title, paragraphs=tuple(paragraphs), strategy=strategy,
            start_key=start_key, end_key=end_key_str,
        ))
    return [d for d in drafts if d.char_count > 0] or drafts


def _veto(drafts: list[ChapterDraft], policy: ChapteringPolicy) -> list[Rejection]:
    """A strategy survives only if its cut looks like real chapters."""

    rejections: list[Rejection] = []
    n = len(drafts)
    if n < 2:
        rejections.append(Rejection("?", "too_few_chapters", {"n": n}))
        return rejections
    sizes = [d.char_count for d in drafts]
    total = sum(sizes) or 1
    largest = max(sizes)
    share = largest / total
    if share > policy.max_share:
        rejections.append(Rejection("?", "dominant_chapter",
                                    {"share": round(share, 4), "max_share": policy.max_share}))
    if largest > policy.single_chapter_max_chars:
        rejections.append(Rejection("?", "oversized_chapter",
                                    {"chars": largest,
                                     "limit": policy.single_chapter_max_chars}))
    if n >= policy.median_chars_min_chapters:
        med = median(sizes)
        if med < policy.median_chars_floor:
            rejections.append(Rejection("?", "tiny_median_chapter",
                                        {"median": med,
                                         "floor": policy.median_chars_floor}))
    return rejections


def choose_strategy(book: ParsedBook, policy: ChapteringPolicy) -> tuple[str, list[ChapterDraft]]:
    """Pick the first strategy the vetoer accepts; annotate the losers."""

    nav_candidates = _candidates(book, book.nav, "nav")
    attempts: list[tuple[str, list[_Candidate]]] = []
    if len(nav_candidates) >= policy.min_nav_entries:
        attempts.append(("nav", nav_candidates))
        hybrid = _hybrid_candidates(book)
        if len(hybrid) > len(nav_candidates):
            attempts.append(("nav+hybrid", hybrid))
    if book.outline:
        attempts.append(("outline", _candidates(book, book.outline, "outline")))
    attempts.append(("spine", _spine_candidates(book)))

    rejections: list[Rejection] = []
    for strategy, candidates in attempts:
        drafts = _build_drafts(book, candidates, strategy)
        veto = _veto(drafts, policy)
        if not veto:
            for draft in drafts:
                draft.rejected = tuple(
                    Rejection(r.strategy, r.reason, r.metrics) for r in rejections
                )
            return strategy, drafts
        rejections.extend(
            Rejection(strategy, r.reason, {**r.metrics, "chapters": len(drafts)})
            for r in veto
        )
    # `spine` can only be vetoed on pathological books; still return it.
    strategy, candidates = attempts[-1]
    drafts = _build_drafts(book, candidates, strategy)
    for draft in drafts:
        draft.rejected = tuple(rejections)
    return strategy, drafts
