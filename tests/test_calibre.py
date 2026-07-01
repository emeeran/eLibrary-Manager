"""Tests for the Calibre library importer and integration routes.

Builds a real (minimal) Calibre library on disk — ``metadata.db`` with the
genuine Calibre schema plus the actual ``<author>/<title> (id)/`` folder
structure containing a real EPUB and ``cover.jpg`` — then exercises:

* :class:`CalibreImporter` catalog reading, file/cover resolution, and the
  full :meth:`import_library` pipeline against an in-memory app DB.
* The ``/api/library/calibre-status`` pre-flight route.
* The ``/api/books/{id}/calibre-web-url`` deep-link route.
* The ``calibre_web_url`` settings round-trip.
"""

from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------- #
# Calibre fixture builder
# --------------------------------------------------------------------- #


def _make_epub(path: Path, title: str = "x") -> bytes:
    """Write a minimal valid EPUB to ``path`` and return its bytes."""
    epub = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
    try:
        epub.writestr("mimetype", "application/epub+zip")
        epub.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?>'
            '<container version="1.0">'
            '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )
        epub.writestr(
            "content.opf",
            f'<?xml version="1.0"?><package version="3.0"><metadata>'
            f"<dc:title xmlns:dc='http://purl.org/dc/elements/1.1/'>{title}</dc:title>"
            "</metadata></package>",
        )
    finally:
        epub.close()
    return path.stat().st_size


def _build_calibre_library(root: Path) -> dict:
    """Create a realistic Calibre library under ``root``.

    Returns a dict describing the volumes created (used for assertions).
    """
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_CALIBRE_SCHEMA)
        # Volume 1: "Dune" by Frank Herbert — EPUB + cover, rated 5 stars.
        _add_book(
            conn,
            book_id=1,
            title="Dune",
            author="Frank Herbert",
            publisher="Chilton Books",
            pubdate="1965-08-01 00:00:00+00:00",
            tags="Science Fiction, Fiction",
            rating=10,
            language="eng",
            comment="A desert epic.",
            isbn="9780441172719",
            uuid="11111111-1111-1111-1111-111111111111",
            rel_folder="Frank Herbert/Dune (1)",
            formats=[("EPUB", "Dune")],
            last_modified="2020-01-01 00:00:00+00:00",
        )
        # Volume 2: "The Pragmatic Programmer" — PDF, no cover, unrated.
        _add_book(
            conn,
            book_id=2,
            title="The Pragmatic Programmer",
            author="Andrew Hunt",
            publisher="Addison-Wesley",
            pubdate="1999-10-30 00:00:00+00:00",
            tags="Programming, Technology",
            rating=0,
            language="eng",
            comment=None,
            isbn=None,
            uuid="22222222-2222-2222-2222-222222222222",
            rel_folder="Andrew Hunt/The Pragmatic Programmer (2)",
            formats=[("PDF", "The Pragmatic Programmer")],
            last_modified="2020-02-02 00:00:00+00:00",
        )
        # Volume 3: a book with only a TXT format → should be skipped
        # (no readable EPUB/PDF/MOBI on disk).
        _add_book(
            conn,
            book_id=3,
            title="Notes Only",
            author="Unknown",
            publisher=None,
            pubdate=None,
            tags="",
            rating=0,
            language=None,
            comment=None,
            isbn=None,
            uuid="33333333-3333-3333-3333-333333333333",
            rel_folder="Unknown/Notes Only (3)",
            formats=[("TXT", "Notes Only")],  # not a supported format
        )
        conn.commit()
    finally:
        conn.close()

    # Write the real ebook files + cover into the per-book folders.
    dune_dir = root / "Frank Herbert" / "Dune (1)"
    dune_dir.mkdir(parents=True, exist_ok=True)
    _make_epub(dune_dir / "Dune.epub", "Dune")
    (dune_dir / "cover.jpg").write_bytes(_JPEG_BYTES)

    pp_dir = root / "Andrew Hunt" / "The Pragmatic Programmer (2)"
    pp_dir.mkdir(parents=True, exist_ok=True)
    (pp_dir / "The Pragmatic Programmer.pdf").write_bytes(_FAKE_PDF_BYTES)

    notes_dir = root / "Unknown" / "Notes Only (3)"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / "Notes Only.txt").write_bytes(b"just text, not an ebook")

    return {
        "root": root,
        "dune_path": str(dune_dir / "Dune.epub"),
        "pp_path": str(pp_dir / "The Pragmatic Programmer.pdf"),
    }


