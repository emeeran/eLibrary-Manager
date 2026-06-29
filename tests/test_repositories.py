"""Tests for repository layer."""

import pytest
from app.repositories import BookRepository, ChapterSummaryRepository, SettingsRepository
from app.schemas import BookCreate, ProgressUpdate
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def sample_book_data() -> dict:
    """Sample book creation data."""
    return {
        "title": "Test Book",
        "author": "Test Author",
        "path": "/test/book.epub",
        "format": "EPUB",
        "file_size": 1024,
    }


@pytest.mark.asyncio
async def test_create_book(db_session: AsyncSession, sample_book_data: dict):
    """Test creating a book."""
    repo = BookRepository(db_session)
    book_data = BookCreate(**sample_book_data)
    book = await repo.create(book_data)

    assert book.id is not None
    assert book.title == "Test Book"
    assert book.author == "Test Author"
    assert book.path == "/test/book.epub"
    assert book.format == "EPUB"


@pytest.mark.asyncio
async def test_create_duplicate_book_raises(db_session: AsyncSession, sample_book_data: dict):
    """Test that creating a duplicate book raises ValidationError."""
    from app.exceptions import ValidationError

    repo = BookRepository(db_session)
    book_data = BookCreate(**sample_book_data)
    await repo.create(book_data)

    with pytest.raises(ValidationError):
        await repo.create(BookCreate(**sample_book_data))


@pytest.mark.asyncio
async def test_get_book_by_id(db_session: AsyncSession, sample_book_data: dict):
    """Test retrieving a book by ID."""
    repo = BookRepository(db_session)
    book_data = BookCreate(**sample_book_data)
    created = await repo.create(book_data)

    found = await repo.get_by_id(created.id)
    assert found is not None
    assert found.id == created.id
    assert found.title == "Test Book"


@pytest.mark.asyncio
async def test_get_book_by_id_not_found(db_session: AsyncSession):
    """Test retrieving a non-existent book."""
    repo = BookRepository(db_session)
    result = await repo.get_by_id(9999)
    assert result is None


@pytest.mark.asyncio
async def test_get_book_by_path(db_session: AsyncSession, sample_book_data: dict):
    """Test retrieving a book by path."""
    repo = BookRepository(db_session)
    await repo.create(BookCreate(**sample_book_data))

    found = await repo.get_by_path("/test/book.epub")
    assert found is not None
    assert found.title == "Test Book"


@pytest.mark.asyncio
async def test_update_book(db_session: AsyncSession, sample_book_data: dict):
    """Test updating book metadata."""
    from app.schemas import BookUpdate

    repo = BookRepository(db_session)
    created = await repo.create(BookCreate(**sample_book_data))

    updated = await repo.update(created.id, BookUpdate(title="Updated Title", rating=4))
    assert updated.title == "Updated Title"
    assert updated.rating == 4


@pytest.mark.asyncio
async def test_update_progress(db_session: AsyncSession, sample_book_data: dict):
    """Test updating reading progress."""
    repo = BookRepository(db_session)
    created = await repo.create(BookCreate(**sample_book_data))

    progress = ProgressUpdate(chapter_index=3, progress=45.5)
    updated = await repo.update_progress(created.id, progress)
    assert updated.current_chapter == 3
    assert updated.progress == 45.5


@pytest.mark.asyncio
async def test_delete_book(db_session: AsyncSession, sample_book_data: dict):
    """Test deleting a book."""

    repo = BookRepository(db_session)
    created = await repo.create(BookCreate(**sample_book_data))
    await repo.delete(created.id)

    assert await repo.get_by_id(created.id) is None


@pytest.mark.asyncio
async def test_list_with_count_empty(db_session: AsyncSession):
    """Test listing books when empty."""
    repo = BookRepository(db_session)
    books, total = await repo.list_with_count()
    assert total == 0
    assert books == []


@pytest.mark.asyncio
async def test_list_with_count_pagination(db_session: AsyncSession):
    """Test pagination in list_with_count."""
    repo = BookRepository(db_session)

    for i in range(5):
        await repo.create(BookCreate(
            title=f"Book {i}",
            path=f"/test/book{i}.epub",
            format="EPUB",
            file_size=100,
        ))

    books, total = await repo.list_with_count(skip=0, limit=2)
    assert total == 5
    assert len(books) == 2

    books2, total2 = await repo.list_with_count(skip=2, limit=2)
    assert total2 == 5
    assert len(books2) == 2


