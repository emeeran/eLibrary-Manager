"""Tests for the /open default-viewer bridge and login next-param (spec 014)."""


import pytest
from app.repositories import BookRepository
from app.schemas import BookCreate


async def _seed_book(db_session, path: str, **overrides):
    create = BookCreate(
        title="Seed Book",
        author="Author",
        path=path,
        format="EPUB",
        file_size=1024,
        **overrides,
    )
    return await BookRepository(db_session).create(create)


# --- GET /open ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_indexed_book_redirects_to_reader(client, db_session, tmp_path):
    """An already-indexed path goes straight to the reader — no re-import."""
    target = tmp_path / "book.epub"
    target.write_bytes(b"PK\x03\x04stub")
    book = await _seed_book(db_session, str(target))

    resp = await client.get("/open", params={"path": str(target)})
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/reader/{book.id}"


@pytest.mark.asyncio
async def test_open_rejects_unsupported_extension(client):
    resp = await client.get("/open", params={"path": "/tmp/notes.txt"})
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_open_missing_unindexed_file_redirects_to_pending_banner(
    client, db_session, tmp_path
):
    """A path that isn't indexed and doesn't exist never dead-ends."""
    missing = str(tmp_path / "gone.epub")
    resp = await client.get("/open", params={"path": missing})
    assert resp.status_code == 302
    assert "calibre_pending=" in resp.headers["location"]


@pytest.mark.asyncio
async def test_open_unindexed_existing_file_falls_back_to_banner_on_import_failure(
    client, db_session, tmp_path
):
    """A real but unparseable file: import is attempted, failure stays graceful."""
    bad = tmp_path / "garbage.epub"
    bad.write_bytes(b"not really an epub")
    resp = await client.get("/open", params={"path": str(bad)})
    assert resp.status_code == 302
    assert "calibre_pending=" in resp.headers["location"]


@pytest.mark.asyncio
async def test_open_hidden_book_never_bypasses_password(client, db_session, tmp_path):
    """Hidden books route to the library banner — same rule as /calibre/launch."""
    target = tmp_path / "secret.epub"
    target.write_bytes(b"PK\x03\x04stub")
    book = await _seed_book(db_session, str(target))
    book.is_hidden = True
    await db_session.flush()

    resp = await client.get("/open", params={"path": str(target)})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/library?calibre_hidden=1"


@pytest.mark.asyncio
async def test_open_requires_relative_paths_not_required(client):
    """A relative path is normalized against CWD without exploding."""
    resp = await client.get("/open", params={"path": "relative/book.epub"})
    # Not indexed and nonexistent → graceful banner, not a 500
    assert resp.status_code == 302
    assert "calibre_pending=" in resp.headers["location"]


# --- login ?next= ------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_page_request_preserves_target(client, monkeypatch):
    """Cold-session deep links survive: redirect carries ?next= with query."""
    import app.main as main_module

    async def _no_session(_token):
        return False

    monkeypatch.setattr(main_module, "validate_session", _no_session)
    monkeypatch.setenv("APP_ENV", "ci-auth")

    resp = await client.get("/open", params={"path": "/nas/EBOOKS/x.epub"}, follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("/login?next=")
    # The full target (path + query) must be preserved, encoded
    assert "open" in location and "path" in location