def _add_book(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    title: str,
    author: str,
    publisher: str | None,
    pubdate: str | None,
    tags: str,
    rating: int,
    language: str | None,
    comment: str | None,
    isbn: str | None,
    uuid: str,
    rel_folder: str,
    formats: list[tuple[str, str]],
    last_modified: str | None = None,
    series: str | None = None,
    series_index: float | None = None,
) -> None:
    """Insert one fully-linked Calibre book."""
    conn.execute(
        "INSERT INTO books (id, title, sort, isbn, pubdate, path, uuid, has_cover, last_modified) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (book_id, title, title, isbn, pubdate, rel_folder, uuid, 1 if comment else 0, last_modified),
    )
    conn.execute("INSERT INTO authors (id, name, sort) VALUES (?, ?, ?)", (book_id, author, author))
    conn.execute(
        "INSERT INTO books_authors_link (id, book, author) VALUES (?, ?, ?)",
        (book_id, book_id, book_id),
    )
    if publisher:
        conn.execute("INSERT INTO publishers (id, name, sort) VALUES (?, ?, ?)", (book_id, publisher, publisher))
        conn.execute(
            "INSERT INTO books_publishers_link (id, book, publisher) VALUES (?, ?, ?)",
            (book_id, book_id, book_id),
        )
    if comment:
        conn.execute("INSERT INTO comments (id, book, text) VALUES (?, ?, ?)", (book_id, book_id, comment))
    if tags:
        for i, tag in enumerate(tags.split(",")):
            tag = tag.strip()
            tag_id = book_id * 100 + i
            conn.execute("INSERT INTO tags (id, name, link) VALUES (?, ?, '')", (tag_id, tag))
            conn.execute(
                "INSERT INTO books_tags_link (id, book, tag) VALUES (?, ?, ?)",
                (tag_id, book_id, tag_id),
            )
    if rating:
        conn.execute("INSERT INTO ratings (id, rating) VALUES (?, ?)", (book_id, rating))
        conn.execute(
            "INSERT INTO books_ratings_link (id, book, rating) VALUES (?, ?, ?)",
            (book_id, book_id, book_id),
        )
    if language:
        conn.execute("INSERT INTO languages (id, lang_code) VALUES (?, ?)", (book_id, language))
        conn.execute(
            "INSERT INTO books_languages_link (id, book, lang_code, item_order) VALUES (?, ?, ?, ?)",
            (book_id, book_id, book_id, 0),
        )
    for fmt, name in formats:
        conn.execute(
            "INSERT INTO data (id, book, format, uncompressed_size, name) VALUES (?, ?, ?, ?, ?)",
            (book_id * 10, book_id, fmt, 1024, name),
        )
    if series:
        conn.execute(
            "INSERT INTO series (id, name, sort) VALUES (?, ?, ?)",
            (book_id, series, series_index),
        )
        conn.execute(
            "INSERT INTO books_series_link (id, book, series, sort) VALUES (?, ?, ?, ?)",
            (book_id, book_id, book_id, series_index),
        )


# Minimal valid JPEG (1×1 px) for cover tests.
_JPEG_BYTES = bytes(
    [
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD2, 0x8A, 0x28, 0xA0, 0xFF, 0xD9,
    ]
)

# Minimal fake PDF (just a valid header) — the importer only stat()s it.
_FAKE_PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

# The Calibre metadata.db schema (subset the importer queries).
_CALIBRE_SCHEMA = """
CREATE TABLE books (
    id INTEGER PRIMARY KEY,
    title TEXT,
    sort TEXT,
    isbn TEXT,
    pubdate TIMESTAMP,
    path TEXT,
    uuid TEXT,
    has_cover BOOL,
    last_modified TEXT
);
CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
CREATE TABLE books_publishers_link (id INTEGER PRIMARY KEY, book INTEGER, publisher INTEGER);
CREATE TABLE comments (id INTEGER PRIMARY KEY, book INTEGER, text TEXT);
CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT, link TEXT);
CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INTEGER, tag INTEGER);
CREATE TABLE ratings (id INTEGER PRIMARY KEY, rating INTEGER);
CREATE TABLE books_ratings_link (id INTEGER PRIMARY KEY, book INTEGER, rating INTEGER);
CREATE TABLE languages (id INTEGER PRIMARY KEY, lang_code TEXT);
CREATE TABLE books_languages_link (id INTEGER PRIMARY KEY, book INTEGER, lang_code INTEGER, item_order INTEGER);
CREATE TABLE identifiers (id INTEGER PRIMARY KEY, book INTEGER, type TEXT, val TEXT);
CREATE TABLE data (id INTEGER PRIMARY KEY, book INTEGER, format TEXT, uncompressed_size INTEGER, name TEXT);
CREATE TABLE series (id INTEGER PRIMARY KEY, name TEXT, sort TEXT);
CREATE TABLE books_series_link (id INTEGER PRIMARY KEY, book INTEGER, series INTEGER, sort REAL);
"""


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #


