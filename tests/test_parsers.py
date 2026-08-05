"""Tests for file parsers (spec 008): metadata extraction + corrupt handling.

The parsers were nearly untested (only init + content-extraction were covered).
These exercise ``extract_metadata`` on real generated EPUB/PDF and confirm
corrupt input surfaces ``EbookParsingError``.
"""

from pathlib import Path

import pytest
from app.exceptions import EbookParsingError
from app.parsers.epub_parser import EPUBParser
from app.parsers.mobi_parser import MOBIParser
from app.parsers.pdf_parser import PDFParser


def _make_epub(path: Path, title: str = "My EPUB Title", author: str = "An Author") -> None:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)
    chapter = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
    chapter.content = "<html><body><p>hello world</p></body></html>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


def _make_pdf(path: Path, body: str = "a generated pdf body") -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body)
    doc.save(str(path))
    doc.close()


@pytest.mark.asyncio
async def test_epub_extract_metadata(tmp_path: Path):
    p = tmp_path / "book.epub"
    _make_epub(p, title="The Title", author="The Author")
    meta = await EPUBParser(covers_path=str(tmp_path), book_images_path=str(tmp_path)).extract_metadata(
        str(p)
    )
    assert meta.title == "The Title"
    assert meta.author == "The Author"
    assert meta.format == "EPUB"


@pytest.mark.asyncio
async def test_pdf_extract_metadata_uses_filename(tmp_path: Path):
    p = tmp_path / "A-Pdf-Title.pdf"
    _make_pdf(p)
    meta = await PDFParser(covers_path=str(tmp_path), book_images_path=str(tmp_path)).extract_metadata(
        str(p)
    )
    assert meta.format == "PDF"
    # PDF parser falls back to the filename-derived title.
    assert meta.title and "A" in meta.title


@pytest.mark.asyncio
async def test_epub_corrupt_raises(tmp_path: Path):
    p = tmp_path / "bad.epub"
    p.write_bytes(b"not a zip and definitely not an epub payload")
    with pytest.raises(EbookParsingError):
        await EPUBParser(covers_path=str(tmp_path), book_images_path=str(tmp_path)).extract_metadata(
            str(p)
        )


@pytest.mark.asyncio
async def test_pdf_missing_file_raises(tmp_path: Path):
    # A non-existent path reliably makes fitz.open raise -> wrapped as EbookParsingError.
    with pytest.raises(EbookParsingError):
        await PDFParser(covers_path=str(tmp_path), book_images_path=str(tmp_path)).extract_metadata(
            str(tmp_path / "does-not-exist.pdf")
        )


@pytest.mark.asyncio
async def test_mobi_corrupt_raises(tmp_path: Path):
    p = tmp_path / "bad.mobi"
    p.write_bytes(b"not a mobi file at all")
    with pytest.raises(EbookParsingError):
        await MOBIParser(covers_path=str(tmp_path)).extract_metadata(str(p))
