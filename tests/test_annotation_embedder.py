"""Tests for embedding annotations into book files (spec 005 v1.1, AC-005.18)."""

import zipfile

import fitz
import pytest
from app.services.annotation_embedder import (
    EmbedItem,
    UnsupportedFormatError,
    embed_annotations_into_file,
)

_QUOTE = "The quiet mountain village held its breath."


def _make_epub(path, body_text: str) -> None:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("embed-test")
    book.set_title("Embed Test")
    book.set_language("en")
    ch = epub.EpubHtml(title="Chapter 1", file_name="ch1.xhtml", lang="en")
    ch.content = f"<html><body><h1>C1</h1><p>{body_text}</p></body></html>"
    book.add_item(ch)
    book.add_item(epub.EpubNcx())
    book.spine = [ch]
    epub.write_epub(str(path), book)


def _chapter_content(path) -> str:
    """Read the first chapter document out of the EPUB zip."""
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith("ch1.xhtml"):
                return zf.read(name).decode("utf-8")
    raise AssertionError("chapter entry not found")


def test_epub_embed_wraps_quote_and_is_idempotent(tmp_path):
    """Quote gets wrapped with the marker span; a second run embeds nothing."""
    body = "Before the storm. " + _QUOTE + " After the storm."
    path = tmp_path / "book.epub"
    _make_epub(path, body)

    items = [EmbedItem(key="a1", quoted=_QUOTE, note="remember this", color="green")]
    result = embed_annotations_into_file("EPUB", str(path), items)
    assert result == {"format": "EPUB", "embedded": 1, "skipped": 0}

    content = _chapter_content(path)
    assert 'data-elm-annot="a1"' in content
    assert 'title="remember this"' in content
    assert "background:#c8e6c9" in content
    assert _QUOTE in content  # text preserved inside the span

    # Re-run: idempotent, nothing new embedded
    result2 = embed_annotations_into_file("EPUB", str(path), items)
    assert result2["embedded"] == 1  # counted as already-done
    content2 = _chapter_content(path)
    assert content2.count("data-elm-annot") == 1  # no duplicate wrap


def test_epub_embed_skips_unlocatable_quote(tmp_path):
    """A quote not present in the file is reported skipped, never forced."""
    path = tmp_path / "book.epub"
    _make_epub(path, "Nothing relevant here.")
    items = [EmbedItem(key="a1", quoted=_QUOTE, note="", color="yellow")]
    result = embed_annotations_into_file("EPUB", str(path), items)
    assert result == {"format": "EPUB", "embedded": 0, "skipped": 1}


def test_pdf_embed_adds_native_highlight_and_note(tmp_path):
    """PDF highlights are real PDF annots; notes become comment popups."""
    path = tmp_path / "book.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), _QUOTE, fontsize=11)
    doc.save(str(path))
    doc.close()

    items = [
        EmbedItem(key="a1", quoted=_QUOTE, note="key scene", color="yellow"),
        EmbedItem(key="a2", quoted="this text is not in the pdf", note="", color="blue"),
    ]
    result = embed_annotations_into_file("PDF", str(path), items)
    assert result == {"format": "PDF", "embedded": 1, "skipped": 1}

    doc = fitz.open(str(path))
    page = doc[0]  # keep the page alive — annots are bound to it
    annots = list(page.annots() or [])
    kinds = {a.type[1] for a in annots}
    assert "Highlight" in kinds
    assert "Text" in kinds  # the note popup
    doc.close()


def test_mobi_format_is_rejected(tmp_path):
    """MOBI cannot carry embedded annotations (spec: 422 upstream)."""
    with pytest.raises(UnsupportedFormatError):
        embed_annotations_into_file("MOBI", str(tmp_path / "b.mobi"), [])


@pytest.mark.asyncio
async def test_route_embed_round_trip(client, db_session, tmp_path):
    """POST /annotations/embed wires book -> annotations -> file."""
    from app.models import Annotation
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    body = "Lead in. " + _QUOTE + " Lead out."
    path = tmp_path / "route.epub"
    _make_epub(path, body)
    book = await BookRepository(db_session).create(
        BookCreate(title="Route", author="A", path=str(path), format="EPUB", file_size=10)
    )
    await db_session.flush()
    db_session.add(
        Annotation(
            book_id=book.id,
            chapter_index=0,
            start_position=10,
            end_position=20,
            text=_QUOTE,
            color="yellow",
        )
    )
    await db_session.commit()

    resp = await client.post(f"/api/books/{book.id}/annotations/embed")
    assert resp.status_code == 200
    body_json = resp.json()
    assert body_json["embedded"] == 1
    assert 'data-elm-annot="a1"' in _chapter_content(path)

