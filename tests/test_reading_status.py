"""Tests for reading_status shelves (item 1.5).

Covers the migration backfill mapping, the progress auto-advance rules,
and the reading_status list filter.
"""

import pytest
from app.models import Book
from app.repositories import BookRepository
from app.schemas import ProgressUpdate
from sqlalchemy import text


async def _make_book(db_session, *, progress=0.0, path="/test/rs.epub"):
    book = Book(
        title=f"Book {path}",
        author="A",
        path=path,
        format="EPUB",
        file_size=1,
        progress=progress,
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)
    return book


@pytest.mark.asyncio
async def test_backfill_mapping(db_session):
    """progress >=95 -> finished, >0 -> reading, else none (mirrors migration SQL)."""
    await _make_book(db_session, progress=100.0, path="/t/fin.epub")
    await _make_book(db_session, progress=40.0, path="/t/mid.epub")
    await _make_book(db_session, progress=0.0, path="/t/new.epub")
    # reading_status default is 'none' pre-backfill; run the migration's SQL.
    await db_session.execute(text("UPDATE books SET reading_status = 'none'"))
    await db_session.execute(
        text("UPDATE books SET reading_status = 'finished' WHERE progress >= 95")
    )
    await db_session.execute(
        text(
            "UPDATE books SET reading_status = 'reading' "
            "WHERE progress > 0 AND progress < 95"
        )
    )
    await db_session.commit()

    rows = dict(
        (await db_session.execute(text("SELECT path, reading_status FROM books")))
        .all()
    )
    assert rows["/t/fin.epub"] == "finished"
    assert rows["/t/mid.epub"] == "reading"
    assert rows["/t/new.epub"] == "none"


@pytest.mark.asyncio
async def test_progress_auto_advance(db_session):
    """Progress saves advance the shelf; to_read survives a zero-progress save."""
    repo = BookRepository(db_session)
    book = await _make_book(db_session)
    assert book.reading_status == "none"

    # Manually marked to-read...
    book.reading_status = "to_read"
    await db_session.commit()

    # ...a save with no real progress leaves it alone (AC 1.5.4).
    await repo.update_progress(book.id, ProgressUpdate(chapter_index=0, progress=0))
    await db_session.refresh(book)
    assert book.reading_status == "to_read"

    # Real progress starts the book (AC 1.5.3).
    await repo.update_progress(book.id, ProgressUpdate(chapter_index=1, progress=30))
    await db_session.refresh(book)
    assert book.reading_status == "reading"

    # Reaching the completion threshold finishes it.
    await repo.update_progress(book.id, ProgressUpdate(chapter_index=9, progress=96))
    await db_session.refresh(book)
    assert book.reading_status == "finished"


@pytest.mark.asyncio
async def test_reading_status_filter(db_session):
    """The list filter returns exactly the shelf's books."""
    repo = BookRepository(db_session)
    await _make_book(db_session, path="/t/a.epub")
    await _make_book(db_session, path="/t/b.epub")
    await db_session.execute(
        text("UPDATE books SET reading_status = 'to_read' WHERE path = '/t/a.epub'")
    )
    await db_session.commit()

    books, total = await repo.list_with_count(reading_status="to_read")
    assert total == 1
    assert books[0].path == "/t/a.epub"

    _, none_total = await repo.list_with_count(reading_status="reading")
    assert none_total == 0