@pytest.mark.asyncio
async def test_list_with_count_search(db_session: AsyncSession):
    """Test search filtering in list_with_count."""
    repo = BookRepository(db_session)

    await repo.create(BookCreate(
        title="Python Programming",
        author="Guido",
        path="/test/python.epub",
        format="EPUB",
        file_size=100,
    ))
    await repo.create(BookCreate(
        title="JavaScript Guide",
        author="Brendan",
        path="/test/js.epub",
        format="EPUB",
        file_size=100,
    ))

    books, total = await repo.list_with_count(search="Python")
    assert total == 1
    assert books[0].title == "Python Programming"

    books, total = await repo.list_with_count(search="Brendan")
    assert total == 1
    assert books[0].title == "JavaScript Guide"


@pytest.mark.asyncio
async def test_list_with_count_format_filter(db_session: AsyncSession):
    """Test format filter."""
    repo = BookRepository(db_session)

    await repo.create(BookCreate(
        title="EPUB Book", path="/test/a.epub", format="EPUB", file_size=100
    ))
    await repo.create(BookCreate(
        title="PDF Book", path="/test/b.pdf", format="PDF", file_size=100
    ))

    books, total = await repo.list_with_count(format_filter="EPUB")
    assert total == 1
    assert books[0].title == "EPUB Book"


@pytest.mark.asyncio
async def test_list_with_count_favorite_filter(db_session: AsyncSession):
    """Test favorite-only filter."""
    from app.schemas import BookUpdate

    repo = BookRepository(db_session)

    b1 = await repo.create(BookCreate(
        title="Fav Book", path="/test/fav.epub", format="EPUB", file_size=100
    ))
    await repo.update(b1.id, BookUpdate(is_favorite=True))

    await repo.create(BookCreate(
        title="Normal Book", path="/test/norm.epub", format="EPUB", file_size=100
    ))

    books, total = await repo.list_with_count(favorite_only=True)
    assert total == 1
    assert books[0].title == "Fav Book"


@pytest.mark.asyncio
async def test_count_total(db_session: AsyncSession):
    """Test count method."""
    repo = BookRepository(db_session)
    assert await repo.count() == 0

    await repo.create(BookCreate(
        title="Book 1", path="/test/1.epub", format="EPUB", file_size=100
    ))
    await repo.create(BookCreate(
        title="Book 2", path="/test/2.epub", format="EPUB", file_size=100
    ))
    assert await repo.count() == 2


@pytest.mark.asyncio
async def test_settings_crud(db_session: AsyncSession):
    """Test settings repository CRUD operations."""
    repo = SettingsRepository(db_session)

    # Set
    await repo.set("test_key", "test_value")
    # Get
    val = await repo.get("test_key")
    assert val == "test_value"

    # Update
    await repo.set("test_key", "updated_value")
    val = await repo.get("test_key")
    assert val == "updated_value"

    # Get all
    await repo.set("other_key", "other_value")
    all_settings = await repo.get_all()
    assert "test_key" in all_settings
    assert "other_key" in all_settings

    # Delete
    await repo.delete("test_key")
    assert await repo.get("test_key") is None

    # Default value
    assert await repo.get("nonexistent", "default") == "default"


@pytest.mark.asyncio
async def test_chapter_summary_cache(db_session: AsyncSession, sample_book_data: dict):
    """Test chapter summary caching."""
    book_repo = BookRepository(db_session)
    summary_repo = ChapterSummaryRepository(db_session)

    book = await book_repo.create(BookCreate(**sample_book_data))

    # No cached summary
    cached = await summary_repo.get_cached_summary(book.id, 0)
    assert cached is None

    # Create summary
    summary = await summary_repo.create(
        book_id=book.id,
        chapter_index=0,
        chapter_title="Chapter 1",
        summary_text="This is a summary of chapter 1.",
        provider="test"
    )
    assert summary.id is not None

    # Now cached
    cached = await summary_repo.get_cached_summary(book.id, 0)
    assert cached is not None
    assert cached.summary_text == "This is a summary of chapter 1."

    # Get all by book
    all_summaries = await summary_repo.get_by_book(book.id)
    assert len(all_summaries) == 1
