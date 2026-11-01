"""Tests for annotation highlight styles (spec 005 v1.2).

The style field round-trips through the annotation API, validates against
the allowed set, defaults to legacy 'highlight', and maps to the file
embedder's PDF annotation subtypes / EPUB span CSS.
"""

from __future__ import annotations

import pytest
from app.schemas import BookCreate
from app.services.annotation_embedder import _STYLE_EPUB_CSS, _STYLE_PDF_TYPE, EmbedItem

pytestmark = pytest.mark.asyncio


async def _make_book(client, db_session) -> int:
    """Create a book row directly and return its id."""
    from app.repositories import BookRepository

    repo = BookRepository(db_session)
    book = await repo.create(
        BookCreate(title="Style Test", path="/test/style.epub", format="EPUB", file_size=100)
    )
    return book.id


async def test_annotation_style_roundtrip(client, db_session) -> None:
    """Creating an annotation with each style persists and lists it back."""
    book_id = await _make_book(client, db_session)

    for style in ("underline", "squiggly", "strikethrough"):
        resp = await client.post(
            f"/api/books/{book_id}/annotations",
            json={
                "chapter_index": 0,
                "start_position": 4,
                "end_position": 24,
                "text": "The highlighted sentence",
                "color": "blue",
                "style": style,
            },
        )
        assert resp.status_code == 200, f"style={style}: {resp.text}"
        assert resp.json()["style"] == style

    listing = await client.get(f"/api/books/{book_id}/annotations")
    styles = {a["style"] for a in listing.json()["annotations"]}
    assert styles == {"underline", "squiggly", "strikethrough"}


async def test_annotation_style_default_is_highlight(client, db_session) -> None:
    """Omitting style yields the legacy 'highlight' behavior."""
    book_id = await _make_book(client, db_session)
    resp = await client.post(
        f"/api/books/{book_id}/annotations",
        json={
            "chapter_index": 0,
            "start_position": 0,
            "end_position": 3,
            "text": "The",
            "color": "yellow",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["style"] == "highlight"


async def test_annotation_style_validation(client, db_session) -> None:
    """An unknown style is rejected with 422 and stored nowhere."""
    book_id = await _make_book(client, db_session)
    resp = await client.post(
        f"/api/books/{book_id}/annotations",
        json={
            "chapter_index": 0,
            "start_position": 0,
            "end_position": 3,
            "text": "The",
            "color": "yellow",
            "style": "glow",
        },
    )
    assert resp.status_code == 422
    listing = await client.get(f"/api/books/{book_id}/annotations")
    assert all(a["style"] != "glow" for a in listing.json()["annotations"])


def test_embedder_style_maps_to_pdf_types() -> None:
    """Each style maps to its PyMuPDF annotation subtype and EPUB CSS."""
    assert _STYLE_PDF_TYPE["squiggly"] == "SQUIGGLY"
    assert _STYLE_PDF_TYPE["strikethrough"] == "STRIKEOUT"
    assert _STYLE_PDF_TYPE["underline"] == "UNDERLINE"
    assert _STYLE_PDF_TYPE["highlight"] == "HIGHLIGHT"

    item = EmbedItem(key="a1", quoted="text", note="", color="yellow", style="squiggly")
    css = _STYLE_EPUB_CSS[item.style].format(color="#fff59d")
    assert "wavy" in css and "background:none" in css
    highlight_css = _STYLE_EPUB_CSS["highlight"].format(color="#fff59d")
    assert highlight_css == "background:#fff59d;"
