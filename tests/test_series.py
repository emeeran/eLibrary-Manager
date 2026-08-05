"""Tests for series browse (spec 011 v1.3, AC-30..AC-33)."""

import pytest
from app.repositories import BookRepository
from app.schemas import BookCreate
from sqlalchemy.ext.asyncio import AsyncSession


def _book(title: str, series: str | None, idx: float | None, cover: str | None = None) -> BookCreate:
    return BookCreate(
        title=title,
        author=f"{title} Author",
        path=f"/books/{title}.epub",
        format="EPUB",
        file_size=1024,
        cover_path=cover,
        series=series,
        series_index=idx,
    )


async def _seed_series(db_session: AsyncSession) -> None:
    """Seed: Foundation x2 (idx 2 then 1 so ordering is exercised), Dune x1, one no-series."""
    repo = BookRepository(db_session)
    await repo.create(_book("Foundation 2", "Foundation", 2.0, cover="/c/found2"))
    await repo.create(_book("Foundation 1", "Foundation", 1.0, cover="/c/found1"))
    await repo.create(_book("Dune", "Dune", 1.0, cover="/c/dune"))
    await repo.create(_book("Standalone", None, None))
    await db_session.flush()


@pytest.mark.asyncio
async def test_list_series_with_meta_counts_and_representative(db_session: AsyncSession):
    """AC-30: distinct series with counts + representative cover (smallest series_index)."""
    await _seed_series(db_session)
    rows = await BookRepository(db_session).list_series_with_meta()

    # Ordered by count desc, then name. Foundation (2) before Dune (1).
    assert [r["name"] for r in rows] == ["Foundation", "Dune"]
    foundation = rows[0]
    assert foundation["count"] == 2
    # Representative cover is the smallest-series_index volume (Foundation 1).
    assert foundation["cover_path"] == "/c/found1"
    assert foundation["author"] == "Foundation 1 Author"
    assert rows[1]["count"] == 1


@pytest.mark.asyncio
async def test_books_in_series_ordered_by_index(db_session: AsyncSession):
    """AC-31: books in a series ordered by series_index ascending."""
    await _seed_series(db_session)
    books = await BookRepository(db_session).books_in_series("Foundation")
    assert [b.title for b in books] == ["Foundation 1", "Foundation 2"]


@pytest.mark.asyncio
async def test_books_in_series_unknown_returns_empty(db_session: AsyncSession):
    """AC-32: unknown series returns an empty list, not an error."""
    await _seed_series(db_session)
    assert await BookRepository(db_session).books_in_series("Nope") == []


@pytest.mark.asyncio
async def test_series_excludes_hidden_and_deleted(db_session: AsyncSession):
    """Hidden/deleted books are excluded from both the browse grid and the detail list."""
    repo = BookRepository(db_session)
    await repo.create(_book("Visible A", "Mystery", 1.0))
    await repo.create(_book("Visible B", "Mystery", 2.0))
    hidden = await repo.create(_book("Hidden C", "Mystery", 3.0))
    hidden.is_hidden = True
    deleted = await repo.create(_book("Deleted D", "Mystery", 4.0))
    deleted.is_deleted = True
    await db_session.flush()

    rows = await repo.list_series_with_meta()
    mystery = next((r for r in rows if r["name"] == "Mystery"), None)
    assert mystery is not None
    # Only the two non-hidden, non-deleted volumes count.
    assert mystery["count"] == 2
    titles = [b.title for b in await repo.books_in_series("Mystery")]
    assert set(titles) == {"Visible A", "Visible B"}


@pytest.mark.asyncio
async def test_get_series_routes(client, db_session: AsyncSession):
    """AC-30/31/32 at the route layer: /api/series and /api/series/{name}.

    ``client`` depends on ``db_session`` so they share one session — seeding via
    ``db_session`` is visible to the client's requests.
    """
    await _seed_series(db_session)

    resp = await client.get("/api/series")
    assert resp.status_code == 200
    data = resp.json()
    assert [r["name"] for r in data] == ["Foundation", "Dune"]
    assert data[0]["count"] == 2
    assert data[0]["cover_path"] == "/c/found1"

    detail = await client.get("/api/series/Foundation")
    assert detail.status_code == 200
    assert [b["title"] for b in detail.json()] == ["Foundation 1", "Foundation 2"]
    # series_index surfaced on the response (AC-23 still holds).
    assert detail.json()[0]["series_index"] == 1.0

    # AC-32: unknown series -> 200 empty list, not 404.
    unknown = await client.get("/api/series/Nope")
    assert unknown.status_code == 200
    assert unknown.json() == []
