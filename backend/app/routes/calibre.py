"""Calibre integration routes.

* ``POST /api/library/import-calibre`` — import a Calibre library catalog
  (reads ``metadata.db``, resolves real files, runs as a background task with
  SSE progress via the shared ``/api/library/scan-progress/{scan_id}`` stream).
* ``GET  /api/library/calibre-status``     — quick pre-flight check that a
  path looks like a Calibre library (used by the import dialog).
* ``GET  /books/{book_id}/calibre-web-url`` — build a deep link into a
  Calibre-Web instance for a Calibre-imported book.
"""

from __future__ import annotations

import asyncio
import uuid
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_manager, get_db
from app.logging_config import get_logger
from app.models import Book
from app.repositories import BookRepository, SettingsRepository
from app.scan_progress import ScanCancelledError, scan_store
from app.schemas import DirectoryImportRequest
from app.services.calibre_importer import CalibreImporter
from app.services.library_service import invalidate_stats_cache

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["calibre"])

# Reuse the library scan lock so a Calibre import and a normal scan can't
# stamp on each other's progress stream or DB batch commits.
from app.routes.library import (  # noqa: E402
    _active_scans,
    invalidate_book_list_cache,
)

# ---------------------------------------------------------------------- #
# Pre-flight check
# ---------------------------------------------------------------------- #


@router.get("/library/calibre-status")
async def calibre_library_status(
    path: str = Query(..., min_length=1, max_length=2000),
) -> dict:
    """Check whether ``path`` is a valid Calibre library root.

    Returns the absolute resolved path, the count of volumes in the catalog,
    and whether ``metadata.db`` is readable. Used by the import dialog to
    validate user input before kicking off the background import.
    """
    importer = CalibreImporter(path)
    try:
        importer.validate()
    except FileNotFoundError as e:
        return {"valid": False, "error": str(e), "path": str(importer.library_root)}

    volume_count = 0
    try:
        volumes = await asyncio.to_thread(importer._read_catalog)  # noqa: SLF001
        volume_count = len(volumes)
    except Exception as e:  # noqa: BLE001 — surface any DB read failure
        return {
            "valid": False,
            "error": f"Could not read metadata.db: {e}",
            "path": str(importer.library_root),
        }

    return {
        "valid": True,
        "path": str(importer.library_root),
        "volume_count": volume_count,
    }


# ---------------------------------------------------------------------- #
# Import
# ---------------------------------------------------------------------- #


