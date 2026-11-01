"""Tests for reading-session tracking and stats aggregation (item 2.2)."""

import pytest
import pytest_asyncio
from app.models import Book, ReadingSession


@pytest_asyncio.fixture
async def book(db_session):
    book = Book(
        title="Session Book",
        path="/test/session.epub",
        format="EPUB",
        file_size=1,
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)
    return book


@pytest.mark.asyncio
async def test_session_endpoint_records_minutes(client, book):
    resp = await client.post(f"/api/books/{book.id}/session", json={"seconds": 600})
    assert resp.status_code == 200
    assert resp.json() == {"recorded": True, "minutes": 10.0}


@pytest.mark.asyncio
async def test_session_endpoint_ignores_empty(client, book):
    resp = await client.post(f"/api/books/{book.id}/session", json={"seconds": 0})
    assert resp.status_code == 200
    assert resp.json() == {"recorded": False}


@pytest.mark.asyncio
async def test_stats_use_tracked_sessions(client, db_session, book):
    """Sessions drive tracked minutes, today's progress, and the source flag."""
    db_session.add(ReadingSession(book_id=book.id, minutes=25.0))
    await db_session.commit()

    resp = await client.get("/api/stats/reading")
    data = resp.json()
    assert data["reading_time_source"] == "tracked"
    assert data["tracked_minutes"] >= 25.0
    assert data["today_minutes"] >= 25.0
    assert data["daily_goal_minutes"] == 30
    assert data["goal_progress_pct"] <= 100
    assert data["reading_streak"] >= 1


@pytest.mark.asyncio
async def test_stats_fall_back_to_estimate_without_sessions(client, db_session):
    resp = await client.get("/api/stats/reading")
    data = resp.json()
    assert data["reading_time_source"] == "estimated"
    assert data["tracked_minutes"] == 0
