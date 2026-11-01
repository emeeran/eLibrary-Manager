"""Tests for AI metadata enrichment (item 2.4)."""

import pytest
from app.models import Book
from app.services.metadata_enrichment import build_prompt, parse_proposals
from sqlalchemy import text


def test_parse_proposals_keeps_allowed_keys_only():
    raw = """Here you go:
    {"title": "Dune", "author": "Frank Herbert", "isbn": "123", "hacker": "x"}
    """
    result = parse_proposals(raw)
    assert result == {"title": "Dune", "author": "Frank Herbert"}


def test_parse_proposals_handles_fenced_and_garbage():
    fenced = '```json\n{"description": "A desert planet epic."}\n```'
    assert parse_proposals(fenced) == {"description": "A desert planet epic."}
    assert parse_proposals("no json at all") == {}
    assert parse_proposals('{"title": 42}') == {}


def test_parse_proposals_caps_lengths():
    raw = '{"title": "' + "x" * 600 + '"}'
    assert len(parse_proposals(raw)["title"]) == 500


def test_build_prompt_truncates_sample():
    prompt = build_prompt("some_file.pdf", "word " * 5000)
    assert "some_file.pdf" in prompt
    assert len(prompt) < 2000  # sample is cut to 1200 chars


@pytest.mark.asyncio
async def test_enrich_unindexed_rejected(client, db_session):
    await db_session.execute(
        text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS books_content_fts "
            "USING fts5(book_id UNINDEXED, content)"
        )
    )
    book = Book(
        title="Not Indexed", path="/test/ni.epub", format="EPUB", file_size=1
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)

    resp = await client.post(f"/api/books/{book.id}/enrich", json={})
    assert resp.status_code == 422
    assert "content-indexed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_enrich_returns_proposals_without_writing(client, db_session):
    await db_session.execute(
        text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS books_content_fts "
            "USING fts5(book_id UNINDEXED, content)"
        )
    )
    book = Book(title="Enrich Me", path="/test/enrich.epub", format="EPUB", file_size=1)
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)
    await db_session.execute(
        text("INSERT INTO books_content_fts(book_id, content) VALUES (:b, :c)"),
        {"b": book.id, "c": "The desert planet Arrakis, source of spice."},
    )
    await db_session.commit()

    class _Orch:
        current_provider = "fake"

        async def complete_text(self, prompt, max_tokens=500):
            assert "enrich.epub" in prompt
            return '{"publisher": "Chilton", "language": "eng"}'

    async def _orch():
        return _Orch()

    import app.ai_engine as ai_engine_mod

    original = ai_engine_mod.get_ai_orchestrator
    ai_engine_mod.get_ai_orchestrator = _orch
    try:
        resp = await client.post(f"/api/books/{book.id}/enrich", json={})
    finally:
        ai_engine_mod.get_ai_orchestrator = original

    assert resp.status_code == 200
    data = resp.json()
    assert data["proposals"] == {"publisher": "Chilton", "language": "eng"}
    # Nothing written: a fresh GET still shows no publisher.
    detail = await client.get(f"/api/books/{book.id}")
    assert detail.json()["publisher"] is None