@router.post("/library/import-calibre")
async def import_calibre_library(
    request: DirectoryImportRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Import a Calibre library into the index as a background task.

    Reads Calibre's ``metadata.db``, resolves each volume's real EPUB/PDF/MOBI
    file, copies covers into ``static_covers``, and writes ``Book`` rows tagged
    with the Calibre book id + uuid. Progress is streamed via the standard
    ``/api/library/scan-progress/{scan_id}`` SSE endpoint.

    Returns a ``scan_id`` immediately.
    """
    importer = CalibreImporter(request.path)
    try:
        importer.validate()
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if _active_scans:
        raise HTTPException(
            status_code=409,
            detail="A scan or import is already in progress. Please wait for it to complete.",
        )

    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    _active_scans.add(scan_id)

    async def _run() -> None:
        from app.services.calibre_sync_service import sync_library

        try:
            async with db_manager.get_session() as session:
                scan_store.update(
                    scan_id, phase="discovering", message="Reading Calibre catalog..."
                )

                async def _progress(processed: int, total: int, title: str) -> None:
                    if scan_store.is_cancelled(scan_id):
                        raise ScanCancelledError()
                    scan_store.update(
                        scan_id,
                        phase="importing",
                        processed=processed,
                        total_found=total,
                        current_file=title,
                        message=f"Importing Calibre library: {processed}/{total}",
                    )

                def _cancel() -> None:
                    if scan_store.is_cancelled(scan_id):
                        raise ScanCancelledError()

                try:
                    summary = await sync_library(
                        session,
                        request.path,
                        progress_callback=_progress,
                        cancel_check=_cancel,
                        prune_missing=True,
                    )

                    # Commit in batches is handled inside the loop via flush;
                    # finalize here.
                    await session.commit()

                    invalidate_stats_cache()
                    invalidate_book_list_cache()
                    scan_store.update(
                        scan_id,
                        status="completed",
                        phase="done",
                        imported=summary.imported,
                        updated=summary.updated,
                        skipped=summary.skipped_existing + summary.no_readable_format,
                        errors=summary.errors,
                        total_found=summary.total_in_library,
                        processed=summary.total_in_library,
                        message=(
                            f"Calibre sync complete: {summary.imported} imported, "
                            f"{summary.updated} updated, "
                            f"{summary.skipped_existing} unchanged"
                        ),
                    )
                except ScanCancelledError:
                    try:
                        await session.rollback()
                    except Exception:  # noqa: BLE001
                        pass
                    invalidate_stats_cache()
                    scan_store.update(
                        scan_id,
                        status="cancelled",
                        phase="cancelled",
                        message="Calibre import cancelled by user",
                    )
        except Exception as e:
            logger.exception("Calibre import failed")
            scan_store.update(scan_id, status="failed", phase="failed", message=str(e))
        finally:
            _active_scans.discard(scan_id)

    asyncio.create_task(_run())
    return {"scan_id": scan_id, "status": "started"}


# ---------------------------------------------------------------------- #
# Calibre-Web deep link
# ---------------------------------------------------------------------- #


@router.get("/books/{book_id}/calibre-web-url")
async def calibre_web_url(book_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Build the Calibre-Web URL for a book, if configured.

    Calibre-Web exposes each book at ``/book/<calibre_id>``. If the book wasn't
    imported from Calibre, or no Calibre-Web base URL is set, ``url`` is null.
    """
    book = await BookRepository(db).get_by_id_or_404(book_id)
    settings_repo = SettingsRepository(db)
    base = (await settings_repo.get("calibre_web_url") or "").rstrip("/")

    if not base:
        return {"url": None, "reason": "calibre_web_url not configured"}
    if not book.calibre_id:
        return {"url": None, "reason": "book is not from a Calibre library"}

    # Calibre-Web routes books by their numeric Calibre id.
    url = urljoin(base + "/", f"book/{book.calibre_id}")
    return {"url": url, "calibre_id": book.calibre_id}


@router.get("/books/{book_id}/open-calibre-web", response_class=RedirectResponse)
async def open_calibre_web(book_id: int, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    """Convenience 302 redirect to the book's Calibre-Web page.

    Lets a frontend use a plain anchor ``href`` (or window.open) and still go
    through a validated, configured endpoint. 404s if the book isn't linked or
    Calibre-Web isn't configured.
    """
    info = await calibre_web_url(book_id, db)
    if not info.get("url"):
        reason = info.get("reason", "unavailable")
        raise HTTPException(
            status_code=404,
            detail=f"Calibre-Web link unavailable ({reason}).",
        )
    # ``url`` already encodes the id; quote defensively in case of odd paths.
    return RedirectResponse(url=info["url"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------- #
# Reverse-direction deep link (spec 013)
# ---------------------------------------------------------------------- #
#
# A *separate* router without the ``/api`` prefix: this is a browser-facing
# GET that the reverse proxy rewrites Calibre-Web's "Read in web browser"
# into. Because it is not under ``/api/``, an unauthenticated request is
# redirected to ``/login`` by ``AuthMiddleware`` (page-route behaviour)
# rather than returned as a 401 JSON — the correct UX for a navigation.
web_router = APIRouter(tags=["calibre"])


@web_router.get("/calibre/launch", response_class=RedirectResponse)
async def launch_reader(
    calibre_id: int | None = Query(None, ge=1),
    calibre_uuid: str | None = Query(None, max_length=64),
    title: str | None = Query(None, max_length=500),
    author: str | None = Query(None, max_length=300),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Resolve a book and redirect to eLM's reader (spec 013).

    Resolution order (every branch returns a 302 — a user click must never hit
    a dead-end 404):

    1. ``calibre_id`` / ``calibre_uuid`` — direct lookup (Calibre-imported books).
    2. ``title`` (+ optional ``author``) — match by title. This is what the
       Calibre-Web userscript uses, since bulk-loaded eLM books have no
       ``calibre_id``. Tries exact (case-insensitive) title first, then a
       title ilike fallback, restricted to non-deleted books.
    3. Resolved book is hidden → ``/library?calibre_hidden=1`` (no password bypass).
    4. No match → ``/library?calibre_pending=<key>``.
    """
    from sqlalchemy import func as sa_func

    if calibre_id is None and not calibre_uuid and not title:
        return RedirectResponse(url="/library", status_code=302)

    book = None
    if calibre_id is not None:
        book = (
            await db.execute(select(Book).where(Book.calibre_id == calibre_id))
        ).scalar_one_or_none()
    elif calibre_uuid:
        book = (
            await db.execute(select(Book).where(Book.calibre_uuid == calibre_uuid))
        ).scalar_one_or_none()
    elif title:
        base = select(Book).where(Book.is_deleted.is_(False))
        q = base.where(sa_func.lower(Book.title) == title.strip().lower())
        if author:
            q = q.where(sa_func.lower(sa_func.coalesce(Book.author, "")) == author.strip().lower())
        book = (await db.execute(q.limit(1))).scalar_one_or_none()
        if book is None:
            # Looser fallback: title contains the term (no author constraint).
            book = (
                await db.execute(base.where(Book.title.ilike(f"%{title.strip()}%")).limit(1))
            ).scalar_one_or_none()

    if book is None:
        key = (
            calibre_id
            if calibre_id is not None
            else (calibre_uuid or (title and f"title:{title[:40]}") or "")
        )
        return RedirectResponse(url=f"/library?calibre_pending={key}", status_code=302)
    if book.is_hidden:
        return RedirectResponse(url="/library?calibre_hidden=1", status_code=302)
    return RedirectResponse(url=f"/reader/{book.id}", status_code=302)
