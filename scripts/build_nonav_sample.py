#!/usr/bin/env python3
"""Build a synthetic Chinese web-novel EPUB with no usable navigation.

The sample targets the one structure the local corpus does not cover: a
chapter-per-file web-novel conversion whose navigation document is missing and
whose chapter titles are plain paragraphs, not headings. The pipeline can only
fall back to ``spine`` there, so chapter titles become file names.

All text is original filler already used by the test suite (no third-party
prose). The EPUB is generated at run time and must stay out of the repository
(``corpus/`` is ignored); only its SHA256 prefix belongs in docs/benchmarks.md.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

#: Original filler sentences, reused from tests/helpers.CHINESE_PARAGRAPHS.
PARAGRAPHS = (
    "凌冽的寒风穿过山谷，卷起漫天碎雪，打在人的脸上生疼。",
    "他握紧了手中的刀，一步一步向山顶走去，脚步沉稳而坚定。",
    "山道两侧是深不见底的悬崖，偶尔有碎石滚落，久久听不到回音。",
    "“你来晚了。”一个苍老的声音从风雪中传来，仿佛就在耳边。",
    "老人坐在一块青石上，身旁放着一只旧茶壶，茶香在冷气中散开。",
    "“路还很长，”老人说，“但你已经走出了第一步。”",
)

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _xhtml(title: str, paragraphs: list[str]) -> str:
    body = "\n".join(f"<p>{text}</p>" for text in paragraphs)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
        f"<head><title>{title}</title></head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def _chapter_paragraphs(index: int) -> list[str]:
    count = 20 + (index % 9)  # 20–28 paragraphs, all above STUB_CHARS
    return [PARAGRAPHS[(index * 7 + offset) % len(PARAGRAPHS)] for offset in range(count)]


def build_epub(output: Path, chapters: int) -> None:
    documents: list[tuple[str, list[str]]] = [
        ("cover.xhtml", ["Cover"]),
        ("copyright.xhtml", ["版权页", "本样本为合成测试文本，仅用于分章流程验证。"]),
    ]
    for index in range(1, chapters + 1):
        documents.append(
            (f"part{index:03d}.xhtml", [f"第{index:03d}章", *_chapter_paragraphs(index)])
        )
    documents.append(("afterword.xhtml", ["完本感言", "感谢阅读这个用于流程验证的合成样本。"]))

    manifest = []
    spine = []
    files: dict[str, str] = {}
    for idx, (name, paragraphs) in enumerate(documents):
        files[f"OEBPS/Text/{name}"] = _xhtml(name.rsplit(".", 1)[0], paragraphs)
        manifest.append(
            f'    <item id="d{idx}" href="Text/{name}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'    <itemref idref="d{idx}"/>')

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '    <dc:identifier id="uid">urn:uuid:synthetic-nonav-webnovel</dc:identifier>\n'
        '    <dc:title>无导航样本（合成）</dc:title>\n'
        '    <dc:creator>soundbook tests</dc:creator>\n'
        '    <dc:language>zh-CN</dc:language>\n'
        "  </metadata>\n  <manifest>\n"
        + "\n".join(manifest) + "\n  </manifest>\n"
        + "  <spine>\n" + "\n".join(spine) + "\n  </spine>\n</package>\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        mimetype = zipfile.ZipInfo("mimetype")
        mimetype.compress_type = zipfile.ZIP_STORED
        archive.writestr(mimetype, "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/content.opf", opf)
        for name, data in files.items():
            archive.writestr(name, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--chapters", type=int, default=120)
    args = parser.parse_args()
    if args.chapters < 3:
        parser.error("a web-novel sample needs at least 3 chapters")
    build_epub(args.output, args.chapters)
    print(f"wrote {args.output} ({args.chapters} chapters, no nav)")


if __name__ == "__main__":
    main()