@pytest.fixture
def calibre_library(tmp_path: Path) -> dict:
    """Build a real on-disk Calibre library and return its descriptor."""
    return _build_calibre_library(tmp_path / "MyCalibreLib")


# --------------------------------------------------------------------- #
# Importer unit tests
# --------------------------------------------------------------------- #


async def test_importer_validates_library_root(calibre_library: dict) -> None:
    """validate() rejects paths lacking metadata.db."""
    from app.services.calibre_importer import CalibreImporter

    importer = CalibreImporter(calibre_library["root"])
    importer.validate()  # should not raise

    bad = CalibreImporter(str(Path(calibre_library["root"]).parent))
    with pytest.raises(FileNotFoundError):
        bad.validate()


async def test_importer_reads_catalog(calibre_library: dict) -> None:
    """The catalog query returns all three volumes with mapped fields."""
    from app.services.calibre_importer import CalibreImporter

    importer = CalibreImporter(calibre_library["root"])
    volumes = importer._read_catalog()  # noqa: SLF001
    by_id = {v.calibre_id: v for v in volumes}

    assert len(volumes) == 3

    dune = by_id[1]
    assert dune.title == "Dune"
    assert dune.author == "Frank Herbert"
    assert dune.publisher == "Chilton Books"
    assert dune.pubdate == "1965-08-01"
    assert dune.isbn == "9780441172719"
    assert dune.calibre_uuid == "11111111-1111-1111-1111-111111111111"
    # Calibre rating 10 → app 5-star scale.
    assert dune.rating == 5
    assert "Science Fiction" in dune.subjects
    assert dune.language == "eng"
    assert dune.description == "A desert epic."

    # Unrated book → rating 0.
    assert by_id[2].rating == 0


async def test_importer_resolves_best_format(calibre_library: dict) -> None:
    """EPUB is preferred over PDF when both resolution runs."""
    from app.services.calibre_importer import FORMAT_PREFERENCE, CalibreImporter

    assert FORMAT_PREFERENCE == ("EPUB", "PDF", "MOBI")

    importer = CalibreImporter(calibre_library["root"])
    volumes = importer._read_catalog()  # noqa: SLF001
    dune = next(v for v in volumes if v.calibre_id == 1)
    importer._resolve_file(dune)  # noqa: SLF001
    assert dune.fmt == "EPUB"
    assert dune.file_path == calibre_library["dune_path"]
    assert dune.file_size > 0

    pp = next(v for v in volumes if v.calibre_id == 2)
    importer._resolve_file(pp)  # noqa: SLF001
    assert pp.fmt == "PDF"

    # The TXT-only volume resolves no readable file.
    notes = next(v for v in volumes if v.calibre_id == 3)
    importer._resolve_file(notes)  # noqa: SLF001
    assert notes.file_path is None


async def test_import_library_full_pipeline(calibre_library: dict, tmp_path: Path) -> None:
    """import_library commits readable volumes, skips the TXT-only one."""
    # Point covers at a temp dir so the cover copy lands somewhere clean.
    import app.config as config_module
    from app.schemas import BookCreate
    from app.services.calibre_importer import CalibreImporter
    orig_covers = config_module.get_config().covers_path
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    config_module.get_config().covers_path = str(covers_dir)
    try:
        importer = CalibreImporter(calibre_library["root"])
        committed: list[BookCreate] = []

        async def commit_one(volume, book_data):  # noqa: ANN001
            committed.append(book_data)

        summary = await importer.import_library(commit_one=commit_one)
    finally:
        config_module.get_config().covers_path = orig_covers

    assert summary.total_in_library == 3
    assert summary.imported == 2  # Dune + Pragmatic Programmer
    assert summary.no_readable_format == 1  # Notes Only
    assert summary.skipped_existing == 0
    assert summary.errors == 0
    # Dune had a cover.jpg → it should have been imported.
    assert summary.covers_imported == 1

    titles = {b.title for b in committed}
    assert titles == {"Dune", "The Pragmatic Programmer"}

    dune = next(b for b in committed if b.title == "Dune")
    assert dune.calibre_id == 1
    assert dune.calibre_uuid == "11111111-1111-1111-1111-111111111111"
    assert dune.format == "EPUB"
    assert dune.isbn == "9780441172719"
    assert dune.publisher == "Chilton Books"
    assert dune.rating == 5  # Calibre 10 → app 5-star scale
    assert "Science Fiction" in dune.subjects
    assert dune.cover_path is not None


