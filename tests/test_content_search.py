"""Tests for full-text content search (spec 012): extraction, indexing, search.

The in-memory test DB uses ``Base.metadata.create_all`` (migrations never run),
so the FTS5 virtual tables are created explicitly in the ``content_fts`` fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def content_fts(db_session):
    """Create the FTS5 virtual tables the migrations would create in production.

    FTS tables aren't in ``Base.metadata`` so they survive ``db_session``'s
    drop/create — drop them here for per-test isolation.
    """
    await db_session.execute(text("DROP TABLE IF EXISTS books_fts"))
    await db_session.execute(text("DROP TABLE IF EXISTS books_content_fts"))
    await db_session.execute(text("CREATE VIRTUAL TABLE books_fts USING fts5(title, author)"))
    await db_session.execute(
        text("CREATE VIRTUAL TABLE books_content_fts USING fts5(book_id UNINDEXED, content)")
    )
    await db_session.commit()
    yield db_session


def _make_text_epub(path: Path, body: str = "the quick brown fox jumps") -> None:
    """Write a valid EPUB whose spine document contains ``body`` (via ebooklib)."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_title("T")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
    chapter.content = f"<html><body><p>{body}</p></body></html>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


def _make_text_pdf(path: Path, body: str = "the lazy dog sleeps") -> None:
    """Write a one-page PDF containing ``body`` via PyMuPDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), body)
    doc.save(str(path))
    doc.close()


# --------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------- #


async def test_extract_text_epub(tmp_path: Path) -> None:
    """EPUB body text is extracted and normalized."""
    from app.services.content_extractor import extract_text

    epub = tmp_path / "book.epub"
    _make_text_epub(epub, "callooh callay the vorpal blade went snicker snack")
    text_out = extract_text(str(epub), "EPUB")
    assert "callooh" in text_out
    assert "snicker snack" in text_out


async def test_extract_text_pdf(tmp_path: Path) -> None:
    """PDF page text is extracted."""
    from app.services.content_extractor import extract_text

    pdf = tmp_path / "book.pdf"
    _make_text_pdf(pdf, "the mitochondria is the powerhouse of the cell")
    text_out = extract_text(str(pdf), "PDF")
    assert "mitochondria" in text_out


async def test_extract_text_unknown_format_returns_empty(tmp_path: Path) -> None:
    """Unsupported formats yield empty text (never raise)."""
    from app.services.content_extractor import extract_text

    assert extract_text(str(tmp_path / "missing.txt"), "TXT") == ""


# --------------------------------------------------------------------- #
# Search integration
# --------------------------------------------------------------------- #


async def test_content_search_surfaces_body_match(content_fts) -> None:
    """A body-text hit surfaces the book even though title/author don't match."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(content_fts)
    book = await repo.create(
        BookCreate(
            title="A Plain Title",
            author="Alice",
            path="/tmp/plain.epub",
            file_size=10,
            format="EPUB",
        )
    )
    await content_fts.execute(
        text("INSERT INTO books_content_fts(book_id, content) VALUES (:bid, :content)"),
        {"bid": book.id, "content": "the sandworms of Arrakis are enormous"},
    )
    await content_fts.commit()

    books, total = await repo.list_with_count(search="sandworm")
    assert total == 1
    assert books[0].id == book.id


