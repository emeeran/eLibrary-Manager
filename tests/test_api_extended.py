"""Extended API endpoint tests."""

import uuid

import pytest
from app.models import Book
from app.schemas import BookCreate
from httpx import AsyncClient


async def _create_test_book(db_session) -> Book:
    """Helper: create a unique test book in the database."""
    from app.repositories import BookRepository
    uid = uuid.uuid4().hex[:8]
    repo = BookRepository(db_session)
    return await repo.create(BookCreate(
        title=f"Test Book {uid}",
        author="Test Author",
        path=f"/test/book_{uid}.epub",
        format="EPUB",
        file_size=2048,
    ))


# ============================================
# BOOK ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_books_list_pagination(client: AsyncClient):
    """Test books listing with pagination parameters."""
    response = await client.get("/api/books?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "books" in data
    assert data["page"] == 1
    assert len(data["books"]) <= 2  # page_size limits results


@pytest.mark.asyncio
async def test_books_list_search(client: AsyncClient, db_session):
    """Test books listing with search."""
    from app.repositories import BookRepository
    repo = BookRepository(db_session)
    await repo.create(BookCreate(
        title="Unique Search Title",
        author="Unique Author",
        path="/test/search_book.epub",
        format="EPUB",
        file_size=100,
    ))

    response = await client.get("/api/books?search=Unique Search")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["books"][0]["title"] == "Unique Search Title"


@pytest.mark.asyncio
async def test_books_list_sort(client: AsyncClient, db_session):
    """Test books listing with sorting."""
    from app.repositories import BookRepository
    repo = BookRepository(db_session)
    await repo.create(BookCreate(
        title="Alpha", path="/test/a.epub", format="EPUB", file_size=100
    ))
    await repo.create(BookCreate(
        title="Zeta", path="/test/z.epub", format="EPUB", file_size=100
    ))

    # Sort by title ascending
    response = await client.get("/api/books?sort_by=title&sort_order=asc")
    assert response.status_code == 200
    books = response.json()["books"]
    assert len(books) >= 2
    titles = [b["title"] for b in books]
    assert titles == sorted(titles)


@pytest.mark.asyncio
async def test_book_update_favorite(client: AsyncClient, db_session):
    """Test toggling favorite on a book."""
    book = await _create_test_book(db_session)

    response = await client.post(f"/api/books/{book.id}/favorite")
    assert response.status_code == 200
    assert response.json()["is_favorite"] is True

    response = await client.post(f"/api/books/{book.id}/favorite")
    assert response.status_code == 200
    assert response.json()["is_favorite"] is False


@pytest.mark.asyncio
async def test_stats_endpoint(client: AsyncClient):
    """Test library stats endpoint."""
    response = await client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_books" in data


@pytest.mark.asyncio
async def test_book_update_progress(client: AsyncClient, db_session):
    """Test updating reading progress."""
    book = await _create_test_book(db_session)

    response = await client.post(
        f"/api/books/{book.id}/progress",
        json={"chapter_index": 2, "progress": 35.5}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_book_delete(client: AsyncClient, db_session):
    """Test deleting a book."""
    book = await _create_test_book(db_session)

    response = await client.delete(f"/api/books/{book.id}")
    assert response.status_code == 200

    response = await client.get(f"/api/books/{book.id}")
    assert response.status_code == 404


# ============================================
# BOOKMARK ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_bookmark_crud(client: AsyncClient, db_session):
    """Test bookmark create, list, get, delete."""
    book = await _create_test_book(db_session)

    # Create
    response = await client.post(
        f"/api/books/{book.id}/bookmarks",
        json={"chapter_index": 1, "position_in_chapter": 100, "title": "Test Bookmark"}
    )
    assert response.status_code == 200
    bookmark = response.json()
    assert bookmark["chapter_index"] == 1
    assert bookmark["title"] == "Test Bookmark"
    bookmark_id = bookmark["id"]

    # List
    response = await client.get(f"/api/books/{book.id}/bookmarks")
    assert response.status_code == 200
    assert len(response.json()["bookmarks"]) == 1

    # Delete
    response = await client.delete(f"/api/bookmarks/{bookmark_id}")
    assert response.status_code == 200

    # Verify deleted
    response = await client.get(f"/api/books/{book.id}/bookmarks")
    assert len(response.json()["bookmarks"]) == 0


# ============================================
# NOTE ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_note_crud(client: AsyncClient, db_session):
    """Test note create, list, delete."""
    book = await _create_test_book(db_session)

    # Create
    response = await client.post(
        f"/api/books/{book.id}/notes",
        json={
            "chapter_index": 0,
            "position_in_chapter": 50,
            "content": "This is an important passage",
            "color": "yellow",
            "quoted_text": "important passage"
        }
    )
    assert response.status_code == 200
    note = response.json()
    assert note["content"] == "This is an important passage"
    assert note["color"] == "yellow"
    note_id = note["id"]

    # List
    response = await client.get(f"/api/books/{book.id}/notes")
    assert response.status_code == 200
    assert len(response.json()["notes"]) == 1

    # Delete
    response = await client.delete(f"/api/notes/{note_id}")
    assert response.status_code == 200


# ============================================
# ANNOTATION ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_annotation_crud(client: AsyncClient, db_session):
    """Test annotation create, list, delete."""
    book = await _create_test_book(db_session)

    # Create
    response = await client.post(
        f"/api/books/{book.id}/annotations",
        json={
            "chapter_index": 0,
            "start_position": 10,
            "end_position": 50,
            "text": "Highlighted text here",
            "color": "green",
            "note": "This is interesting"
        }
    )
    assert response.status_code == 200
    annotation = response.json()
    assert annotation["text"] == "Highlighted text here"
    assert annotation["color"] == "green"
    annotation_id = annotation["id"]

    # List
    response = await client.get(f"/api/books/{book.id}/annotations")
    assert response.status_code == 200
    assert len(response.json()["annotations"]) == 1

    # List with chapter filter
    response = await client.get(f"/api/books/{book.id}/annotations?chapter_index=0")
    assert response.status_code == 200
    assert len(response.json()["annotations"]) == 1

    # Delete
    response = await client.delete(f"/api/annotations/{annotation_id}")
    assert response.status_code == 200


# ============================================
# SETTINGS ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_settings_get_defaults(client: AsyncClient):
    """Test getting default settings."""
    response = await client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "library_path" in data
    assert "theme" in data
    assert "font_size" in data


@pytest.mark.asyncio
async def test_settings_update(client: AsyncClient):
    """Test updating settings."""
    response = await client.post(
        "/api/settings",
        json={"theme": "night", "font_size": 18}
    )
    assert response.status_code == 200

    # Verify update
    response = await client.get("/api/settings")
    assert response.json()["theme"] == "night"
    assert response.json()["font_size"] == 18


# ============================================
# TTS ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_tts_engines(client: AsyncClient):
    """Test TTS engines listing."""
    response = await client.get("/api/tts/engines")
    assert response.status_code == 200
    data = response.json()
    assert len(data["engines"]) == 3
    assert data["default_engine"] == "edgetts"


@pytest.mark.asyncio
async def test_tts_voices(client: AsyncClient):
    """Test TTS voices listing."""
    response = await client.get("/api/tts/voices?engine=edgetts")
    assert response.status_code == 200
    data = response.json()
    assert len(data["voices"]) > 0


@pytest.mark.asyncio
async def test_tts_synthesize_empty_text(client: AsyncClient):
    """Test TTS with empty text returns 400."""
    response = await client.post("/api/tts/synthesize", json={"text": ""})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_tts_stream_empty_text(client: AsyncClient):
    """Test TTS stream with empty text returns 400."""
    response = await client.post("/api/tts/stream", json={"text": ""})
    assert response.status_code == 400


# ============================================
# CATEGORIES ENDPOINTS
# ============================================

@pytest.mark.asyncio
async def test_categories_crud(client: AsyncClient, db_session):
    """Test category create, list, delete."""
    # Create
    response = await client.post(
        "/api/categories",
        json={"name": "Fiction", "color": "#ff0000"}
    )
    assert response.status_code == 201
    cat = response.json()
    cat_id = cat["id"]
    assert cat["name"] == "Fiction"

    # List
    response = await client.get("/api/categories")
    assert response.status_code == 200
    cats = response.json()
    assert any(c["name"] == "Fiction" for c in cats)

    # Delete
    response = await client.delete(f"/api/categories/{cat_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_assign_category_to_book(client: AsyncClient, db_session):
    """Test assigning a category to a book."""
    book = await _create_test_book(db_session)

    # Create category
    response = await client.post(
        "/api/categories",
        json={"name": "Science", "color": "#00ff00"}
    )
    cat_id = response.json()["id"]

    # Assign
    response = await client.post(
        f"/api/books/{book.id}/categories",
        json={"category_ids": [cat_id]}
    )
    assert response.status_code == 200


# ============================================
# EXPORT ENDPOINT (markdown + json)
# ============================================

@pytest.mark.asyncio
async def test_export_markdown(client: AsyncClient, db_session):
    """Markdown export returns book title and a markdown blob."""
    book = await _create_test_book(db_session)
    await client.post(
        f"/api/books/{book.id}/bookmarks",
        json={"chapter_index": 0, "position_in_chapter": 0, "title": "Mark One"},
    )
    resp = await client.get(f"/api/books/{book.id}/export?format=markdown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["book_title"] == book.title
    assert "Mark One" in data["markdown"]


@pytest.mark.asyncio
async def test_export_json_structure_and_disposition(client: AsyncClient, db_session):
    """JSON export returns structured data as a downloadable attachment."""
    book = await _create_test_book(db_session)
    await client.post(
        f"/api/books/{book.id}/bookmarks",
        json={"chapter_index": 2, "position_in_chapter": 50, "title": "BK"},
    )
    await client.post(
        f"/api/books/{book.id}/notes",
        json={"chapter_index": 2, "position_in_chapter": 50, "content": "a note", "color": "yellow"},
    )

    resp = await client.get(f"/api/books/{book.id}/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment" in resp.headers["content-disposition"]
    assert ".json" in resp.headers["content-disposition"]

    payload = resp.json()
    assert payload["book"]["title"] == book.title
    assert len(payload["bookmarks"]) == 1
    assert payload["bookmarks"][0]["title"] == "BK"
    assert len(payload["notes"]) == 1
    assert payload["notes"][0]["content"] == "a note"
    assert "exported_at" in payload


@pytest.mark.asyncio
async def test_export_rejects_bad_format(client: AsyncClient, db_session):
    """Unknown format values are rejected with 400."""
    book = await _create_test_book(db_session)
    resp = await client.get(f"/api/books/{book.id}/export?format=csv")
    assert resp.status_code == 400
