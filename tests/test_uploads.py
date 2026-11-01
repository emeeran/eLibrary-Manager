"""Tests for upload size limits, magic-byte sniffing, and /api/health."""

import pytest
from app.main import app
from app.routes.library import _upload_signature_matches

# --- _upload_signature_matches ----------------------------------------------


def _write(tmp_path, name: str, payload: bytes):
    f = tmp_path / name
    f.write_bytes(payload)
    return str(f)


def test_epub_magic_accepted(tmp_path):
    path = _write(tmp_path, "a.epub", b"PK\x03\x04" + b"x" * 64)
    assert _upload_signature_matches(path, ".epub") is True


def test_epub_rejects_non_zip(tmp_path):
    path = _write(tmp_path, "a.epub", b"#!/bin/sh\nrm -rf /\n")
    assert _upload_signature_matches(path, ".epub") is False


def test_pdf_magic_accepted(tmp_path):
    path = _write(tmp_path, "a.pdf", b"%PDF-1.7\n...")
    assert _upload_signature_matches(path, ".pdf") is True


def test_pdf_with_junk_prefix_accepted(tmp_path):
    """Spec allows bytes before %PDF within the first 1KB."""
    path = _write(tmp_path, "a.pdf", b"junk" * 200 + b"%PDF-1.7")
    assert _upload_signature_matches(path, ".pdf") is True


def test_mobi_magic_at_offset_60(tmp_path):
    path = _write(tmp_path, "a.mobi", b"\x00" * 60 + b"BOOKMOBI" + b"rest")
    assert _upload_signature_matches(path, ".mobi") is True


def test_mobi_rejects_wrong_magic(tmp_path):
    path = _write(tmp_path, "a.mobi", b"\x00" * 60 + b"NOTMAGIC")
    assert _upload_signature_matches(path, ".mobi") is False


def test_unknown_extension_rejected(tmp_path):
    path = _write(tmp_path, "a.exe", b"MZ\x90\x00")
    assert _upload_signature_matches(path, ".exe") is False


def test_missing_file_rejected(tmp_path):
    assert _upload_signature_matches(str(tmp_path / "gone.epub"), ".epub") is False


# --- POST /api/library/upload ------------------------------------------------


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client, monkeypatch, tmp_path):
    """A body over max_upload_size_mb returns 413 and is not persisted."""
    from app.config import get_config

    monkeypatch.setattr(get_config(), "max_upload_size_mb", 1)

    # Build just over the 1MB limit (zip magic so the size check trips first)
    payload = b"PK\x03\x04" + b"\0" * (1024 * 1024 + 100)
    resp = await client.post(
        "/api/library/upload",
        files={"file": ("big.epub", payload, "application/epub+zip")},
    )
    assert resp.status_code == 413
    assert "limit" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_rejects_misnamed_payload(client):
    """Content that isn't the claimed format returns 415."""
    payload = b"this is definitely not a zip file"
    resp = await client.post(
        "/api/library/upload",
        files={"file": ("fake.epub", payload, "application/epub+zip")},
    )
    assert resp.status_code == 415
    assert "does not match" in resp.json()["detail"]


# --- GET /api/health ---------------------------------------------------------


@pytest.mark.asyncio
async def test_health_ok_with_db(client):
    """Healthy DB → 200 ok; NAS unset in tests → null, not failure."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] is True


@pytest.mark.asyncio
async def test_health_degraded_when_db_down(client, monkeypatch):
    """A DB that fails SELECT 1 → 503 degraded."""
    from app.database import get_db

    class _BrokenSession:
        async def execute(self, _query):
            raise RuntimeError("database disk image is malformed")

    async def _broken_db():
        yield _BrokenSession()

    app.dependency_overrides[get_db] = _broken_db
    try:
        resp = await client.get("/api/health")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] is False


@pytest.mark.asyncio
async def test_health_degraded_when_nas_down(client, monkeypatch):
    """A configured-but-unhealthy NAS backend → 503."""
    app = client._transport.app

    class _SickBackend:
        async def health_check(self):
            return {"healthy": False, "details": "stale mount"}

    original = getattr(app.state, "nas_backend", None)
    app.state.nas_backend = _SickBackend()
    try:
        resp = await client.get("/api/health")
    finally:
        app.state.nas_backend = original
    assert resp.status_code == 503
    assert resp.json()["nas"] is False
