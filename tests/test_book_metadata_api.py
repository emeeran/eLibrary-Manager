"""Tests for the book metadata PATCH endpoint (review + editable metadata)."""

import pytest
import pytest_asyncio
from app.models import Book


@pytest_asyncio.fixture
async def book(db_session):
    """One book row to PATCH against."""
    book = Book(
        title="Patch Target",
        author="Author",
        path="/test/patch-target.epub",
        format="EPUB",
        file_size=1234,
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)
    return book


@pytest.mark.asyncio
async def test_review_round_trip(client, db_session, book):
    """A saved review persists and comes back through the API."""
    resp = await client.patch(
        f"/api/books/{book.id}", json={"review": "A cracking read."}
    )
    assert resp.status_code == 200
    assert resp.json()["review"] == "A cracking read."

    resp = await client.get(f"/api/books/{book.id}")
    assert resp.json()["review"] == "A cracking read."


@pytest.mark.asyncio
async def test_review_explicit_null_clears(client, db_session, book):
    """Sending review: null clears an existing review."""
    await client.patch(f"/api/books/{book.id}", json={"review": "temp"})
    resp = await client.patch(f"/api/books/{book.id}", json={"review": None})
    assert resp.status_code == 200
    assert resp.json()["review"] is None


@pytest.mark.asyncio
async def test_review_omitted_does_not_touch_others(client, db_session, book):
    """A PATCH without review leaves title/author intact (exclude_unset)."""
    resp = await client.patch(
        f"/api/books/{book.id}", json={"title": "Renamed"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Renamed"
    assert data["author"] == "Author"


@pytest.mark.asyncio
async def test_review_over_length_rejected(client, db_session, book):
    """Reviews are capped at 20k chars (422 beyond)."""
    resp = await client.patch(
        f"/api/books/{book.id}", json={"review": "x" * 20001}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_hand_edit_sets_metadata_edited(client, db_session, book):
    """Editing a protected field raises the metadata_edited shield."""
    resp = await client.patch(
        f"/api/books/{book.id}", json={"publisher": "Chilton"}
    )
    assert resp.status_code == 200
    assert resp.json()["metadata_edited"] is True


@pytest.mark.asyncio
async def test_reading_state_edit_does_not_set_flag(client, db_session, book):
    """favorite/progress edits are not metadata edits."""
    resp = await client.patch(f"/api/books/{book.id}", json={"is_favorite": True})
    assert resp.status_code == 200
    assert resp.json()["metadata_edited"] is False


@pytest.mark.asyncio
async def test_over_length_fields_rejected(client, db_session, book):
    """Column-length violations 422 (language max 20, publisher max 300)."""
    resp = await client.patch(f"/api/books/{book.id}", json={"language": "x" * 21})
    assert resp.status_code == 422
    resp = await client.patch(f"/api/books/{book.id}", json={"publisher": "x" * 301})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_series_index_round_trip(client, db_session, book):
    """Series + numeric index save and come back."""
    resp = await client.patch(
        f"/api/books/{book.id}", json={"series": "Dune", "series_index": 1.5}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["series"] == "Dune"
    assert data["series_index"] == 1.5
