"""Calibre library importer.

Reads a Calibre library's ``metadata.db`` (the SQLite catalog Calibre
maintains in every library folder) and resolves each volume's real ebook
file on disk, producing :class:`BookCreate` records ready for the index.

Calibre's schema (a stable, well-documented layout) is queried read-only:

  books(id, title, sort, author_sort, isbn, pubdate, path, uuid, has_cover)
  authors(id, name, sort)             ← joined via books_authors_link
  publishers(id, name)                ← joined via books_publishers_link
  comments(book, text)
  tags(id, name)                      ← joined via books_tags_link
  ratings(id, rating)                 ← 0..10 (half-stars); converted to 1..5
  languages(id, lang_code)            ← joined via books_languages_link
  identifiers(book, type, val)        ← ISBN/mobi/google/asin etc.
  data(book, format, name)            ← one row per available format

Each Calibre ``books.path`` is relative to the library root and names the
folder holding the formats + ``cover.jpg``; the actual file is
``<library>/<books.path>/<data.name>.<format.lower()>``.

The importer:

* picks the best available format (EPUB > PDF > MOBI, matching the formats
  this app can read),
* copies Calibre's ``cover.jpg`` into ``static_covers`` via the shared
  optimizer (so covers match the rest of the library),
* maps Calibre's rating (0..10) to the app's 1..5 star scale,
* preserves the Calibre book id + uuid on the record for deep-linking, and
* passes Calibre tags through as ``subjects`` for auto-categorization.

The DB read runs in a threadpool (``sqlite3`` is blocking) and file I/O is
batched + yielded so the server stays responsive during large imports.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_config
from app.logging_config import get_logger
from app.parsers.image_service import optimize_cover_bytes
from app.schemas import BookCreate
from app.utils import hash_path

logger = get_logger(__name__)

#: Format preference — first available wins. Matches the readers we support.
FORMAT_PREFERENCE: tuple[str, ...] = ("EPUB", "PDF", "MOBI")

#: Calibre stores ratings as 0..10 (half-star granularity); 2 = 1 star.
_CALIBRE_RATING_DIVISOR = 2

#: Maximum number of subjects/tags passed through to categorization.
_MAX_SUBJECTS = 20


@dataclass
class CalibreVolume:
    """One resolved Calibre volume ready to import."""

    calibre_id: int
    calibre_uuid: str | None
    title: str
    author: str
    publisher: str | None
    pubdate: str | None
    description: str | None
    language: str | None
    isbn: str | None
    rating: int  # 0..5
    subjects: list[str] = field(default_factory=list)
    file_path: str | None = None
    fmt: str | None = None
    file_size: int = 0
    cover_source: str | None = None  # absolute path to Calibre cover.jpg
    book_rel_path: str = ""  # Calibre "books.path" (folder), for cover lookup
    # Incremental-sync + series (spec 011 v1.1). ``last_modified`` is Calibre's
    # raw timestamp string; the route compares it to the stored value to decide
    # new vs. changed vs. unchanged.
    last_modified: str | None = None
    series: str | None = None
    series_index: float | None = None


@dataclass
class CalibreImportSummary:
    """Aggregate result of an import run."""

    total_in_library: int = 0
    imported: int = 0
    updated: int = 0
    skipped_existing: int = 0
    no_readable_format: int = 0
    errors: int = 0
    covers_imported: int = 0

    def as_dict(self) -> dict:
        return {
            "total_in_library": self.total_in_library,
            "imported": self.imported,
            "updated": self.updated,
            "skipped_existing": self.skipped_existing,
            "no_readable_format": self.no_readable_format,
            "errors": self.errors,
            "covers_imported": self.covers_imported,
        }


class CalibreImporter:
    """Import a Calibre library catalog into the application's index."""

    def __init__(self, library_root: str) -> None:
        """Initialize for a Calibre library root.

        Args:
            library_root: Absolute path to the Calibre library (the folder
                containing ``metadata.db``).
        """
        self.library_root = Path(library_root).expanduser().resolve()
        self.metadata_db = self.library_root / "metadata.db"
        self.config = get_config()
        self.covers_path = Path(self.config.covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def validate(self) -> None:
        """Verify the library root looks like a Calibre library.

        Raises:
            FileNotFoundError: If the root or ``metadata.db`` is missing.
        """
        if not self.library_root.is_dir():
            raise FileNotFoundError(
                f"Calibre library directory not found: {self.library_root}"
            )
        if not self.metadata_db.is_file():
            raise FileNotFoundError(
                f"metadata.db not found in {self.library_root} — "
                "is this a Calibre library root?"
            )

    # ------------------------------------------------------------------ #
    # Catalog reading (runs read-only against Calibre's SQLite DB)
    # ------------------------------------------------------------------ #

    def _open_calibre_db(self) -> sqlite3.Connection:
        """Open Calibre's metadata.db read-only (URI mode prevents writes)."""
        uri = f"file:{self.metadata_db}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _read_catalog(self) -> list[CalibreVolume]:
        """Read the full Calibre catalog into memory.

        Calibre libraries are typically modest in size (tens of thousands of
        rows at most), so a single join is simpler and faster than per-book
        queries. Aggregations use ``GROUP_CONCAT`` to collapse the many-to-many
        author/tag/language tables into one row per book.
        """
        conn = self._open_calibre_db()
        try:
            rows = conn.execute(_CALIBRE_CATALOG_SQL).fetchall()
        finally:
            conn.close()

        volumes: list[CalibreVolume] = []
        for r in rows:
            rating = (r["rating"] or 0) // _CALIBRE_RATING_DIVISOR
            # Calibre ratings go 0,2,4,6,8,10 → 0,1,2,3,4,5. A rating of 0
            # means "unrated"; clamp to the app's 0..5 scale.
            rating = min(max(rating, 0), 5)

            isbn = r["isbn"] or r["identifier_isbn"]
            series_index = r["series_index"]
            volumes.append(
                CalibreVolume(
                    calibre_id=r["id"],
                    calibre_uuid=r["uuid"],
                    title=r["title"] or "Untitled",
                    author=r["authors"] or "Unknown",
                    publisher=r["publisher"],
                    pubdate=_normalize_pubdate(r["pubdate"]),
                    description=r["comment"],
                    language=r["languages"] or None,
                    isbn=isbn,
                    rating=rating,
                    subjects=_split_tags(r["tags"], r["title"]),
                    book_rel_path=r["path"] or "",
                    last_modified=_normalize_last_modified(r["last_modified"]),
                    series=r["series"],
                    series_index=float(series_index) if series_index is not None else None,
                )
            )
        return volumes

    # ------------------------------------------------------------------ #
    # File + cover resolution
    # ------------------------------------------------------------------ #

    def _resolve_file(self, volume: CalibreVolume) -> None:
        """Resolve the best readable format file for ``volume`` in place."""
        if not volume.book_rel_path:
            return
        folder = self.library_root / volume.book_rel_path
        if not folder.is_dir():
            return

        # Query the formats table for this book, then pick by preference.
        conn = self._open_calibre_db()
        try:
            fmt_rows = conn.execute(
                "SELECT format, name FROM data WHERE book = ? ORDER BY format",
                (volume.calibre_id,),
            ).fetchall()
        finally:
            conn.close()

        available: dict[str, tuple[str, str]] = {}
        for fr in fmt_rows:
            fmt = (fr["format"] or "").upper()
            name = fr["name"] or ""
            if fmt and name:
                available[fmt] = (name, fmt)

        for preferred in FORMAT_PREFERENCE:
            if preferred in available:
                name, fmt = available[preferred]
                candidate = folder / f"{name}.{fmt.lower()}"
                if candidate.is_file():
                    volume.file_path = str(candidate)
                    volume.fmt = fmt
                    try:
                        volume.file_size = candidate.stat().st_size
                    except OSError:
                        volume.file_size = 0
                break

        # Cover: Calibre stores cover.jpg next to the formats.
        cover = folder / "cover.jpg"
        if cover.is_file():
            volume.cover_source = str(cover)

    # ------------------------------------------------------------------ #
    # Cover handling
    # ------------------------------------------------------------------ #

    def _import_cover(self, volume: CalibreVolume) -> str | None:
        """Optimize Calibre's cover.jpg into ``static_covers``; return its path."""
        if not volume.cover_source or not Path(volume.cover_source).is_file():
            return None
        dest_hash = hash_path(volume.file_path or volume.cover_source)
        dest = self.covers_path / f"{dest_hash}.jpg"
        if dest.exists():
            # Already imported (e.g. a previous run or duplicate detection).
            return str(dest)
        try:
            with open(volume.cover_source, "rb") as fh:
                img_bytes = fh.read()
            if optimize_cover_bytes(img_bytes, dest):
                return str(dest)
        except Exception as e:  # noqa: BLE001 — cover failures are non-fatal
            logger.warning(f"Failed to import Calibre cover for {volume.title}: {e}")
        return None

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def import_library(
        self,
        progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
        cancel_check: Callable[[], None] | None = None,
        exists_check: Callable[[CalibreVolume], bool] | None = None,
        commit_one: Callable[[CalibreVolume, BookCreate], Awaitable[None]]
        | None = None,
        lookup_check: Callable[[CalibreVolume], str] | None = None,
        update_one: Callable[[CalibreVolume, BookCreate], Awaitable[None]]
        | None = None,
    ) -> CalibreImportSummary:
        """Import the Calibre library into the index.

        The actual DB persistence is delegated to callbacks so this class stays
        free of session/ORM concerns (and is unit-testable without a DB).

        Resolution per volume (after file resolution) is one of:

        * ``"new"``       — not present → ``commit_one`` (if given), counts as
          ``imported``.
        * ``"changed"``   — present but Calibre's ``last_modified`` differs →
          ``update_one`` (if given), counts as ``updated`` (incremental sync).
        * ``"unchanged"`` — present and unchanged → skipped, counts as
          ``skipped_existing``.

        The status comes from ``lookup_check`` when provided; otherwise the
        legacy ``exists_check`` bool is used (True ⇒ "unchanged", False ⇒ "new").
        This keeps older callers working while enabling incremental re-sync.

        Args:
            progress_callback: ``async (processed, total, current_title)``.
            cancel_check: raises to abort cooperatively.
            exists_check: legacy ``sync (volume) -> bool``; True means skip.
            commit_one: ``async (volume, book_create) -> None`` to insert.
            lookup_check: ``sync (volume) -> "new"|"changed"|"unchanged"``.
            update_one: ``async (volume, book_create) -> None`` to update.

        Returns:
            Aggregate :class:`CalibreImportSummary`.
        """
        self.validate()

        # Catalog read is blocking SQLite I/O → offload to a worker thread.
        volumes = await asyncio.to_thread(self._read_catalog)
        summary = CalibreImportSummary(total_in_library=len(volumes))
        logger.info(
            f"Calibre import: {summary.total_in_library} volumes in catalog at "
            f"{self.library_root}"
        )

        for i, volume in enumerate(volumes):
            if cancel_check:
                cancel_check()
            try:
                # Resolve the real ebook file (threadpool: blocking stat/sqlite).
                await asyncio.to_thread(self._resolve_file, volume)

                if not volume.file_path:
                    summary.no_readable_format += 1
                    logger.debug(
                        f"Skipping Calibre book {volume.calibre_id} "
                        f"({volume.title!r}): no EPUB/PDF/MOBI format on disk"
                    )
                    continue

                # Decide new / changed / unchanged (incremental sync, spec 011 v1.1).
                if lookup_check is not None:
                    status = lookup_check(volume)
                elif exists_check is not None and exists_check(volume):
                    status = "unchanged"
                else:
                    status = "new"

                if status == "unchanged":
                    summary.skipped_existing += 1
                else:
                    cover_dest = await asyncio.to_thread(self._import_cover, volume)
                    if cover_dest:
                        summary.covers_imported += 1

                    book_data = _volume_to_book_create(volume, cover_dest)
                    if status == "changed":
                        if update_one:
                            await update_one(volume, book_data)
                        summary.updated += 1
                    else:  # "new"
                        if commit_one:
                            await commit_one(volume, book_data)
                        summary.imported += 1
            except Exception as e:  # noqa: BLE001 — keep importing on per-book errors
                summary.errors += 1
                logger.error(
                    f"Failed to import Calibre book {volume.calibre_id}: {e}"
                )

            if progress_callback and (i % 10 == 0 or i == summary.total_in_library - 1):
                await progress_callback(i + 1, summary.total_in_library, volume.title)
            # Yield control periodically to keep the server responsive.
            if i % 25 == 0:
                await asyncio.sleep(0)

        logger.info(f"Calibre import complete: {summary.as_dict()}")
        return summary


# ====================================================================== #
# Helpers
# ====================================================================== #


def _normalize_pubdate(value: str | None) -> str | None:
    """Normalize a Calibre pubdate to a ``YYYY-MM-DD`` string if possible."""
    if not value:
        return None
    # Calibre stores timestamps as "2018-05-03 00:00:00+00:00".
    text = str(value).strip()
    return text.split(" ")[0] or None


def _normalize_last_modified(value: str | None) -> str | None:
    """Return Calibre's ``last_modified`` as a stable string for equality compare.

    Stored verbatim (not parsed) so re-sync detection is exact string equality
    across Calibre versions, regardless of timestamp format/precision.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _split_tags(tags: str | None, fallback_title: str | None) -> list[str]:
    """Split a Calibre ``GROUP_CONCAT`` tag string into a deduped list."""
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in str(tags).split(","):
        name = raw.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
        if len(out) >= _MAX_SUBJECTS:
            break
    return out


def _volume_to_book_create(
    volume: CalibreVolume, cover_path: str | None
) -> BookCreate:
    """Convert a resolved :class:`CalibreVolume` to a :class:`BookCreate`."""
    return BookCreate(
        title=volume.title[:500],
        author=(volume.author or "Unknown")[:300],
        path=volume.file_path or "",
        format=volume.fmt or "EPUB",
        file_size=volume.file_size,
        cover_path=cover_path,
        publisher=volume.publisher,
        publish_date=volume.pubdate,
        description=volume.description,
        language=volume.language,
        isbn=volume.isbn,
        # Calibre doesn't give us page counts; estimate from file size like the
        # fast-indexer does so progress math has a sane denominator.
        total_pages=max(1, volume.file_size // 2048),
        storage_type="local",
        subjects=volume.subjects,
        calibre_id=volume.calibre_id,
        calibre_uuid=volume.calibre_uuid,
        series=volume.series,
        series_index=volume.series_index,
    )


# One-shot catalog query. LEFT JOINs everywhere so a book missing publishers /
# comments / tags still imports. Aggregations collapse the many-to-many tables.
_CALIBRE_CATALOG_SQL = """
SELECT
    b.id              AS id,
    b.title           AS title,
    b.isbn            AS isbn,
    b.pubdate         AS pubdate,
    b.path            AS path,
    b.uuid            AS uuid,
    b.last_modified   AS last_modified,
    COALESCE(
        (SELECT GROUP_CONCAT(a.name, ', ')
         FROM books_authors_link bal
         JOIN authors a ON a.id = bal.author
         WHERE bal.book = b.id),
        ''
    )                 AS authors,
    COALESCE(
        (SELECT p.name
         FROM books_publishers_link bpl
         JOIN publishers p ON p.id = bpl.publisher
         WHERE bpl.book = b.id),
        NULL
    )                 AS publisher,
    COALESCE(
        (SELECT c.text
         FROM comments c
         WHERE c.book = b.id),
        NULL
    )                 AS comment,
    COALESCE(
        (SELECT GROUP_CONCAT(t.name, ', ')
         FROM books_tags_link btl
         JOIN tags t ON t.id = btl.tag
         WHERE btl.book = b.id),
        ''
    )                 AS tags,
    COALESCE(
        (SELECT MAX(rat.rating)
         FROM books_ratings_link brl
         JOIN ratings rat ON rat.id = brl.rating
         WHERE brl.book = b.id),
        0
    )                 AS rating,
    COALESCE(
        (SELECT GROUP_CONCAT(l.lang_code, ', ')
         FROM books_languages_link bll
         JOIN languages l ON l.id = bll.lang_code
         WHERE bll.book = b.id),
        ''
    )                 AS languages,
    COALESCE(
        (SELECT s.name
         FROM books_series_link bsl
         JOIN series s ON s.id = bsl.series
         WHERE bsl.book = b.id),
        NULL
    )                 AS series,
    COALESCE(
        (SELECT bsl.sort
         FROM books_series_link bsl
         WHERE bsl.book = b.id),
        NULL
    )                 AS series_index,
    COALESCE(
        (SELECT i.val
         FROM identifiers i
         WHERE i.book = b.id AND lower(i.type) = 'isbn'
         LIMIT 1),
        NULL
    )                 AS identifier_isbn
FROM books b
ORDER BY b.id
"""


__all__ = [
    "FORMAT_PREFERENCE",
    "CalibreImporter",
    "CalibreImportSummary",
    "CalibreVolume",
]
