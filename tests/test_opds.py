"""Tests for OPDS catalog support (spec 015).

All catalog feeds are served from in-process fixtures by monkeypatching
``app.services.opds_service.fetch_url`` — no network access in tests.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import cast

import pytest
from app.schemas import OpdsCatalogCreate
from app.services import opds_service as opds_module
from app.services.opds_service import OpdsService

pytestmark = pytest.mark.asyncio

# --------------------------------------------------------------------- #
# Feed fixtures (Atom / OPDS 1.x style)
# --------------------------------------------------------------------- #

NAVIGATION_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:uuid:root</id>
  <title>Test Catalog</title>
  <updated>2026-11-01T00:00:00Z</updated>
  <entry>
    <id>urn:uuid:nav1</id>
    <title>Science Fiction</title>
    <summary>Sci-fi shelf</summary>
    <link rel="subsection" href="/section/scifi" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  </entry>
</feed>
"""

ACQUISITION_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <id>urn:uuid:acq</id>
  <title>Science Fiction</title>
  <entry>
    <id>urn:uuid:book1</id>
    <title>Example Book</title>
    <summary>An example book</summary>
    <author><name>Jane Doe</name></author>
    <link rel="http://opds-spec.org/image/thumbnail" href="/covers/1.png" type="image/png"/>
    <link rel="http://opds-spec.org/acquisition" href="/files/1.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""


def _fake_fetch(
    body: bytes, status: int = 200
) -> Callable[..., object]:
    """Build a monkeypatch replacement for opds_service.fetch_url."""

    async def _fetch(url: str, **kwargs: object) -> bytes:
        if status != 200:
            raise opds_module.OpdsCatalogError(
                f"Catalog returned HTTP {status}", {"url": url}
            )
        if kwargs.get("password"):
            seen_auth.append(
                base64.b64encode(
                    f"{kwargs.get('username')}:{kwargs.get('password')}".encode()
                ).decode()
            )
        seen_urls.append(url)
        return body

    seen_auth: list[str] = []
    seen_urls: list[str] = []
    _fetch.auth_seen = seen_auth  # type: ignore[attr-defined]
    _fetch.urls_seen = seen_urls  # type: ignore[attr-defined]
    return cast(Callable[..., object], _fetch)


# --------------------------------------------------------------------- #
# Catalog CRUD
# --------------------------------------------------------------------- #


