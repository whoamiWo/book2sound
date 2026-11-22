#!/usr/bin/env python3
"""Build a nine-chapter public-domain Ah Q EPUB from a plain-text source.

The source uses ``## <title>`` for chapter headings and blank lines between
paragraphs. The standard library is sufficient; --font optionally uses a local
TTF/OTF font plus ffmpeg drawtext for Chinese cover lettering.
"""

from __future__ import annotations

import argparse
import html
import shutil
import struct
import subprocess
import urllib.request
import zipfile
import zlib
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/baooab/The-true-story-of-Ah-Q/"
    "1402397efe0e18f3d6dbaaecd628c76647aa1ba3/content.md"
)
EXPECTED_TITLES = [
    "第一章 序",
    "第二章 优胜记略",
    "第三章 续优胜记略",
    "第四章 恋爱的悲剧",
    "第五章 生计问题",
    "第六章 从中兴到末路",
    "第七章 革命",
    "第八章 不准革命",
    "第九章 大团圆",
]


def parse_chapters(text: str) -> list[tuple[str, list[str]]]:
    chapters: list[tuple[str, list[str]]] = []
    title: str | None = None
    paragraphs: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## ") and not line.startswith("### "):
            if title is not None:
                chapters.append((title, paragraphs))
            title = line[3:].strip()
            if title == "目录":
                title = None
                paragraphs = []
                continue
            paragraphs = []
        elif title is not None and line and not line.startswith("<a "):
            paragraphs.append(line)
    if title is not None:
        chapters.append((title, paragraphs))
    if [title for title, _ in chapters] != EXPECTED_TITLES:
        raise ValueError("source must contain exactly the nine expected chapters")
    if any(not paragraphs for _, paragraphs in chapters):
        raise ValueError("every chapter must contain prose")
    return chapters


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def make_cover(path: Path, font_path: Path | None = None) -> None:
    """Create an original 1200x1600 PNG, with a typographic cover if possible."""
    width, height = 1200, 1600
    pixels = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 3
            border = x < 55 or x >= width - 55 or y < 55 or y >= height - 55
            inset_line = (x in (74, width - 75) or y in (74, height - 75))
            color = (206, 176, 110) if border or inset_line else (39, 67, 57)
            pixels[offset:offset + 3] = bytes(color)

    # Large, original vector-like Q, without importing an image dependency.
    for y in range(440, 1160):
        for x in range(250, 950):
            dx, dy = (x - 600) / 270, (y - 770) / 300
            radius = dx * dx + dy * dy
            if 0.68 < radius < 1.0 or (520 < x < 940 and abs(y - (860 + (x - 520) * 0.65)) < 28):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = bytes((222, 196, 133))

    # The original Q and frame are always drawn without an image dependency.
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = b"".join(b"\0" + pixels[y * width * 3:(y + 1) * width * 3]
                         for y in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header)
                     + _png_chunk(b"IDAT", zlib.compress(scanlines, 9))
                     + _png_chunk(b"IEND", b""))
    if font_path is not None:
        _add_cover_text(path, font_path)


def _add_cover_text(path: Path, font_path: Path) -> None:
    """Letter the cover with a local font, using ffmpeg's drawtext filter."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("cover lettering with --font requires ffmpeg")
    if not font_path.is_file():
        raise SystemExit(f"font not found: {font_path}")
    font = str(font_path).replace("\\", "\\\\").replace(":", "\\:")
    text = (
        f"drawtext=fontfile='{font}':text='阿Q正传':fontsize=108:fontcolor=white:x=250:y=180,"
        f"drawtext=fontfile='{font}':text='鲁迅':fontsize=48:fontcolor=white:x=470:y=1240"
    )
    titled = path.with_name(path.stem + ".titled.png")
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-vf", text,
         "-frames:v", "1", "-update", "1", str(titled)],
        check=True,
    )
    titled.replace(path)


def build_epub(source: Path, output: Path, cover: Path) -> None:
    chapters = parse_chapters(source.read_text(encoding="utf-8-sig"))
    identifier = "urn:uuid:2a2cc6cc-777f-4f2b-9870-9c9abeb7f1b1"
    files: dict[str, bytes] = {}
    manifest = [
        '<item id="cover-image" href="Images/cover.png" media-type="image/png" properties="cover-image"/>',
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
    ]
    spine = []
    nav_items = []
    for idx, (title, paragraphs) in enumerate(chapters, 1):
        escaped_title = html.escape(title)
        body = "\n".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
        files[f"OEBPS/Text/ch{idx}.xhtml"] = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">'
            f"<head><title>{escaped_title}</title></head><body>"
            f"<h1>{escaped_title}</h1>{body}</body></html>"
        ).encode()
        manifest.append(
            f'<item id="ch{idx}" href="Text/ch{idx}.xhtml" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="ch{idx}"/>')
        nav_items.append(f'<li><a href="Text/ch{idx}.xhtml">{escaped_title}</a></li>')
    files["OEBPS/Images/cover.png"] = cover.read_bytes()
    files["OEBPS/nav.xhtml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        '<head><title>目录</title></head><body><nav epub:type="toc"><h1>目录</h1><ol>'
        + "".join(nav_items) + "</ol></nav></body></html>"
    ).encode()
    files["OEBPS/content.opf"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="uid">{identifier}</dc:identifier>'
        '<dc:title>阿Q正传</dc:title><dc:creator>鲁迅</dc:creator>'
        '<dc:language>zh-CN</dc:language>'
        '<meta property="dcterms:modified">2026-11-21T00:00:00Z</meta>'
        f'<dc:source>{html.escape(SOURCE_URL)}</dc:source>'
        '</metadata><manifest>' + "".join(manifest) + '</manifest><spine>'
        + "".join(spine) + "</spine></package>"
    ).encode()
    files["META-INF/container.xml"] = (
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>'
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        mimetype = zipfile.ZipInfo("mimetype")
        mimetype.compress_type = zipfile.ZIP_STORED
        archive.writestr(mimetype, "application/epub+zip")
        for name, data in files.items():
            archive.writestr(name, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="downloaded source Markdown; fetched if omitted")
    parser.add_argument("--font", type=Path, help="local Chinese TTF/OTF for cover lettering")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source:
        source = args.source
    else:
        source = args.output.with_suffix(".source.md")
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            source.write_bytes(response.read())
    cover = args.output.with_suffix(".cover.png")
    make_cover(cover, args.font)
    build_epub(source, args.output, cover)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
