#!/usr/bin/env python3
"""Write reviewable chapter-boundary drafts beside one local EPUB."""

from __future__ import annotations

import argparse
from pathlib import Path

from soundbook import PIPELINE_VERSION
from soundbook.config import ChapteringPolicy
from soundbook.ingest.chaptering import choose_strategy
from soundbook.ingest.loader import load_book


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument("--force", action="store_true", help="replace an existing .boundaries file")
    args = parser.parse_args()
    epub = args.epub.resolve()
    gold = epub.with_suffix(".boundaries")
    if gold.exists() and not args.force:
        parser.error(f"{gold} already exists; use --force to replace it")

    book = load_book(epub)
    strategy, drafts = choose_strategy(book, ChapteringPolicy())
    gold.write_text(
        f"# pipeline {PIPELINE_VERSION}\n"
        + "".join(f"{draft.start_key} # {draft.title}\n" for draft in drafts),
        encoding="utf-8",
    )
    headings = epub.with_suffix(".headings.txt")
    headings.write_text(
        "".join(
            f"{document.href}|{heading.idx}\t{heading.text}\n"
            for document in book.documents
            for heading in document.headings
        ),
        encoding="utf-8",
    )
    print(f"{epub.name}: strategy={strategy} chapters={len(drafts)}")
    print(f"wrote {gold}")
    print(f"wrote {headings}")


if __name__ == "__main__":
    main()