async def test_create_and_list_catalog(client) -> None:
    resp = await client.post(
        "/api/opds/catalogs",
        json={"name": "Calibre-Web", "url": "https://example.com/opds"},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["name"] == "Calibre-Web"
    assert created["has_password"] is False

    listing = await client.get("/api/opds/catalogs")
    assert listing.status_code == 200
    assert [c["id"] for c in listing.json()] == [created["id"]]


async def test_password_encrypted_and_hidden(client, db_session) -> None:
    from app.models import OpdsCatalog

    resp = await client.post(
        "/api/opds/catalogs",
        json={
            "name": "Secured",
            "url": "https://example.com/opds",
            "username": "alice",
            "password": "s3cret",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["has_password"] is True
    assert "password" not in body
    assert "password_encrypted" not in body

    row = await db_session.get(OpdsCatalog, body["id"])
    # Encrypted at rest (Fernet token, not plaintext) — spec AC-2.
    assert row.password_encrypted is not None
    assert row.password_encrypted != "s3cret"
    assert row.password_encrypted.startswith("gAAAA")


async def test_update_and_delete_catalog(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Old", "url": "https://a.example/opds"},
        )
    ).json()

    upd = await client.put(
        f"/api/opds/catalogs/{created['id']}",
        json={"name": "New", "url": "https://b.example/opds"},
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "New"
    assert upd.json()["url"].startswith("https://b.example")

    deleted = await client.delete(f"/api/opds/catalogs/{created['id']}")
    assert deleted.status_code == 204

    missing_upd = await client.put(
        f"/api/opds/catalogs/{created['id']}", json={"name": "Ghost"}
    )
    assert missing_upd.status_code == 404
    missing_del = await client.delete(f"/api/opds/catalogs/{created['id']}")
    assert missing_del.status_code == 404


async def test_reject_non_http_scheme(client) -> None:
    resp = await client.post(
        "/api/opds/catalogs",
        json={"name": "Evil", "url": "file:///etc/passwd"},
    )
    assert resp.status_code == 400
    listing = await client.get("/api/opds/catalogs")
    assert listing.json() == []


# --------------------------------------------------------------------- #
# Browse (feed proxy)
# --------------------------------------------------------------------- #


async def test_browse_normalizes_navigation_feed(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()
    _orig = opds_module.fetch_url
    opds_module.fetch_url = _fake_fetch(NAVIGATION_FEED.encode())
    try:
        resp = await client.get(f"/api/opds/catalogs/{created['id']}/browse")
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 200
    feed = resp.json()
    assert feed["title"] == "Test Catalog"
    assert feed["url"] == "https://cat.example/opds"
    entry = feed["entries"][0]
    assert entry["title"] == "Science Fiction"
    assert entry["is_navigation"] is True
    assert entry["download"] is None


async def test_browse_classifies_acquisition_entries(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()
    _orig = opds_module.fetch_url
    opds_module.fetch_url = _fake_fetch(ACQUISITION_FEED.encode())
    try:
        resp = await client.get(f"/api/opds/catalogs/{created['id']}/browse")
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 200
    entry = resp.json()["entries"][0]
    assert entry["is_navigation"] is False
    assert entry["authors"] == ["Jane Doe"]
    assert entry["thumbnail_url"] == "/covers/1.png"
    assert entry["download"]["url"] == "/files/1.epub"
    assert entry["download"]["media_type"] == "application/epub+zip"


async def test_browse_sends_basic_auth(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={
                "name": "Auth",
                "url": "https://cat.example/opds",
                "username": "bob",
                "password": "pw123",
            },
        )
    ).json()
    _orig = opds_module.fetch_url
    fetcher = _fake_fetch(NAVIGATION_FEED.encode())
    opds_module.fetch_url = fetcher
    try:
        resp = await client.get(f"/api/opds/catalogs/{created['id']}/browse")
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 200
    expected = base64.b64encode(b"bob:pw123").decode()
    assert fetcher.auth_seen == [expected]  # type: ignore[attr-defined]


async def test_browse_malformed_feed_502(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()
    _orig = opds_module.fetch_url
    opds_module.fetch_url = _fake_fetch(b"<not-a-feed>")
    try:
        resp = await client.get(f"/api/opds/catalogs/{created['id']}/browse")
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 502
    assert resp.json()["error"] == "Catalog Unavailable"


async def test_browse_fetch_failure_502(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()
    _orig = opds_module.fetch_url
    opds_module.fetch_url = _fake_fetch(b"", status=500)
    try:
        resp = await client.get(f"/api/opds/catalogs/{created['id']}/browse")
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 502


async def test_browse_oversized_feed_502(client, monkeypatch) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()

    async def _huge(url: str, **kwargs: object) -> bytes:
        raise opds_module.OpdsCatalogError(
            "Catalog response exceeds size limit", {"url": url}
        )

    _orig = opds_module.fetch_url
    opds_module.fetch_url = _huge
    try:
        resp = await client.get(f"/api/opds/catalogs/{created['id']}/browse")
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 502


async def test_browse_unknown_catalog_404(client) -> None:
    resp = await client.get("/api/opds/catalogs/9999/browse")
    assert resp.status_code == 404


async def test_browse_cross_host_url_allowed(client) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()
    _orig = opds_module.fetch_url
    fetcher = _fake_fetch(NAVIGATION_FEED.encode())
    opds_module.fetch_url = fetcher
    try:
        resp = await client.get(
            f"/api/opds/catalogs/{created['id']}/browse",
            params={"url": "https://other-host.example/feed"},
        )
    finally:
        opds_module.fetch_url = _orig
    assert resp.status_code == 200
    assert fetcher.urls_seen == ["https://other-host.example/feed"]  # type: ignore[attr-defined]

    # Scheme whitelist still applies to the target URL (AC-11).
    resp2 = await client.get(
        f"/api/opds/catalogs/{created['id']}/browse",
        params={"url": "ftp://other-host.example/feed"},
    )
    assert resp2.status_code == 400


# --------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------- #


async def test_download_imports_book(client, monkeypatch, temp_library) -> None:
    from app.config import get_config

    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()

    # Build a genuinely parseable minimal EPUB (same trick as test_calibre).
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        zf.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package version="3.0" '
            'xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid">'
            "<metadata "
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>OPDS Book</dc:title>"
            '<dc:identifier id="bookid">urn:uuid:opds-test-1</dc:identifier>'
            "<dc:language>en</dc:language></metadata>"
            '<manifest><item id="c1" href="c1.xhtml" '
            'media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c1"/></spine></package>',
        )
        zf.writestr(
            "OEBPS/c1.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
            "<body><p>hello</p></body></html>",
        )
    minimal_epub = buf.getvalue()

    async def _file(url: str, **kwargs: object) -> bytes:
        return minimal_epub

    monkeypatch.setattr(opds_module, "fetch_url", _file)
    monkeypatch.setattr(get_config(), "library_path", str(temp_library))

    resp = await client.post(
        f"/api/opds/catalogs/{created['id']}/download",
        json={"url": "https://cat.example/files/1.epub", "filename": "opds-book.epub"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["book_id"], int)
    assert body["title"] == "OPDS Book"
    assert (temp_library / "opds-book.epub").exists()


async def test_download_rejects_unsupported_extension(client, monkeypatch) -> None:
    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()

    async def _never(url: str, **kwargs: object) -> bytes:  # pragma: no cover
        raise AssertionError("fetch must not be called for unsupported formats")

    monkeypatch.setattr(opds_module, "fetch_url", _never)
    resp = await client.post(
        f"/api/opds/catalogs/{created['id']}/download",
        json={"url": "https://cat.example/files/1.exe", "filename": "evil.exe"},
    )
    assert resp.status_code == 400


async def test_download_failure_leaves_no_file(client, monkeypatch, temp_library) -> None:
    from app.config import get_config

    created = (
        await client.post(
            "/api/opds/catalogs",
            json={"name": "Cat", "url": "https://cat.example/opds"},
        )
    ).json()

    async def _boom(url: str, **kwargs: object) -> bytes:
        raise opds_module.OpdsCatalogError("Failed to reach catalog", {"url": url})

    monkeypatch.setattr(opds_module, "fetch_url", _boom)
    monkeypatch.setattr(get_config(), "library_path", str(temp_library))

    resp = await client.post(
        f"/api/opds/catalogs/{created['id']}/download",
        json={"url": "https://cat.example/files/1.epub", "filename": "x.epub"},
    )
    assert resp.status_code == 502
    assert list(temp_library.iterdir()) == []  # no partial file left behind


# --------------------------------------------------------------------- #
# Service-level unit checks (scheme validation + entry parsing edge cases)
# --------------------------------------------------------------------- #


async def test_service_rejects_bad_scheme_unit(db_session) -> None:
    from app.exceptions import ValidationError

    with pytest.raises(ValidationError):
        opds_module._validate_url_scheme("javascript:alert(1)")


async def test_create_catalog_unit_encryption_roundtrip(db_session) -> None:
    service = OpdsService(db_session)
    created = await service.create_catalog(
        OpdsCatalogCreate(
            name="Unit", url="https://unit.example/opds", password="topsecret"
        )
    )
    assert created.has_password is True
    listed = await service.list_catalogs()
    assert [c.id for c in listed] == [created.id]
