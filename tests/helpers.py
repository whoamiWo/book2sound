"""Tiny synthetic EPUB builder used by the test suite.

Fixtures are generated at test time (never committed) so the repository stays
free of third-party text. Everything here is stdlib-only.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass
class Chapter:
    title: str
    paragraphs: list[str]
    anchor: str | None = None      # id placed on the first paragraph
    anchor_paragraph: int = 0      # which paragraph carries the id
    headings: list[str] = field(default_factory=list)  # extra <h2> inserted


def _xhtml(title: str, chapter: Chapter) -> str:
    body: list[str] = [f"<h1>{title}</h1>"]
    for idx, text in enumerate(chapter.paragraphs):
        anchor = ""
        if chapter.anchor and idx == chapter.anchor_paragraph:
            anchor = f' id="{chapter.anchor}"'
        body.append(f"<p{anchor}>{text}</p>")
        if chapter.headings and idx == 0:
            for heading in chapter.headings:
                body.append(f"<h2>{heading}</h2>")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
        f"<head><title>{title}</title></head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )


def _nav(entries: list[tuple[str, str]], depth_children: bool) -> str:
    items = []
    for label, href in entries:
        items.append(f'      <li><a href="{href}">{label}</a></li>')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>nav</title></head><body>\n"
        '  <nav epub:type="toc"><ol>\n' + "\n".join(items) + "\n  </ol></nav>\n"
        "</body></html>\n"
    )


def make_epub(
    path: Path,
    chapters: list[Chapter],
    *,
    nav_entries: list[tuple[str, str]] | None = None,
    encryption_xml: str | None = None,
    image_only: bool = False,
) -> Path:
    """Write a minimal, valid EPUB 3 with a nav document (unless nav_entries=[])."""

    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    spine = []
    files: dict[str, str | bytes] = {}
    for idx, chapter in enumerate(chapters):
        name = f"Text/ch{idx + 1}.xhtml"
        files[f"OEBPS/{name}"] = _xhtml(chapter.title, chapter)
        manifest.append(
            f'    <item id="ch{idx + 1}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'    <itemref idref="ch{idx + 1}"/>')

    if nav_entries is None:
        nav_entries = [(c.title, f"Text/ch{i + 1}.xhtml") for i, c in enumerate(chapters)]
    if nav_entries:
        files["OEBPS/nav.xhtml"] = _nav(nav_entries, depth_children=False)
        manifest.append(
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>')

    if image_only:
        # replace all text with a single image per page
        for idx, _chapter in enumerate(chapters):
            files[f"OEBPS/Text/ch{idx + 1}.xhtml"] = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>p</title></head>'
                '<body><img src="../Images/page.png" alt=""/></body></html>\n')
        files["OEBPS/Images/page.png"] = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">urn:uuid:test-book</dc:identifier>\n'
        '    <dc:title>测试之书</dc:title>\n'
        '    <dc:language>zh-CN</dc:language>\n'
        "  </metadata>\n  <manifest>\n"
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
        + "\n".join(manifest) + "\n  </manifest>\n"
        '  <spine toc="ncx">\n' + "\n".join(spine) + "\n  </spine>\n</package>\n")
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        "<head/><docTitle><text>t</text></docTitle><navMap/>"
        "</ncx>\n")

    with zipfile.ZipFile(path, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        if encryption_xml:
            zf.writestr("META-INF/encryption.xml", encryption_xml)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        for name, data in files.items():
            zf.writestr(name, data)
    return path


CHINESE_PARAGRAPHS = [
    "凌冽的寒风穿过山谷，卷起漫天碎雪，打在人的脸上生疼。",
    "他握紧了手中的刀，一步一步向山顶走去，脚步沉稳而坚定。",
    "山道两侧是深不见底的悬崖，偶尔有碎石滚落，久久听不到回声。",
    "“你来晚了。”一个苍老的声音从风雪中传来，仿佛就在耳边。",
    "老人坐在一块青石上，身旁放着一只旧茶壶，茶香在冷气中散开。",
    "“路还很长，”老人说，“但你已经走出了第一步。”",
]


def simple_book(path: Path, n_chapters: int = 5, paras: int = 12) -> Path:
    paragraphs = (CHINESE_PARAGRAPHS * ((paras // len(CHINESE_PARAGRAPHS)) + 1))[:paras]
    chapters = [
        Chapter(title=f"第{i + 1}章 风雪夜归人", paragraphs=paragraphs)
        for i in range(n_chapters)
    ]
    return make_epub(path, chapters)


FONT_ENCRYPTION = """<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
  xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>
    <enc:CipherData><enc:CipherReference URI="OEBPS/Fonts/font.otf"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>
"""

REAL_DRM = """<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
  xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>
    <enc:KeyInfo><enc:EncryptedKey/></enc:KeyInfo>
    <enc:CipherData><enc:CipherReference URI="OEBPS/Text/ch1.xhtml"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>
"""
