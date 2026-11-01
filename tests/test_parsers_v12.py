"""Tests for the v1.2 format parsers (spec 008 v1.2): FB2, CBZ, Markdown.

Each parser is exercised on real generated files covering the unified parser
interface (metadata, cover, chapters, count, TOC, single chapter) plus the
scanner routing (extension dispatch + scan inclusion).
"""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest
from app.exceptions import EbookParsingError
from app.parsers.cbz_parser import CBZParser
from app.parsers.fb2_parser import FB2Parser
from app.parsers.md_parser import MDParser
from app.scanner import LibraryScanner

# --------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------- #


def _make_fb2(path: Path, title: str = "FB2 Book", sections: int = 3) -> None:
    """Write a minimal valid FB2 with a cover binary and N sections."""
    sections_xml = "".join(
        f"""
        <section>
          <title><p>Section {i + 1}</p></title>
          <p>Paragraph text of section {i + 1}.</p>
          <empty-line/>
          <p>More <emph>emphasized</emph> text.</p>
        </section>"""
        for i in range(sections)
    )
    cover_b64 = base64.b64encode(b"\xff\xd8\xff\xe0fakejpeg").decode()
    path.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"
             xmlns:l="http://www.w3.org/1999/xlink">
  <description>
    <title-info>
      <genre>sci_fi</genre>
      <author><first-name>Jane</first-name><last-name>Doe</last-name></author>
      <book-title>{title}</book-title>
      <annotation>Test annotation text</annotation>
      <lang>en</lang>
      <coverpage><image l:href="#cover.jpg"/></coverpage>
    </title-info>
    <publish-info><publisher>Test Press</publisher><year>2024</year></publish-info>
  </description>
  <body>{sections_xml}</body>
  <binary id="cover.jpg" content-type="image/jpeg">{cover_b64}</binary>
</FictionBook>""",
        encoding="utf-8",
    )


def _make_cbz(path: Path, pages: int = 4) -> None:
    """Write a minimal CBZ with N PNG pages and a ComicInfo.xml."""
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ComicInfo.xml", """<ComicInfo>
  <Title>The Comic</Title><Series>Awesome Series</Series><Number>3</Number>
  <Writer>Cartoonist</Writer><Genre>Action, Comedy</Genre>
</ComicInfo>""")
        for i in range(pages):
            zf.writestr(f"page_{i:03d}.png", png)


def _make_md(path: Path) -> None:
    """Write a Markdown doc with a title heading and two chapters."""
    path.write_text(
        """# My Markdown Book

Intro paragraph with **bold** and `code`.

## Sub Heading

Some detail.

# Chapter Two

- item one
- item two

