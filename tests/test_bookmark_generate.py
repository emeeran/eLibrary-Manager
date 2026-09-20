"""Tests for POST /books/{id}/bookmarks/generate (spec 004 v1.1, AC-18..20)."""

import pytest
from app.repositories import BookRepository
from app.schemas import BookCreate
from app.services import ReaderService

_TOC = [
    {"index": 0, "title": "Chapter One", "level": 1},
    {"index": 1, "title": "Chapter Two", "level": 1},
    {"index": 4, "title": "Chapter Three", "level": 2},
]


async def _seed_book(db_session, path: str = "/tmp/seed.epub") -> int:
    book = await BookRepository(db_session).create(
        BookCreate(
            title="Seed",
            author="Author",
            path=path,
            format="EPUB",
            file_size=1024,
            total_chapters=5,
        )
    )
    await db_session.flush()
    return book.id


@pytest.fixture
def fake_toc(monkeypatch):
    """Stub ReaderService.get_table_of_contents with canned entries."""

    async def _toc(self, book_id):
        return list(_TOC)

    monkeypatch.setattr(
        "app.services.reader_service.ReaderService.get_table_of_contents", _toc
    )


@pytest.mark.asyncio
async def test_generate_creates_bookmark_per_toc_entry(client, db_session, fake_toc):
    """AC-004.18: one bookmark per TOC entry at position 0."""
    book_id = await _seed_book(db_session)

    resp = await client.post(f"/api/books/{book_id}/bookmarks/generate")
    assert resp.status_code == 200
    assert resp.json() == {"created": 3, "total_available": 3}

    bookmarks = await ReaderService(db_session).list_bookmarks(book_id)
    assert {b.title for b in bookmarks} == {"Chapter One", "Chapter Two", "Chapter Three"}
    by_title = {b.title: b for b in bookmarks}
    assert by_title["Chapter Three"].chapter_index == 4
    assert all(b.position_in_chapter == 0 for b in bookmarks)


@pytest.mark.asyncio
async def test_generate_refuses_when_bookmarks_exist(client, db_session, fake_toc):
    """AC-004.19: existing bookmarks (manual or generated) are never touched."""

    book_id = await _seed_book(db_session)
    service = ReaderService(db_session)
    await service.create_bookmark(
        book_id=book_id, chapter_index=2, position_in_chapter=10, title="My spot"
    )

    resp = await client.post(f"/api/books/{book_id}/bookmarks/generate")
    assert resp.status_code == 409
    assert "already has bookmarks" in resp.json()["detail"]

    bookmarks = await service.list_bookmarks(book_id)
    assert [b.title for b in bookmarks] == ["My spot"]  # unchanged


@pytest.mark.asyncio
async def test_generate_without_toc_returns_422(client, db_session, monkeypatch):
    """AC-004.20: no TOC entries → explicit 422, nothing created."""

    async def _empty(self, book_id):
        return []

    monkeypatch.setattr(
        "app.services.reader_service.ReaderService.get_table_of_contents", _empty
    )

    book_id = await _seed_book(db_session)
    resp = await client.post(f"/api/books/{book_id}/bookmarks/generate")
    assert resp.status_code == 422
    assert "No table of contents" in resp.json()["detail"]
    assert await ReaderService(db_session).list_bookmarks(book_id) == []


@pytest.mark.asyncio
async def test_generate_caps_at_max(client, db_session, monkeypatch):
    """The 200-entry ceiling keeps page-per-chapter PDFs from flooding the panel."""
    from app.routes.reader import MAX_GENERATED_BOOKMARKS

    big_toc = [{"index": i, "title": f"Page {i + 1}", "level": 1} for i in range(250)]

    async def _big(self, book_id):
        return big_toc

    monkeypatch.setattr(
        "app.services.reader_service.ReaderService.get_table_of_contents", _big
    )

    book_id = await _seed_book(db_session)
    resp = await client.post(f"/api/books/{book_id}/bookmarks/generate")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"created": MAX_GENERATED_BOOKMARKS, "total_available": 250}
    assert len(await ReaderService(db_session).list_bookmarks(book_id)) == 200


@pytest.mark.asyncio
async def test_generate_is_scoped_to_book(client, db_session, fake_toc):
    """Generating for book A must not seed book B (isolation, mirrors AC-004.11)."""

    book_a = await _seed_book(db_session, "/tmp/a.epub")
    book_b = await _seed_book(db_session, "/tmp/b.epub")

    await client.post(f"/api/books/{book_b}/bookmarks/generate")  # give B bookmarks

    resp = await client.post(f"/api/books/{book_a}/bookmarks/generate")
    # A still has none of its own → generation proceeds for A only
    assert resp.status_code == 200
    assert await ReaderService(db_session).list_bookmarks(book_b)  # B untouched by A's run
