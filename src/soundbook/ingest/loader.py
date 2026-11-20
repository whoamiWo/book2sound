"""The one place that imports ``epubx``.

Everything downstream (chaptering, cleaning, segmentation) works on plain
tuples of :class:`Document` / :class:`NavEntry`, so the upstream library can be
swapped or wrapped in tests without touching the rest of the package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

import epubx

from soundbook.models import BookInfo
from soundbook.util.hashing import sha256_file

#: Block kinds that carry prose a narrator should read.
SPEAKABLE_KINDS = frozenset(
    {"heading", "paragraph", "quote", "list", "definition_list", "table", "preformatted"}
)

#: Block kinds that are structure, not speech.
SILENT_KINDS = frozenset({"page_break", "footnote_ref", "figure", "math"})


class UnusableBook(RuntimeError):
    """The file cannot be narrated at all (missing, DRM, image-only, broken)."""

    exit_code = 3


@dataclass(frozen=True)
class DocBlock:
    """A block flattened out of epubx, with only what we need."""

    idx: int
    kind: str
    text: str
    level: int | None = None
    dom_ids: tuple[str, ...] = ()
    target_id: str | None = None

    @property
    def is_heading(self) -> bool:
        return self.kind == "heading"


@dataclass(frozen=True)
class Document:
    index: int
    href: str
    blocks: tuple[DocBlock, ...]
    #: Raw XHTML bytes of the spine document, kept so fragment anchors that no
    #: block claims can be resolved with lxml (anchors.py path B).
    payload: bytes = b""

    def block(self, idx: int) -> DocBlock | None:
        if 0 <= idx < len(self.blocks):
            return self.blocks[idx]
        return None

    @property
    def headings(self) -> tuple[DocBlock, ...]:
        return tuple(b for b in self.blocks if b.is_heading and b.text)


@dataclass(frozen=True)
class NavEntry:
    """A flattened TOC entry: book.toc or book.outline, pre-order."""

    label: str
    href: str | None
    anchor: str | None
    depth: int
    source: str  # "nav" | "outline"


@dataclass(frozen=True)
class ParsedBook:
    info: BookInfo
    documents: tuple[Document, ...]
    nav: tuple[NavEntry, ...]
    outline: tuple[NavEntry, ...]
    cover_bytes: bytes | None = None
    cover_media_type: str | None = None

    def doc_index(self, href: str) -> int | None:
        for doc in self.documents:
            if doc.href == href:
                return doc.index
        return None


def _flatten_toc(nodes, *, source: str, depth: int = 0) -> list[NavEntry]:
    seen: list[NavEntry] = []
    for node in nodes:
        label = " ".join((node.label or "").split())
        seen.append(
            NavEntry(
                label=label,
                href=node.href or None,
                anchor=node.anchor or None,
                depth=depth,
                source=source,
            )
        )
        seen.extend(_flatten_toc(node.children, source=source, depth=depth + 1))
    return seen


def _block_from_epubx(block, idx: int) -> DocBlock | None:
    kind = str(block.kind)
    if kind not in SPEAKABLE_KINDS:
        return None
    text = " ".join(block.plain_text.split())
    if not text:
        return None
    level = block.attributes.get("level")
    dom_ids = tuple(block.attributes.get("dom_ids") or ())
    return DocBlock(
        idx=idx,
        kind=kind,
        text=text,
        level=level if isinstance(level, int) else None,
        dom_ids=dom_ids,
        target_id=block.attributes.get("target_id"),
    )


def _chapter_payload(book, chapter) -> bytes:
    """Raw XHTML bytes for anchors.py path B; empty when unreadable."""

    try:
        return book.member(chapter.href)
    except Exception:
        return b""


def load_book(path: str | Path) -> ParsedBook:
    """Open ``path`` and materialise every spine document.

    Raises :class:`UnusableBook` for anything that should map to exit code 3.
    """

    book_path = Path(path)
    if not book_path.is_file():
        raise UnusableBook(f"not a file: {book_path}")

    try:
        book = epubx.open_book(str(book_path))
    except Exception as exc:  # epubx raises EpubError/ZipFile errors
        raise UnusableBook(f"cannot open EPUB: {exc}") from exc

    try:
        documents: list[Document] = []
        for chapter in book.chapters:
            blocks: list[DocBlock] = []
            for ordinal, raw in enumerate(chapter.blocks):
                converted = _block_from_epubx(raw, ordinal)
                if converted is None:
                    continue
                # epubx emits a heading twice — once in the paragraph flow and
                # once as kind="heading" — which would narrate every title
                # twice. Drop the paragraph copy when they are identical.
                if (blocks and converted.is_heading
                        and blocks[-1].kind == "paragraph"
                        and blocks[-1].text == converted.text):
                    blocks.pop()
                # Renumber so Document.block(idx) is a plain list index even
                # after silent blocks were filtered out.
                blocks.append(replace(converted, idx=len(blocks)))
            documents.append(Document(index=chapter.index, href=chapter.href,
                                      blocks=tuple(blocks),
                                      payload=_chapter_payload(book, chapter)))

        # Image-only detection is lazy: it samples chapters on first access, so
        # this must be asked *after* the chapters above have been parsed (C4).
        unsupported = book.unsupported
        if unsupported:
            raise UnusableBook(unsupported)

        if not any(doc.blocks for doc in documents):
            raise UnusableBook("no narratable text blocks in any spine document")

        metadata = book.metadata
        title = (metadata.title or "").strip() or book_path.stem
        language = (metadata.language or "").strip() or None

        cover_sha: str | None = None
        cover_bytes: bytes | None = None
        cover_media_type: str | None = None
        cover = book.cover
        if cover is not None:
            try:
                from soundbook.util.hashing import sha256_bytes

                cover_bytes = cover.read()
                cover_sha = sha256_bytes(cover_bytes)
                cover_media_type = cover.media_type
            except Exception:
                cover_sha = None
                cover_bytes = None

        info = BookInfo(
            book_id=sha256_file(book_path),
            path=str(book_path.resolve()),
            title=title,
            language=language,
            n_spine=len(documents),
            n_toc=len(book.toc),
            unsupported=None,
            obfuscated_fonts=tuple(book.obfuscated_fonts),
            cover_sha256=cover_sha,
        )
        nav = tuple(_flatten_toc(book.toc, source="nav"))
        outline = tuple(_flatten_toc(book.outline, source="outline"))
        return ParsedBook(info=info, documents=tuple(documents), nav=nav, outline=outline,
                          cover_bytes=cover_bytes, cover_media_type=cover_media_type)
    finally:
        try:
            book.close()
        except Exception:  # pragma: no cover
            pass


def book_id_from_path(path: str | Path) -> str:
    return sha256_file(os.fspath(path))
