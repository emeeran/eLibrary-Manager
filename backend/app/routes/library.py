"""Library management routes."""

import asyncio
import hashlib
import json
import os
import shutil
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.database import get_db
from app.repositories import BookRepository
from app.scan_progress import ScanCancelledError, scan_store
from app.schemas import (
    BookListResponse,
    BookResponse,
    BookUpdate,
    DirectoryImportRequest,
    ProgressUpdate,
    book_to_response,
)
from app.services import LibraryService

router = APIRouter(prefix="/api", tags=["library"])
config = get_config()

# Guard against concurrent scans
_active_scans: set[str] = set()

# Search result cache — TTLCache handles expiration and size limits automatically
from cachetools import TTLCache

# Cross-request cache for list/search results. Sized for a large library where
# many distinct filter/sort/page combinations recur within the TTL. The repo's
# per-instance _count_cache doesn't span requests, so this is the real cache.
_search_cache: TTLCache = TTLCache(maxsize=256, ttl=60)


def invalidate_book_list_cache() -> None:
    """Clear the cached ``/api/books`` list responses.

    Any mutation that changes which books appear in a listing (or their
    visible flags — favorite/hidden/deleted) must call this, otherwise the UI
    keeps serving the stale cached list for up to ``ttl`` seconds and the
    change appears to "not work".
    """
    _search_cache.clear()


def _validate_path_within_library(file_path: str) -> str:
    """Validate that a path is within the configured library directory.

    Raises HTTPException if the path escapes the library root.
    """
    resolved = Path(file_path).resolve()
    library_root = Path(config.library_path).resolve()
    # Resolve symlinks to prevent escape via symlink chains
    resolved = resolved.resolve()
    try:
        resolved.relative_to(library_root)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Path must be within the configured library directory",
        ) from None
    return str(resolved)


# Blocked system directories for filesystem browsing
_BLOCKED_PATHS = {
    "/etc",
    "/root",
    "/boot",
    "/dev",
    "/proc",
    "/sys",
    "/run",
    "/sbin",
    "/bin",
    "/lib",
    "/lib64",
    "/usr",
    "/var",
    "/lost+found",
    "/snap",
    "/swapfile",
}


def _validate_path_safe(file_path: str) -> str:
    """Validate that an arbitrary local path is safe to access.

    Blocks sensitive system directories. Used for indexing directories
    outside the configured library_path.
    """
    resolved = Path(file_path).resolve()
    resolved_str = str(resolved)

    for blocked in _BLOCKED_PATHS:
        if resolved_str == blocked or resolved_str.startswith(blocked + "/"):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: system directory ({blocked})",
            )

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {file_path}")

    if not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Not a directory: {file_path}",
        )

    return resolved_str


async def _run_background_scan(
    scan_id: str,
    coro_fn: Callable[[LibraryService], Awaitable[Any]],
    complete_message: str = "Scan complete",
) -> None:
    """Shared background task runner for scan operations."""
    from app.database import db_manager as _db_manager

    try:
        async with _db_manager.get_session() as db:
            service = LibraryService(db)
            try:
                results = await coro_fn(service)
                # Handle both flat stats and nested {"local": ..., "nas": ...} format
                if "local" in results:
                    local = results["local"]
                    nas = results.get("nas", {})
                    combined = {
                        "imported": local.get("imported", 0) + nas.get("imported", 0),
                        "skipped": local.get("skipped", 0) + nas.get("skipped", 0),
                        "errors": local.get("errors", 0) + nas.get("errors", 0),
                        "total": local.get("total", 0) + nas.get("total", 0),
                    }
                else:
                    combined = results
                scan_store.update(
                    scan_id,
                    phase="finalizing",
                    message="Finalizing...",
                )
                from app.services.library_service import invalidate_stats_cache

                invalidate_stats_cache()
                scan_store.update(
                    scan_id,
                    status="completed",
                    phase="done",
                    imported=combined.get("imported", 0),
                    skipped=combined.get("skipped", 0),
                    errors=combined.get("errors", 0),
                    total_found=combined.get("total", 0),
                    processed=combined.get("total", 0),
                    message=complete_message,
                )
            except ScanCancelledError:
                # Cooperative cancellation. Roll back any uncommitted batch and
                # mark the scan cancelled so the SSE client gets a final event.
                try:
                    await db.rollback()
                except Exception:
                    pass
                from app.services.library_service import invalidate_stats_cache

                invalidate_stats_cache()
                scan_store.update(
                    scan_id,
                    status="cancelled",
                    phase="cancelled",
                    message="Scan cancelled by user",
                )
            except Exception as e:
                scan_store.update(scan_id, status="failed", phase="failed", message=str(e))
    finally:
        _active_scans.discard(scan_id)