```
code block
line two
```
""",
        encoding="utf-8",
    )


# --------------------------------------------------------------------- #
# FB2
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fb2_metadata(tmp_path: Path) -> None:
    p = tmp_path / "book.fb2"
    _make_fb2(p, title="The FB2 Title")
    meta = await FB2Parser(covers_path=str(tmp_path)).extract_metadata(str(p))
    assert meta.title == "The FB2 Title"
    assert meta.author == "Jane Doe"
    assert meta.format == "FB2"
    assert meta.description == "Test annotation text"
    assert meta.language == "en"
    assert meta.publisher == "Test Press"
    assert meta.subjects == ["sci_fi"]


@pytest.mark.asyncio
async def test_fb2_cover_extracted(tmp_path: Path) -> None:
    p = tmp_path / "book.fb2"
    _make_fb2(p)
    cover = await FB2Parser(covers_path=str(tmp_path)).extract_cover(str(p))
    assert cover is not None
    assert Path(cover).exists()


@pytest.mark.asyncio
async def test_fb2_chapters(tmp_path: Path) -> None:
    p = tmp_path / "book.fb2"
    _make_fb2(p, sections=3)
    parser = FB2Parser(covers_path=str(tmp_path))
    chapters = await parser.get_chapters(str(p))
    assert [t for _, t, _ in chapters] == ["Section 1", "Section 2", "Section 3"]
    assert "Paragraph text of section 1." in chapters[0][2]
    assert "<em>emphasized</em>" in chapters[0][2]
    assert await parser.count_chapters(str(p)) == 3
    toc = await parser.get_table_of_contents(str(p))
    assert toc[1] == {"index": 1, "title": "Section 2", "level": 1}
    content, title, total = await parser.get_single_chapter(str(p), 2)
    assert title == "Section 3"
    assert total == 3
    assert "section 3" in content


@pytest.mark.asyncio
async def test_fb2_corrupt_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.fb2"
    p.write_text("<FictionBook><unclosed>", encoding="utf-8")
    with pytest.raises(EbookParsingError):
        await FB2Parser(covers_path=str(tmp_path)).extract_metadata(str(p))


# --------------------------------------------------------------------- #
# CBZ
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cbz_metadata_from_comicinfo(tmp_path: Path) -> None:
    p = tmp_path / "comic.cbz"
    _make_cbz(p)
    meta = await CBZParser(covers_path=str(tmp_path)).extract_metadata(str(p))
    assert meta.title == "The Comic"
    assert meta.author == "Cartoonist"
    assert meta.format == "CBZ"
    assert meta.subjects == ["Action", "Comedy"]


@pytest.mark.asyncio
async def test_cbz_pages_are_chapters(tmp_path: Path) -> None:
    p = tmp_path / "comic.cbz"
    _make_cbz(p, pages=4)
    parser = CBZParser(covers_path=str(tmp_path))
    chapters = await parser.get_chapters(str(p))
    assert len(chapters) == 4
    assert chapters[2][1] == "Page 3"
    assert "data:image/png;base64," in chapters[0][2]
    assert await parser.count_chapters(str(p)) == 4
    cover = await parser.extract_cover(str(p))
    assert cover is not None and Path(cover).exists()
    content, title, total = await parser.get_single_chapter(str(p), 3)
    assert title == "Page 4" and total == 4


@pytest.mark.asyncio
async def test_cbz_corrupt_raises(tmp_path: Path) -> None:
    p = tmp_path / "broken.cbz"
    p.write_bytes(b"not a zip")
    with pytest.raises(EbookParsingError):
        await CBZParser(covers_path=str(tmp_path)).extract_metadata(str(p))


# --------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_md_metadata_uses_title_heading(tmp_path: Path) -> None:
    p = tmp_path / "notes.md"
    _make_md(p)
    meta = await MDParser(covers_path=str(tmp_path)).extract_metadata(str(p))
    assert meta.title == "My Markdown Book"
    assert meta.format == "MD"
    assert await MDParser(covers_path=str(tmp_path)).extract_cover(str(p)) is None


@pytest.mark.asyncio
async def test_md_chapters_split_on_h1(tmp_path: Path) -> None:
    p = tmp_path / "notes.md"
    _make_md(p)
    parser = MDParser(covers_path=str(tmp_path))
    chapters = await parser.get_chapters(str(p))
    assert [t for _, t, _ in chapters] == ["My Markdown Book", "Chapter Two"]
    assert "<strong>bold</strong>" in chapters[0][2]
    assert "<ul><li>item one</li><li>item two</li></ul>" in chapters[1][2]
    assert "<pre><code>" in chapters[1][2]
    assert await parser.count_chapters(str(p)) == 2


@pytest.mark.asyncio
async def test_md_without_headings_is_single_chapter(tmp_path: Path) -> None:
    p = tmp_path / "plain.md"
    p.write_text("Just a paragraph.\n\nAnother one.\n", encoding="utf-8")
    parser = MDParser(covers_path=str(tmp_path))
    chapters = await parser.get_chapters(str(p))
    assert len(chapters) == 1
    assert chapters[0][1] == "plain"
    assert "<p>Just a paragraph.</p>" in chapters[0][2]


# --------------------------------------------------------------------- #
# Scanner routing (spec 008 AC-008.08 analog for the new formats)
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_scanner_routes_new_formats(tmp_path: Path) -> None:
    scanner = LibraryScanner()
    fb2 = tmp_path / "a.fb2"
    cbz = tmp_path / "b.cbz"
    md = tmp_path / "c.md"
    _make_fb2(fb2)
    _make_cbz(cbz)
    _make_md(md)

    fb2_meta = await scanner.extract_metadata(str(fb2))
    assert fb2_meta.format == "FB2"
    cbz_meta = await scanner.extract_metadata(str(cbz))
    assert cbz_meta.format == "CBZ"
    md_meta = await scanner.extract_metadata(str(md))
    assert md_meta.format == "MD"

    chapters = await scanner.get_chapters(str(md))
    assert len(chapters) == 2
    assert ".fb2" in LibraryScanner.SUPPORTED_FORMATS
    assert ".cbz" in LibraryScanner.SUPPORTED_FORMATS
    assert ".md" in LibraryScanner.SUPPORTED_FORMATS