async def test_import_library_skips_existing(calibre_library: dict, tmp_path: Path) -> None:
    """exists_check short-circuits already-imported volumes."""
    from app.services.calibre_importer import CalibreImporter

    importer = CalibreImporter(calibre_library["root"])
    imported_paths: set[str] = set()

    def exists(volume) -> bool:  # noqa: ANN001
        return volume.calibre_id == 1  # pretend Dune is already imported

    async def commit_one(volume, book_data):  # noqa: ANN001
        imported_paths.add(book_data.path)

    summary = await importer.import_library(exists_check=exists, commit_one=commit_one)
    assert summary.imported == 1  # only Pragmatic Programmer
    assert summary.skipped_existing == 1
    assert len(imported_paths) == 1


# --------------------------------------------------------------------- #
# Route integration tests
# --------------------------------------------------------------------- #


async def test_calibre_status_route(client, calibre_library: dict) -> None:
    """GET /api/library/calibre-status validates a real library."""
    resp = await client.get(
        "/api/library/calibre-status", params={"path": str(calibre_library["root"])}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["volume_count"] == 3
    assert body["path"] == str(calibre_library["root"])


async def test_calibre_status_rejects_bad_path(client, tmp_path: Path) -> None:
    """A non-Calibre directory is reported invalid."""
    resp = await client.get(
        "/api/library/calibre-status", params={"path": str(tmp_path)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert "metadata.db" in body["error"]


async def test_calibre_web_url_route(client, db_session, calibre_library: dict) -> None:
    """The Calibre-Web deep-link route builds the expected URL."""
    # Import Dune into the test DB directly via the importer + repo.
    from app.repositories import BookRepository
    from app.services.calibre_importer import CalibreImporter

    repo = BookRepository(db_session)
    importer = CalibreImporter(calibre_library["root"])
    volumes = importer._read_catalog()  # noqa: SLF001
    importer._resolve_file(volumes[0])  # noqa: SLF001
    from app.schemas import BookCreate

    book_data = BookCreate(
        title=volumes[0].title,
        author=volumes[0].author,
        path=volumes[0].file_path,
        format="EPUB",
        file_size=volumes[0].file_size,
        calibre_id=volumes[0].calibre_id,
        calibre_uuid=volumes[0].calibre_uuid,
    )
    book = await repo.create(book_data)
    await db_session.commit()

    # No calibre_web_url configured → url is null.
    resp = await client.get(f"/api/books/{book.id}/calibre-web-url")
    assert resp.status_code == 200
    assert resp.json()["url"] is None

    # Configure Calibre-Web base URL.
    resp = await client.post(
        "/api/settings", json={"calibre_web_url": "http://cw.example.com:8083/"}
    )
    assert resp.status_code == 200
    assert resp.json()["calibre_web_url"].rstrip("/") == "http://cw.example.com:8083"

    resp = await client.get(f"/api/books/{book.id}/calibre-web-url")
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == "http://cw.example.com:8083/book/1"
    assert body["calibre_id"] == 1


async def test_calibre_web_url_for_non_calibre_book(client, db_session) -> None:
    """A non-Calibre book has no deep link even when Calibre-Web is set."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    book = await repo.create(
        BookCreate(title="Plain", author="A", path="/tmp/plain.epub", file_size=10)
    )
    await db_session.commit()

    await client.post("/api/settings", json={"calibre_web_url": "http://cw.example.com"})
    resp = await client.get(f"/api/books/{book.id}/calibre-web-url")
    assert resp.status_code == 200
    assert resp.json()["url"] is None
    assert resp.json()["reason"] == "book is not from a Calibre library"


# --------------------------------------------------------------------- #
# Launch endpoint — reverse deep link (spec 013)
# --------------------------------------------------------------------- #


async def _insert_calibre_book(
    db_session, *, calibre_id: int, calibre_uuid: str | None = None,
    is_hidden: bool = False, title: str = "X", author: str = "A",
):
    """Insert a Calibre-linked book into the test DB and return it."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    book = await repo.create(
        BookCreate(
            title=title,
            author=author,
            path=f"/tmp/calibre_{calibre_id}.epub",
            file_size=10,
            format="EPUB",
            calibre_id=calibre_id,
            calibre_uuid=calibre_uuid,
        )
    )
    if is_hidden:
        book.is_hidden = True
    await db_session.commit()
    return book


async def test_launch_resolves_to_reader(client, db_session) -> None:
    """calibre_id → 302 /reader/{elm_id}."""
    book = await _insert_calibre_book(db_session, calibre_id=42, calibre_uuid="u-42", title="Dune")
    resp = await client.get("/calibre/launch", params={"calibre_id": 42})
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/reader/{book.id}"


async def test_launch_by_uuid(client, db_session) -> None:
    """calibre_uuid is accepted as an alternate key."""
    book = await _insert_calibre_book(db_session, calibre_id=7, calibre_uuid="abc-123", title="X")
    resp = await client.get("/calibre/launch", params={"calibre_uuid": "abc-123"})
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/reader/{book.id}"


async def test_launch_no_params_redirects_to_library(client) -> None:
    """No id/uuid → /library (never an error on a user click)."""
    resp = await client.get("/calibre/launch")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/library"


async def test_launch_unknown_id_redirects_to_pending(client) -> None:
    """An unimported Calibre id → pending notice, not a dead-end 404."""
    resp = await client.get("/calibre/launch", params={"calibre_id": 9999})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/library?calibre_pending=9999"


async def test_launch_hidden_book_redirects_to_library(client, db_session) -> None:
    """A hidden book must not be opened via deep link."""
    await _insert_calibre_book(db_session, calibre_id=5, is_hidden=True, title="Secret")
    resp = await client.get("/calibre/launch", params={"calibre_id": 5})
    assert resp.status_code == 302
    assert resp.headers["location"] == "/library?calibre_hidden=1"


async def test_launch_by_title(client, db_session) -> None:
    """A bulk-loaded book (no calibre_id) is found by title for the userscript."""
    await _insert_calibre_book(db_session, calibre_id=91, title="A Unique Title", author="Author A")
    # No calibre_id — resolve by title.
    resp = await client.get("/calibre/launch", params={"title": "A Unique Title"})
    assert resp.status_code == 302
    assert "/reader/" in resp.headers["location"]


async def test_launch_by_title_with_author_disambiguates(client, db_session) -> None:
    """title + author picks the right book among same-titled entries."""
    wanted = await _insert_calibre_book(db_session, calibre_id=101, title="Same", author="Wanted")
    other = await _insert_calibre_book(db_session, calibre_id=102, title="Same", author="Other")
    resp = await client.get("/calibre/launch", params={"title": "Same", "author": "Wanted"})
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/reader/{wanted.id}"
    assert wanted.id != other.id


# --------------------------------------------------------------------- #
# Incremental re-sync + series (spec 011 v1.1)
# --------------------------------------------------------------------- #


async def test_importer_reads_series_and_last_modified(tmp_path: Path) -> None:
    """Series + last_modified are read from the Calibre catalog."""
    from app.services.calibre_importer import CalibreImporter

    root = tmp_path / "SeriesLib"
    root.mkdir()
    conn = sqlite3.connect(root / "metadata.db")
    try:
        conn.executescript(_CALIBRE_SCHEMA)
        _add_book(
            conn,
            book_id=1,
            title="Foundation",
            author="Isaac Asimov",
            publisher=None,
            pubdate="1951-06-01 00:00:00+00:00",
            tags="",
            rating=0,
            language=None,
            comment=None,
            isbn=None,
            uuid="s-1",
            rel_folder="Isaac Asimov/Foundation (1)",
            formats=[("EPUB", "Foundation")],
            last_modified="2020-05-05 00:00:00+00:00",
            series="Foundation",
            series_index=1.0,
        )
        conn.commit()
    finally:
        conn.close()

    book_dir = root / "Isaac Asimov" / "Foundation (1)"
    book_dir.mkdir(parents=True)
    _make_epub(book_dir / "Foundation.epub", "Foundation")

    vol = CalibreImporter(root)._read_catalog()[0]  # noqa: SLF001
    assert vol.series == "Foundation"
    assert vol.series_index == 1.0
    assert vol.last_modified == "2020-05-05 00:00:00+00:00"


async def test_import_library_incremental_update(
    calibre_library: dict, tmp_path: Path
) -> None:
    """lookup_check/update_one refresh changed volumes instead of re-inserting."""
    import app.config as config_module
    from app.services.calibre_importer import CalibreImporter

    orig_covers = config_module.get_config().covers_path
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    config_module.get_config().covers_path = str(covers_dir)
    try:
        importer = CalibreImporter(calibre_library["root"])

        # First pass: insert both readable volumes; remember their last_modified.
        state: dict[int, str | None] = {}

        async def commit_one(volume, book_data):  # noqa: ANN001
            state[volume.calibre_id] = volume.last_modified

        first = await importer.import_library(commit_one=commit_one)
        assert first.imported == 2  # Dune + Pragmatic Programmer
        assert first.updated == 0

        # Simulate a Calibre metadata edit on Dune (calibre_id=1).
        conn = sqlite3.connect(calibre_library["root"] / "metadata.db")
        try:
            conn.execute(
                "UPDATE books SET last_modified = ? WHERE id = 1",
                ("2099-01-01 00:00:00+00:00",),
            )
            conn.commit()
        finally:
            conn.close()

        def lookup_check(volume):  # noqa: ANN001
            if volume.calibre_id not in state:
                return "new"
            stored = state[volume.calibre_id]
            if stored is None or (
                volume.last_modified is not None and volume.last_modified != stored
            ):
                return "changed"
            return "unchanged"

        updated: list[tuple[int, str]] = []

        async def update_one(volume, book_data):  # noqa: ANN001
            updated.append((volume.calibre_id, book_data.title))
            state[volume.calibre_id] = volume.last_modified

        second = await importer.import_library(
            lookup_check=lookup_check, commit_one=commit_one, update_one=update_one
        )
        assert second.imported == 0
        assert second.updated == 1  # only Dune changed
        assert second.skipped_existing == 1  # Pragmatic Programmer unchanged
        assert updated and updated[0][0] == 1
        assert updated[0][1] == "Dune"
    finally:
        config_module.get_config().covers_path = orig_covers


# --------------------------------------------------------------------- #
# Sync service: prune + restore (spec 011 v1.2)
# --------------------------------------------------------------------- #


async def test_sync_library_prunes_missing(
    calibre_library: dict, db_session, tmp_path: Path
) -> None:
    """A volume removed from Calibre is soft-deleted on the next sync."""
    import app.config as config_module
    from app.repositories import BookRepository
    from app.services.calibre_sync_service import sync_library

    orig = config_module.get_config().covers_path
    covers = tmp_path / "covers"
    covers.mkdir()
    config_module.get_config().covers_path = str(covers)
    try:
        await sync_library(db_session, calibre_library["root"], prune_missing=True)
        await db_session.commit()

        repo = BookRepository(db_session)
        _, total = await repo.list_with_count()
        assert total == 2  # Dune (1) + Pragmatic Programmer (2)

        # Remove Dune from the Calibre catalog.
        conn = sqlite3.connect(calibre_library["root"] / "metadata.db")
        conn.execute("DELETE FROM books WHERE id = 1")
        conn.commit()
        conn.close()

        await sync_library(db_session, calibre_library["root"], prune_missing=True)
        await db_session.commit()

        # Fresh repo (per-instance count cache would otherwise serve the
        # pre-prune count; production uses a new repo per request).
        _, total = await BookRepository(db_session).list_with_count()
        assert total == 1  # Dune soft-deleted → excluded from the normal view
    finally:
        config_module.get_config().covers_path = orig


async def test_restore_book_route(client, db_session) -> None:
    """POST /api/books/{id}/restore clears the soft-delete flag."""
    from app.repositories import BookRepository
    from app.schemas import BookCreate

    repo = BookRepository(db_session)
    book = await repo.create(BookCreate(title="X", author="A", path="/tmp/x.epub", file_size=10))
    book.is_deleted = True
    await db_session.commit()

    resp = await client.post(f"/api/books/{book.id}/restore")
    assert resp.status_code == 200
    assert resp.json()["restored"] is True

    refreshed = await repo.get_by_id(book.id)
    assert refreshed.is_deleted is False