@router.post("/library/scan")
async def scan_library(
    mode: str = "fast",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger library scan as a background task.

    Returns a scan_id for tracking progress via SSE.
    Only one scan can run at a time.
    """
    if _active_scans:
        raise HTTPException(
            status_code=409,
            detail="A scan is already in progress. Please wait for it to complete.",
        )

    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    _active_scans.add(scan_id)

    async def _scan_coro(service: LibraryService) -> Any:
        if mode == "full":
            return await service.scan_and_import(scan_id=scan_id)
        return await service.fast_index(scan_id=scan_id)

    asyncio.create_task(_run_background_scan(scan_id, _scan_coro, "Scan complete"))
    return {"scan_id": scan_id, "status": "started"}


@router.post("/library/backfill-content")
async def backfill_content() -> dict:
    """Build the full-text CONTENT index as a background task (spec 012).

    Extracts every book's text into ``books_content_fts`` so the library search
    box matches book content, not just title/author. Returns a ``scan_id`` for
    the shared SSE progress stream. Mutually exclusive with any running
    scan/import (shares ``_active_scans``).
    """
    if _active_scans:
        raise HTTPException(
            status_code=409,
            detail="A scan or import is already in progress. Please wait for it to complete.",
        )

    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    _active_scans.add(scan_id)

    async def _run() -> None:
        from app.database import db_manager as _db_manager
        from app.services.content_backfill_service import run_content_backfill
        from app.services.library_service import invalidate_stats_cache

        try:
            async with _db_manager.get_session() as session:

                def _cancel() -> None:
                    if scan_store.is_cancelled(scan_id):
                        raise ScanCancelledError()

                async def _progress(processed: int, total: int, current: str) -> None:
                    if scan_store.is_cancelled(scan_id):
                        raise ScanCancelledError()
                    scan_store.update(
                        scan_id,
                        phase="indexing",
                        processed=processed,
                        total_found=total,
                        current_file=current,
                        message=f"Indexing content: {processed}/{total}",
                    )

                try:
                    stats = await run_content_backfill(
                        session, progress_callback=_progress, cancel_check=_cancel
                    )
                    await session.commit()
                    invalidate_stats_cache()
                    scan_store.update(
                        scan_id,
                        status="completed",
                        phase="done",
                        message=(
                            f"Content index complete: {stats['extracted']} indexed, "
                            f"{stats['empty']} empty, {stats['failed']} failed"
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
                        message="Content indexing cancelled by user",
                    )
        except Exception as e:  # noqa: BLE001
            scan_store.update(scan_id, status="failed", phase="failed", message=str(e))
        finally:
            _active_scans.discard(scan_id)

    asyncio.create_task(_run())
    return {"scan_id": scan_id, "status": "started"}


@router.get("/library/content-index-status")
async def content_index_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Report content-index coverage (extracted / pending / empty / failed)."""
    from app.repositories import BookContentRepository

    counts = await BookContentRepository(db).status_counts()
    total = await BookRepository(db).count()
    return {
        "total": total,
        "indexed": counts.get("extracted", 0),
        "pending": counts.get("pending", 0),
        "empty": counts.get("empty", 0),
        "failed": counts.get("failed", 0),
    }


@router.get("/library/scan-progress/{scan_id}")
async def scan_progress_stream(scan_id: str) -> StreamingResponse:
    """Stream scan progress via Server-Sent Events.

    Polls the in-memory progress store and yields JSON events
    until the scan completes or fails.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            progress = scan_store.get(scan_id)
            if not progress:
                yield f"data: {json.dumps({'status': 'unknown', 'message': 'Scan not found'})}\n\n"
                break

            yield f"data: {json.dumps(scan_store.to_dict(progress))}\n\n"

            if progress.status in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/library/scan-cancel/{scan_id}")
async def cancel_scan(scan_id: str) -> dict:
    """Request cooperative cancellation of a running scan.

    Sets a flag that the scan loops check between files; the scan stops at
    the next batch boundary, rolls back its current uncommitted batch, and the
    SSE stream delivers a final ``status == "cancelled"`` event.
    """
    ok = scan_store.request_cancel(scan_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Scan not found or already finished.",
        )
    return {"scan_id": scan_id, "status": "cancelling"}


@router.post("/library/import-dir")
async def import_directory(
    request: DirectoryImportRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Import books from a specific directory as a background task.

    Returns a scan_id for tracking progress via SSE.
    """
    if not os.path.exists(request.path) or not os.path.isdir(request.path):
        raise HTTPException(status_code=400, detail=f"Directory not found: {request.path}")

    _validate_path_within_library(request.path)

    if _active_scans:
        raise HTTPException(status_code=409, detail="A scan is already in progress.")

    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    _active_scans.add(scan_id)

    async def _import_coro(service: LibraryService) -> Any:
        return await service.scan_and_import(request.path, scan_id=scan_id)

    asyncio.create_task(_run_background_scan(scan_id, _import_coro, "Import complete"))
    return {"scan_id": scan_id, "status": "started"}


@router.post("/library/index-local-dir")
async def index_local_directory(
    request: DirectoryImportRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Index books from any local directory on the filesystem.

    Unlike /import-dir, this endpoint is not restricted to the
    configured library_path. It allows indexing ebooks from any
    accessible directory (e.g. ~/ebooks, /mnt/storage/books).

    Security: blocks sensitive system directories.
    """
    safe_path = _validate_path_safe(request.path)

    if _active_scans:
        raise HTTPException(status_code=409, detail="A scan is already in progress.")

    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    _active_scans.add(scan_id)

    async def _index_coro(service: LibraryService) -> Any:
        return await service.fast_index(safe_path, scan_id=scan_id)

    asyncio.create_task(
        _run_background_scan(scan_id, _index_coro, "Local directory index complete")
    )
    return {"scan_id": scan_id, "status": "started", "path": safe_path}


@router.get("/library/browse-fs")
async def browse_filesystem(
    path: str = "/",
) -> list[dict]:
    """Browse the local filesystem for directory selection.

    Returns subdirectories of the given path. Used by the frontend
    directory browser to pick directories outside the library_path.
    Uses os.scandir for fast, non-blocking directory listing.
    """
    from fastapi.concurrency import run_in_threadpool

    resolved = Path(path).resolve()
    resolved_str = str(resolved)

    # Block sensitive paths
    for blocked in _BLOCKED_PATHS:
        if resolved_str == blocked or resolved_str.startswith(blocked + "/"):
            raise HTTPException(
                status_code=403,
                detail="Access denied: system directory",
            )

    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {path}")

    def _list_dirs() -> list[dict]:
        entries = []
        try:
            with os.scandir(resolved) as it:
                dirs = [
                    e
                    for e in it
                    if e.is_dir(follow_symlinks=False)
                    and not e.name.startswith(".")
                    and str(Path(e.path).resolve()) not in _BLOCKED_PATHS
                ]
            dirs.sort(key=lambda e: e.name.lower())

            for entry in dirs:
                try:
                    # Quick has_subdirs check — stops at first subdir found
                    with os.scandir(entry.path) as sub_it:
                        has_subdirs = any(
                            s.is_dir(follow_symlinks=False) and not s.name.startswith(".")
                            for s in sub_it
                        )
                    entries.append(
                        {
                            "name": entry.name,
                            "path": str(Path(entry.path).resolve()),
                            "has_subdirs": has_subdirs,
                        }
                    )
                except PermissionError:
                    entries.append(
                        {
                            "name": entry.name,
                            "path": str(Path(entry.path).resolve()),
                            "has_subdirs": False,
                            "permission_denied": True,
                        }
                    )
        except PermissionError:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {path}",
            ) from None
        return entries

    return await run_in_threadpool(_list_dirs)


@router.post("/library/import-file")
async def import_book_file(request: dict, db: AsyncSession = Depends(get_db)) -> BookResponse:
    """Import a book file from an existing file path.

    Args:
        request: Dictionary with 'file_path' key containing absolute path to book file
        db: Database session

    Returns:
        Imported book metadata
    """
    file_path = request.get("file_path")
    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    # Validate path is within library directory
    _validate_path_within_library(file_path)

    # Validate file exists
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Check extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in {".epub", ".pdf", ".mobi"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {ext}")

    try:
        service = LibraryService(db)
        book = await service.import_book(file_path)
        return book_to_response(book)

    except Exception as e:
        from app.logging_config import get_logger

        logger = get_logger(__name__)
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}") from e


@router.post("/library/upload")
async def upload_book(
    file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
) -> BookResponse:
    """Upload and import a book file by indexing its path (no copy).

    Note: The uploaded file is saved to a temporary uploads directory,
    and only its path is indexed. The file is not copied to the library.

    Args:
        file: Uploaded file
        db: Database session

    Returns:
        Imported book metadata
    """
    # Sanitize filename to prevent path traversal
    filename = os.path.basename(file.filename or "unknown")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".epub", ".pdf", ".mobi"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {ext}")

    # Create uploads directory if needed
    uploads_dir = os.path.join(os.path.dirname(config.library_path), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # Save uploaded file to uploads directory
    file_path = os.path.join(uploads_dir, filename)

    try:
        from fastapi.concurrency import run_in_threadpool

        def _save_upload() -> None:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        await run_in_threadpool(_save_upload)

        service = LibraryService(db)
        book = await service.import_book(file_path)
        return book_to_response(book)

    except Exception as e:
        # Cleanup if failed
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        from app.logging_config import get_logger

        logger = get_logger(__name__)
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}") from e


@router.post("/library/refresh-covers")
async def refresh_covers(force: bool = False, db: AsyncSession = Depends(get_db)) -> dict:
    """Re-extract covers for books missing them.

    Args:
        force: If True, re-extract all covers. If False, only missing ones.
        db: Database session

    Returns:
        Refresh statistics
    """
    service = LibraryService(db)
    results = await service.refresh_covers(force=force)
    return results


@router.get("/books/series")
async def list_series(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Distinct series with book counts, for the series facet (spec 012)."""
    from sqlalchemy import func, select

    from app.models import Book

    rows = (
        await db.execute(
            select(Book.series, func.count(Book.id))
            .where(Book.series.isnot(None), Book.is_hidden.is_(False))
            .group_by(Book.series)
            .order_by(func.count(Book.id).desc())
        )
    ).all()
    return [{"name": r[0], "count": int(r[1])} for r in rows]


@router.get("/books", response_model=BookListResponse)
async def list_books(
    request: Request,
    page: int = 1,
    page_size: int = 20,  # max 100 enforced below
    favorite_only: bool = False,
    recent_only: bool = False,
    reading_only: bool = False,
    deleted_only: bool = False,
    search: str | None = None,
    format_filter: str | None = None,
    source_filter: str | None = None,
    sort_by: str = "added_date",
    sort_order: str = "desc",
    category_id: int | None = None,
    hidden_only: bool = False,
    show_hidden: bool = False,
    directory_filter: str | None = None,
    series: str | None = None,
    rating_min: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> BookListResponse:
    """List books with pagination, filters, and sorting.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        favorite_only: Filter favorites
        recent_only: Filter recent
        search: Search term
        format_filter: Filter by file format
        source_filter: Filter by storage source ("local" or "nas")
        sort_by: Column to sort by (title, author, added_date, last_read, progress)
        sort_order: Sort direction ("asc" or "desc")
        category_id: Filter by category ID
        directory_filter: Filter by parent directory path
        db: Database session

    Returns:
        Paginated book list
    """
    # Enforce pagination limits
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    # Series facet: comma-separated names → list (spec 012).
    series_filter = (
        [s.strip() for s in series.split(",") if s.strip()] if series else None
    )
    rating_min = rating_min if (rating_min and 1 <= rating_min <= 5) else None

    service = LibraryService(db)

    # Handle deleted_only: soft-deleted (pruned from Calibre) books OR books with
    # missing files. Bypasses the response cache.
    if deleted_only:
        from sqlalchemy import or_, select

        from app.models import Book

        stale_ids = await BookRepository(db).get_stale_book_ids()

        conds = [Book.is_deleted.is_(True)]
        if stale_ids:
            conds.append(Book.id.in_(stale_ids))
        result = await db.execute(select(Book).where(or_(*conds)))
        books = result.scalars().all()

        deleted_book_ids = [b.id for b in books]
        categories_map = await service.book_repo.get_categories_for_books(deleted_book_ids)

        return BookListResponse(
            books=[book_to_response(b, categories=categories_map.get(b.id, [])) for b in books],
            total=len(books),
            page=page,
            page_size=page_size,
            counts=None,
        )

    # Check search cache — include session token hash for user isolation
    from app.auth import SESSION_COOKIE_NAME as _SCN

    session_token = request.cookies.get(_SCN, "")
    user_hash = hashlib.sha256(session_token.encode()).hexdigest()[:8] if session_token else "anon"
    cache_key = f"{user_hash}|{search}|{format_filter}|{sort_by}|{sort_order}|{page}|{favorite_only}|{recent_only}|{reading_only}|{category_id}|{directory_filter}|{hidden_only}|{show_hidden}|{series_filter}|{rating_min}"
    if cache_key in _search_cache:
        return _search_cache[cache_key]

    books, total = await service.list_books(
        page=page,
        page_size=page_size,
        favorite_only=favorite_only,
        recent_only=recent_only,
        reading_only=reading_only,
        search=search,
        format_filter=format_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        source_filter=source_filter if source_filter in ("local", "nas") else None,
        category_id=category_id,
        hidden_only=hidden_only,
        show_hidden=show_hidden,
        directory_filter=directory_filter,
        series_filter=series_filter,
        rating_min=rating_min,
    )

    # Batch-fetch categories for all books in a single query
    book_ids = [book.id for book in books]
    categories_map = await service.book_repo.get_categories_for_books(book_ids)

    # When searching, surface a content snippet for any book that matched by body
    # text (spec 012). No-op when not searching or no content index.
    content_snippets = None
    if search:
        from app.repositories import BookContentRepository, _build_fts_query

        fts_match = _build_fts_query(search)
        if fts_match:
            content_snippets = await BookContentRepository(db).snippets_for(book_ids, fts_match)

    result = BookListResponse(
        books=[
            book_to_response(book, categories=categories_map.get(book.id, [])) for book in books
        ],
        total=total,
        page=page,
        page_size=page_size,
        counts=None,  # Fetched independently via /api/stats/sidebar
        content_snippets=content_snippets,
    )

    _search_cache[cache_key] = result
    return result


@router.get("/books/{book_id}", response_model=BookResponse)
async def get_book(book_id: int, db: AsyncSession = Depends(get_db)) -> BookResponse:
    """Get book details.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        Book details
    """
    service = LibraryService(db)
    book = await service.get_book(book_id)
    return book_to_response(book)


@router.patch("/books/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: int, update_data: BookUpdate, db: AsyncSession = Depends(get_db)
) -> BookResponse:
    """Update book details.

    Args:
        book_id: Book primary key
        update_data: Update data (partial)
        db: Database session

    Returns:
        Updated book
    """
    repo = BookRepository(db)
    book = await repo.update(book_id, update_data)
    return book_to_response(book)


@router.post("/books/{book_id}/restore")
async def restore_book(book_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Restore a soft-deleted book (clear its ``is_deleted`` flag). Spec 011 v1.2."""
    from sqlalchemy import update

    from app.models import Book

    result = await db.execute(
        update(Book).where(Book.id == book_id).values(is_deleted=False)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    await db.commit()
    invalidate_book_list_cache()
    from app.services.library_service import invalidate_stats_cache

    invalidate_stats_cache()
    return {"restored": True, "book_id": book_id}


@router.post("/books/{book_id}/cover")
async def upload_cover(
    book_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Upload or update a book's cover image.

    Accepts JPG, PNG, or WebP images. Saves to static_covers directory.

    Args:
        book_id: Book primary key
        file: Uploaded image file
        db: Database session

    Returns:
        Updated cover path
    """
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type. Accepted: JPG, PNG, WebP")

    service = LibraryService(db)
    book = await service.get_book(book_id)

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"

    filename = f"cover_{book_id}.{ext}"
    covers_dir = config.covers_path
    os.makedirs(covers_dir, exist_ok=True)
    filepath = os.path.join(covers_dir, filename)

    content = await file.read()

    def _write_cover() -> None:
        with open(filepath, "wb") as f:
            f.write(content)

    await asyncio.get_event_loop().run_in_executor(None, _write_cover)

    book.cover_path = filename
    await db.flush()

    return {"cover_path": filename}


@router.delete("/books/{book_id}")
async def delete_book(book_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Delete a book.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        Success message
    """
    repo = BookRepository(db)
    await repo.delete(book_id)
    invalidate_book_list_cache()
    return {"message": "Book deleted successfully"}


@router.post("/books/{book_id}/favorite", response_model=BookResponse)
async def toggle_favorite(book_id: int, db: AsyncSession = Depends(get_db)) -> BookResponse:
    """Toggle book favorite status.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        Updated book
    """
    service = LibraryService(db)
    book = await service.get_book(book_id)
    book.is_favorite = not book.is_favorite
    await db.flush()
    await db.refresh(book)
    invalidate_book_list_cache()
    return book_to_response(book)


@router.post("/books/{book_id}/progress", response_model=BookResponse)
async def update_progress(
    book_id: int, progress: ProgressUpdate, db: AsyncSession = Depends(get_db)
) -> BookResponse:
    """Update reading progress.

    Args:
        book_id: Book primary key
        progress: Progress data
        db: Database session

    Returns:
        Updated book
    """
    from app.services import ReaderService

    service = ReaderService(db)
    book = await service.update_progress(book_id, progress)
    return book_to_response(book)


@router.get("/stats")
async def get_library_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """Get library statistics.

    Returns:
        Library stats dictionary
    """
    service = LibraryService(db)
    stats = await service.get_library_stats()
    return stats


# ============================================
# NAS CACHE ENDPOINTS
# ============================================


@router.post("/books/{book_id}/cache")
async def cache_book_offline(book_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Pre-cache a NAS book for offline access.

    Args:
        book_id: Book primary key.
        db: Database session.

    Returns:
        Success message with cache info.
    """
    from app.nas_cache import get_nas_cache
    from app.repositories import BookRepository

    repo = BookRepository(db)
    book = await repo.get_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if getattr(book, "storage_type", "local") != "nas":
        return {"message": "Only NAS books can be cached for offline access"}

    cache = get_nas_cache()
    if not cache:
        raise HTTPException(status_code=400, detail="NAS cache not configured")

    cached_path = await cache.put(book.path)
    size = os.path.getsize(cached_path) if os.path.exists(cached_path) else 0
    return {
        "message": "Book cached for offline access",
        "cached_path": cached_path,
        "size_bytes": size,
    }


@router.delete("/books/{book_id}/cache")
async def remove_book_cache(book_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Remove a book from the offline cache.

    Args:
        book_id: Book primary key.
        db: Database session.

    Returns:
        Success message.
    """
    from app.nas_cache import get_nas_cache
    from app.repositories import BookRepository

    repo = BookRepository(db)
    book = await repo.get_by_id(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    cache = get_nas_cache()
    if not cache:
        raise HTTPException(status_code=400, detail="NAS cache not configured")

    removed = await cache.remove(book.path)
    return {
        "message": "Cache removed" if removed else "Book was not cached",
    }


@router.get("/library/cache-status")
async def get_cache_status() -> dict:
    """Get NAS cache status and statistics.

    Returns:
        Cache status with size info and cached book list.
    """
    from app.nas_cache import get_nas_cache

    cache = get_nas_cache()
    if not cache:
        return {
            "cached_books": 0,
            "total_cache_size_bytes": 0,
            "max_cache_size_bytes": 0,
            "books": [],
        }

    cached = cache.list_cached()
    return {
        "cached_books": len(cached),
        "total_cache_size_bytes": cache.get_total_size(),
        "max_cache_size_bytes": cache.max_size,
        "books": cached,
    }


# ============================================
# DIRECTORY BROWSING ENDPOINTS
# ============================================


@router.get("/library/directories")
async def list_directories(
    parent: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List directories with book counts, supporting tree browsing.

    When `parent` is None, returns root-level directories.
    When `parent` is a path, returns its immediate children.
    Each entry includes path, name, book_count (direct),
    total_count (recursive), and has_subdirs flag.
    """
    import os
    from collections import Counter

    from sqlalchemy import select

    from app.models import Book

    result = await db.execute(select(Book.path).where(Book.is_hidden.is_(False)))
    paths = [row[0] for row in result.all()]

    if not paths:
        return []

    # Count books per immediate directory
    dir_counts: Counter = Counter(os.path.dirname(p) for p in paths)

    def _get_children(parent_path: str) -> list[str]:
        """Get immediate children of a directory that contain books."""
        prefix = parent_path.rstrip("/") + "/"
        children: set[str] = set()
        for d in dir_counts:
            if d.startswith(prefix):
                rest = d[len(prefix) :]
                child_name = rest.split("/")[0]
                children.add(prefix + child_name)
        return sorted(children)

    # Determine root level using common prefix
    if parent is None:
        all_dir_list = sorted(dir_counts.keys())
        prefix = os.path.commonprefix(all_dir_list)
        # Truncate to last complete path segment
        if not prefix.endswith("/"):
            prefix = prefix.rsplit("/", 1)[0]

        if prefix:
            dirs_to_return = _get_children(prefix)
        else:
            # Multiple unrelated roots — find shallowest directories
            min_depth = min(d.count("/") for d in dir_counts)
            dirs_to_return = sorted(d for d in dir_counts if d.count("/") == min_depth)
    else:
        dirs_to_return = _get_children(parent)

    # Build response
    response = []
    for d in dirs_to_return:
        name = d.rsplit("/", 1)[-1] if "/" in d else d
        direct_books = dir_counts.get(d, 0)
        d_prefix = d + "/"
        total_books = direct_books + sum(
            c for dd, c in dir_counts.items() if dd.startswith(d_prefix)
        )
        has_children = any(dd.startswith(d_prefix) and dd != d for dd in dir_counts)

        response.append(
            {
                "directory": d,
                "name": name,
                "book_count": direct_books,
                "total_count": total_books,
                "has_subdirs": has_children,
            }
        )

    return response


@router.get("/library/formats")
async def list_formats(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List unique file formats with book counts."""
    from sqlalchemy import func, select

    from app.models import Book

    result = await db.execute(
        select(Book.format, func.count(Book.id))
        .where(Book.is_hidden.is_(False))
        .group_by(Book.format)
        .order_by(func.count(Book.id).desc())
    )
    return [{"format": row[0], "book_count": row[1]} for row in result.all()]
