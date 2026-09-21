"""Tests for the bulk book operations endpoint (item 1.8)."""

import pytest
import pytest_asyncio
from app.models import Book, Category


@pytest_asyncio.fixture
async def books(db_session):
    """Three books and one category."""
    rows = [
        Book(title=f"B{i}", path=f"/test/bulk{i}.epub", format="EPUB", file_size=1)
        for i in range(3)
    ]
    db_session.add_all(rows)
    db_session.add(Category(name="BulkCat"))
    await db_session.commit()
    for row in rows:
        await db_session.refresh(row)
    return rows


@pytest.mark.asyncio
async def test_bulk_set_rating_and_status(client, db_session, books):
    ids = [b.id for b in books]
    resp = await client.patch(
        "/api/books/bulk", json={"ids": ids, "op": "set_rating", "value": 4}
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3

    resp = await client.patch(
        "/api/books/bulk",
        json={"ids": ids, "op": "set_reading_status", "value": "to_read"},
    )
    assert resp.status_code == 200
    for book in books:
        await db_session.refresh(book)
        assert book.rating == 4
        assert book.reading_status == "to_read"


@pytest.mark.asyncio
async def test_bulk_partial_failure_reports(client, db_session, books):
    """A missing id fails that entry but the rest still apply."""
    ids = [books[0].id, books[1].id, 999999]
    resp = await client.patch(
        "/api/books/bulk", json={"ids": ids, "op": "set_favorite", "value": True}
    )
    data = resp.json()
    assert resp.status_code == 200
    assert data["updated"] == 2
    assert data["failed"] == [{"id": 999999, "error": "not found"}]
    await db_session.refresh(books[0])
    assert books[0].is_favorite is True


@pytest.mark.asyncio
async def test_bulk_soft_delete(client, db_session, books):
    ids = [b.id for b in books]
    resp = await client.patch(
        "/api/books/bulk", json={"ids": ids, "op": "soft_delete"}
    )
    assert resp.status_code == 200
    for book in books:
        await db_session.refresh(book)
        assert book.is_deleted is True


@pytest.mark.asyncio
async def test_bulk_invalid_input_rejected(client, books):
    for payload in (
        {"ids": [], "op": "set_rating", "value": 3},
        {"ids": [1], "op": "unknown_op"},
        {"ids": [1], "op": "set_rating", "value": 9},
        {"ids": [1], "op": "set_rating", "value": True},  # bool is not a rating
        {"ids": [1], "op": "set_favorite", "value": "yes"},
        {"ids": [1], "op": "set_reading_status", "value": "maybe"},
        {"ids": [1], "op": "set_category", "value": 424242},
    ):
        resp = await client.patch("/api/books/bulk", json=payload)
        assert resp.status_code == 422, payload


@pytest.mark.asyncio
async def test_bulk_set_category(client, db_session, books):
    """set_category writes the book→category links."""
    from sqlalchemy import text

    cat_id = (await db_session.execute(text("SELECT id FROM categories"))).scalar()
    resp = await client.patch(
        "/api/books/bulk",
        json={"ids": [books[0].id], "op": "set_category", "value": cat_id},
    )
    assert resp.status_code == 200
    rows = (
        await db_session.execute(
            text("SELECT category_id FROM book_categories WHERE book_id = :b"),
            {"b": books[0].id},
        )
    ).scalars().all()
    assert rows == [cat_id]