async def test_metadata_search_still_works(content_fts) -> None:
    """Title/author matching (ilike + metadata FTS path) still returns the book."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(content_fts)
    await repo.create(
        BookCreate(title="Dune Chronicles", author="Herbert", path="/tmp/d.epub", file_size=10)
    )
    await content_fts.commit()

    books, total = await repo.list_with_count(search="dune")
    assert total == 1
    assert books[0].title == "Dune Chronicles"


# --------------------------------------------------------------------- #
# Backfill end-to-end
# --------------------------------------------------------------------- #


async def test_backfill_indexes_and_enables_search(content_fts, tmp_path: Path) -> None:
    """Running the backfill extracts a real EPUB and makes it searchable by body text."""
    from app.repositories import BookContentRepository, BookRepository
    from app.schemas import BookCreate
    from app.services.content_backfill_service import run_content_backfill

    epub = tmp_path / "novel.epub"
    _make_text_epub(epub, "frumious bandersnatch whiffling through the tulgey wood")

    repo = BookRepository(content_fts)
    book = await repo.create(
        BookCreate(title="Jabberwocky", author="Carroll", path=str(epub), file_size=10, format="EPUB")
    )
    await content_fts.commit()

    stats = await run_content_backfill(content_fts)
    await content_fts.commit()

    assert stats["extracted"] >= 1
    status = (await BookContentRepository(content_fts).status_counts()).get("extracted", 0)
    assert status >= 1

    # The body term now finds the book via content FTS.
    books, total = await repo.list_with_count(search="bandersnatch")
    assert total == 1
    assert books[0].id == book.id


async def test_search_returns_content_snippet(content_fts) -> None:
    """A content match yields a context snippet via snippet()."""
    from app.repositories import BookContentRepository, BookRepository, _build_fts_query
    from app.schemas import BookCreate

    repo = BookRepository(content_fts)
    book = await repo.create(
        BookCreate(title="Plain Title", author="Alice", path="/tmp/snip.epub", file_size=10)
    )
    await content_fts.execute(
        text("INSERT INTO books_content_fts(book_id, content) VALUES (:bid, :content)"),
        {"bid": book.id, "content": "the sandworms of Arrakis are enormous creatures"},
    )
    await content_fts.commit()

    snips = await BookContentRepository(content_fts).snippets_for(
        [book.id], _build_fts_query("sandworm")
    )
    assert book.id in snips
    assert "sandworm" in snips[book.id].lower()


# --------------------------------------------------------------------- #
# Faceted filters + advanced search syntax (spec 012)
# --------------------------------------------------------------------- #


async def test_faceted_series_filter(db_session) -> None:
    """series_filter (multi-select) narrows to the chosen series."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    await repo.create(
        BookCreate(title="Foundation", author="Asimov", path="/tmp/f.epub", file_size=10, series="Foundation")
    )
    await repo.create(
        BookCreate(title="Dune", author="Herbert", path="/tmp/d.epub", file_size=10, series="Dune")
    )
    await db_session.commit()

    books, total = await repo.list_with_count(series_filter=["Foundation"])
    assert total == 1
    assert books[0].title == "Foundation"


async def test_faceted_rating_filter(db_session) -> None:
    """rating_min keeps only books at or above the threshold."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    low = await repo.create(BookCreate(title="Low", author="X", path="/tmp/low.epub", file_size=10))
    low.rating = 2
    high = await repo.create(BookCreate(title="High", author="Y", path="/tmp/high.epub", file_size=10))
    high.rating = 5
    await db_session.commit()

    books, total = await repo.list_with_count(rating_min=4)
    assert total == 1
    assert books[0].title == "High"


async def test_advanced_search_field_term(db_session) -> None:
    """``author:term`` is an ANDed ilike predicate (no FTS needed)."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    await repo.create(BookCreate(title="Rings", author="Tolkien", path="/tmp/r.epub", file_size=10))
    await repo.create(BookCreate(title="Others", author="Smith", path="/tmp/o.epub", file_size=10))
    await db_session.commit()

    books, total = await repo.list_with_count(search="author:tolkien")
    assert total == 1
    assert books[0].author == "Tolkien"


async def test_advanced_search_field_plus_bare(content_fts) -> None:
    """A field term ANDs with a bare term's ilike/FTS match."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(content_fts)
    await repo.create(
        BookCreate(title="Hobbit", author="Tolkien", path="/tmp/h.epub", file_size=10)
    )
    await repo.create(
        BookCreate(title="Rings", author="Tolkien", path="/tmp/rg.epub", file_size=10)
    )
    await content_fts.commit()

    # author:tolkien AND title contains "hobbit"
    books, total = await repo.list_with_count(search="author:tolkien hobbit")
    assert total == 1
    assert books[0].title == "Hobbit"


async def test_series_endpoint(client, db_session) -> None:
    """GET /api/books/series returns distinct series with counts."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    await repo.create(
        BookCreate(title="Foundation", author="Asimov", path="/tmp/f.epub", file_size=10, series="Foundation")
    )
    await repo.create(
        BookCreate(title="Foundation 2", author="Asimov", path="/tmp/f2.epub", file_size=10, series="Foundation")
    )
    await db_session.commit()

    resp = await client.get("/api/books/series")
    assert resp.status_code == 200
    foundation = next((s for s in resp.json() if s["name"] == "Foundation"), None)
    assert foundation is not None
    assert foundation["count"] == 2
