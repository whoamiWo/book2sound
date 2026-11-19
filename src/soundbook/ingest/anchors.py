"""Fragment → block resolution (ADR-015).

Path A uses the ``dom_ids`` epubx exposes on every block: any ``@id`` the HTML
carries is claimed by the block that owns it, so a ``nav.xhtml`` href like
``Text/ch1.xhtml#c2`` maps directly to a block.

Path B re-parses the same spine document with lxml, takes the document order
of ``//*[@id]`` and aligns each element's first 20 normalised characters
against the epubx block texts.  It exists for books whose ids sit on elements
the block parser drops entirely (empty anchors).
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from soundbook.ingest.loader import Document

PREFIX_CHARS = 20


def normalize_prefix(text: str, length: int = PREFIX_CHARS) -> str:
    return "".join(text.split())[:length]


def anchor_positions(doc: Document) -> dict[str, int]:
    """dom id → first block idx claiming it (path A)."""

    positions: dict[str, int] = {}
    for block in doc.blocks:
        for dom_id in block.dom_ids:
            positions.setdefault(dom_id, block.idx)
    return positions


@dataclass(frozen=True)
class Anchor:
    dom_id: str
    prefix: str


def lxml_anchors(payload: bytes) -> tuple[Anchor, ...]:
    """Every ``//*[@id]`` in document order, with its text prefix (path B)."""

    parser = etree.HTMLParser(encoding="utf-8", recover=True)
    root = etree.fromstring(payload, parser)
    anchors: list[Anchor] = []
    for el in root.iter():
        dom_id = el.get("id")
        if not dom_id:
            continue
        text = " ".join(" ".join(el.itertext()).split())
        anchors.append(Anchor(dom_id=dom_id, prefix=normalize_prefix(text)))
    return tuple(anchors)


def resolve_anchor(
    doc: Document,
    anchor: str,
    *,
    payload: bytes | None = None,
    prefix_chars: int = PREFIX_CHARS,
) -> int | None:
    """Block idx an ``#anchor`` points at, or None when nothing claims it.

    None means "the anchor is not definable in this document" and callers
    treat it as the document start (matching epubx's own outline semantics).
    """

    positions = anchor_positions(doc)
    if anchor in positions:
        return positions[anchor]

    if payload is None:
        return None
    try:
        wanted = next(a for a in lxml_anchors(payload) if a.dom_id == anchor)
    except StopIteration:
        return None
    if not wanted.prefix:
        return None
    wanted_prefix = normalize_prefix(wanted.prefix, prefix_chars)
    for block in doc.blocks:
        block_prefix = normalize_prefix(block.text, prefix_chars)
        if block_prefix and (block_prefix.startswith(wanted_prefix) or wanted_prefix.startswith(block_prefix)):
            return block.idx
    return None
