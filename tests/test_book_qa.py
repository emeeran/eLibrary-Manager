"""Tests for "Ask this book" (item 2.1): retrieval, refusals, endpoint contract."""

import pytest
from sqlalchemy import text

from app.models import Book
from app.services.book_qa import select_passages, question_terms

MITOSIS = (
    "Mitosis is the process of cell division producing two identical cells. "
    "Prophase, metaphase, anaphase, and telophase are its stages. "
) * 3 + (
    "Photosynthesis converts light into chemical energy inside chloroplasts. "
) * 3


def test_question_terms_drop_stopwords():
    terms = question_terms("What is the function of mitochondria in a cell?")
    assert "mitochondria" in terms
    assert "the" not in terms and "of" not in terms


def test_select_passages_ranks_relevant_window_first():
    passages = select_passages(MITOSIS, "How does photosynthesis work?", window=300, step=150)
    assert passages
    assert "Photosynthesis" in passages[0]
    assert "Mitosis" not in passages[0]


def test_select_passages_no_match_returns_empty():
    assert select_passages(MITOSIS, "quantum entanglement贝尔") == []


def test_select_passages_empty_content():
    assert select_passages("", "anything") == []


@pytest.mark.asyncio
async def test_ask_unindexed_book_rejected(client, db_session):
    from app.models import Book as _B  # noqa: F401
    await db_session.execute(
        text("CREATE VIRTUAL TABLE IF NOT EXISTS books_content_fts USING fts5(book_id UNINDEXED, content)")
    )
    book = Book(
        title="No Content", path="/test/nocontent.epub", format="EPUB", file_size=1
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)

    resp = await client.post(
        f"/api/books/{book.id}/ask", json={"question": "What is mitosis?"}
    )
    assert resp.status_code == 422
    assert "content-indexed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ask_input_validation(client):
    for payload in ({}, {"question": ""}, {"question": "x" * 501}):
        resp = await client.post("/api/books/1/ask", json=payload)
        assert resp.status_code == 422, payload


@pytest.mark.asyncio
async def test_ask_no_term_match_answers_directly(client, db_session):
    """Terms absent from the text are answered without an AI call."""
    await db_session.execute(
        text("CREATE VIRTUAL TABLE IF NOT EXISTS books_content_fts USING fts5(book_id UNINDEXED, content)")
    )
    book = Book(
        title="Indexed", path="/test/indexed.epub", format="EPUB", file_size=1
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)
    await db_session.execute(
        text("INSERT INTO books_content_fts(book_id, content) VALUES (:b, :c)"),
        {"b": book.id, "c": MITOSIS},
    )
    await db_session.commit()

    async def _fail():
        raise AssertionError("orchestrator must not be called")

    import app.ai_engine as ai_engine_mod

    original = ai_engine_mod.get_ai_orchestrator
    ai_engine_mod.get_ai_orchestrator = _fail
    try:
        resp = await client.post(
            f"/api/books/{book.id}/ask", json={"question": "quantum entanglement"}
        )
    finally:
        ai_engine_mod.get_ai_orchestrator = original

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "The book doesn't seem to cover that."
    assert data["passages"] == []
    assert data["provider"] is None
