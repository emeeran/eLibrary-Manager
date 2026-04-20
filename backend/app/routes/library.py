"""Library management routes."""

import asyncio
import json
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.database import get_db
from app.scan_progress import scan_store
from app.schemas import (
    BookListResponse,
    BookResponse,
    BookUpdate,
    CategoryAssignRequest,
    CategoryCreate,
    CategoryResponse,
    DirectoryImportRequest,
    ProgressUpdate,
    book_to_response,
)
from app.services import LibraryService

router = APIRouter(prefix="/api", tags=["library"])
config = get_config()


async def _run_scan(scan_id: str, mode: str) -> None:
    """Background task that runs the scan and updates progress."""
    from app.database import db_manager

    async with db_manager.get_session() as db:
        service = LibraryService(db)
        try:
            if mode == "full":
                results = await service.scan_and_import(scan_id=scan_id)
            else:
                results = await service.fast_index(scan_id=scan_id)

            # Final update with totals
            scan_store.update(
                scan_id,
                status="completed",
                imported=results.get("imported", 0),
                skipped=results.get("skipped", 0),
                errors=results.get("errors", 0),
                total_found=results.get("total", 0),
                processed=results.get("total", 0),
                message="Scan complete",
            )
        except Exception as e:
            scan_store.update(scan_id, status="failed", message=str(e))


async def _run_import_dir(scan_id: str, directory: str) -> None:
    """Background task for directory import."""
    from app.database import db_manager

    async with db_manager.get_session() as db:
        service = LibraryService(db)
        try:
            results = await service.scan_and_import(directory, scan_id=scan_id)
            scan_store.update(
                scan_id,
                status="completed",
                imported=results.get("imported", 0),
                skipped=results.get("skipped", 0),
                errors=results.get("errors", 0),
                total_found=results.get("total", 0),
                processed=results.get("total", 0),
                message="Import complete",
            )
        except Exception as e:
            scan_store.update(scan_id, status="failed", message=str(e))


@router.post("/library/scan")
async def scan_library(
    mode: str = "fast",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger library scan as a background task.

    Returns a scan_id for tracking progress via SSE.
    """
    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    asyncio.create_task(_run_scan(scan_id, mode))
    return {"scan_id": scan_id, "status": "started"}


@router.get("/library/scan-progress/{scan_id}")
async def scan_progress_stream(scan_id: str) -> StreamingResponse:
    """Stream scan progress via Server-Sent Events.

    Polls the in-memory progress store and yields JSON events
    until the scan completes or fails.
    """
    async def event_generator():
        while True:
            progress = scan_store.get(scan_id)
            if not progress:
                yield f"data: {json.dumps({'status': 'unknown', 'message': 'Scan not found'})}\n\n"
                break

            yield f"data: {json.dumps(scan_store.to_dict(progress))}\n\n"

            if progress.status in ("completed", "failed"):
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


@router.post("/library/import-dir")
async def import_directory(
    request: DirectoryImportRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Import books from a specific directory as a background task.

    Returns a scan_id for tracking progress via SSE.
    """
    if not os.path.exists(request.path) or not os.path.isdir(request.path):
        raise HTTPException(
            status_code=400,
            detail=f"Directory not found: {request.path}"
        )

    scan_id = uuid.uuid4().hex[:8]
    scan_store.create(scan_id)
    asyncio.create_task(_run_import_dir(scan_id, request.path))
    return {"scan_id": scan_id, "status": "started"}


@router.post("/library/import-file")
async def import_book_file(
    request: dict,
    db: AsyncSession = Depends(get_db)
) -> BookResponse:
    """Import a book file from an existing file path.

    Args:
        request: Dictionary with 'file_path' key containing absolute path to book file
        db: Database session

    Returns:
        Imported book metadata
    """
    file_path = request.get("file_path")
    if not file_path:
        raise HTTPException(
            status_code=400,
            detail="file_path is required"
        )

    # Validate file exists
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {file_path}"
        )

    # Check extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in {".epub", ".pdf", ".mobi"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}"
        )

    try:
        service = LibraryService(db)
        book = await service.import_book(file_path)
        return book_to_response(book)

    except Exception as e:
        from app.logging_config import get_logger
        logger = get_logger(__name__)
        logger.error(f"Import failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}"
        )


@router.post("/library/upload")
async def upload_book(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
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
    # Check extension
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".epub", ".pdf", ".mobi"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}"
        )

    # Create uploads directory if needed
    uploads_dir = os.path.join(os.path.dirname(config.library_path), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # Save uploaded file to uploads directory
    file_path = os.path.join(uploads_dir, filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

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
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


@router.post("/library/refresh-covers")
async def refresh_covers(
    force: bool = False,
    db: AsyncSession = Depends(get_db)
) -> dict:
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


@router.get("/books", response_model=BookListResponse)
async def list_books(
    page: int = 1,
    page_size: int = 20,
    favorite_only: bool = False,
    recent_only: bool = False,
    search: str | None = None,
    format_filter: str | None = None,
    source_filter: str | None = None,
    sort_by: str = "added_date",
    sort_order: str = "desc",
    category_id: int | None = None,
    hidden_only: bool = False,
    show_hidden: bool = False,
    directory_filter: str | None = None,
    db: AsyncSession = Depends(get_db)
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
    service = LibraryService(db)
    books, total = await service.list_books(
        page=page,
        page_size=page_size,
        favorite_only=favorite_only,
        recent_only=recent_only,
        search=search,
        format_filter=format_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        source_filter=source_filter if source_filter in ("local", "nas") else None,
        category_id=category_id,
        hidden_only=hidden_only,
        show_hidden=show_hidden,
        directory_filter=directory_filter,
    )

    # Get sidebar counts for real-time updates
    stats = await service.get_library_stats()
    counts = {
        "all": stats.get("total_books", 0),
        "recent": stats.get("recent_books", 0),
        "favorites": stats.get("favorite_books", 0),
        "reading": stats.get("reading_books", 0),
        "deleted": stats.get("deleted_books", 0),
        "hidden": stats.get("hidden_books", 0),
    }

    return BookListResponse(
        books=[book_to_response(book) for book in books],
        total=total,
        page=page,
        page_size=page_size,
        counts=counts
    )


@router.get("/books/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> BookResponse:
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
    book_id: int,
    update_data: BookUpdate,
    db: AsyncSession = Depends(get_db)
) -> BookResponse:
    """Update book details.

    Args:
        book_id: Book primary key
        update_data: Update data (partial)
        db: Database session

    Returns:
        Updated book
    """
    service = LibraryService(db)
    book = await service.update_book(book_id, update_data)
    return book_to_response(book)


@router.post("/books/{book_id}/cover")
async def upload_cover(
    book_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
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
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Accepted: JPG, PNG, WebP"
        )

    service = LibraryService(db)
    book = await service.get_book(book_id)

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"

    filename = f"cover_{book_id}.{ext}"
    covers_dir = config.covers_path
    os.makedirs(covers_dir, exist_ok=True)
    filepath = os.path.join(covers_dir, filename)

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    book.cover_path = filename
    await db.commit()

    return {"cover_path": filename}


@router.delete("/books/{book_id}")
async def delete_book(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Delete a book.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        Success message
    """
    service = LibraryService(db)
    await service.delete_book(book_id)
    return {"message": "Book deleted successfully"}


@router.post("/books/{book_id}/favorite", response_model=BookResponse)
async def toggle_favorite(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> BookResponse:
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
    await db.commit()
    await db.refresh(book)
    return book_to_response(book)


@router.post("/books/{book_id}/progress", response_model=BookResponse)
async def update_progress(
    book_id: int,
    progress: ProgressUpdate,
    db: AsyncSession = Depends(get_db)
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
async def cache_book_offline(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Pre-cache a NAS book for offline access.

    Args:
        book_id: Book primary key.
        db: Database session.

    Returns:
        Success message with cache info.
    """
    from app.nas_cache import get_nas_cache

    repo = BookRepository(db) if hasattr(BookRepository, '__module__') else None
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
async def remove_book_cache(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
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
# CATEGORY ENDPOINTS
# ============================================

@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[CategoryResponse]:
    """List all categories with book counts."""
    from sqlalchemy import func, select
    from app.models import Category, BookCategory

    # Single query with LEFT JOIN — no N+1, top 10 by book count
    result = await db.execute(
        select(
            Category.id,
            Category.name,
            Category.color,
            func.count(BookCategory.book_id).label("book_count"),
        )
        .outerjoin(BookCategory, Category.id == BookCategory.category_id)
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.count(BookCategory.book_id).desc(), Category.name)
        .limit(10)
    )

    return [
        CategoryResponse(id=row.id, name=row.name, color=row.color, book_count=row.book_count)
        for row in result.all()
    ]


@router.post("/categories", response_model=CategoryResponse, status_code=201)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db)
) -> CategoryResponse:
    """Create a new category."""
    from app.models import Category

    # Check for duplicate name
    from sqlalchemy import select
    existing = await db.execute(select(Category).where(Category.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Category already exists")

    cat = Category(name=data.name, color=data.color)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return CategoryResponse(id=cat.id, name=cat.name, color=cat.color, book_count=0)


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Delete a category."""
    from sqlalchemy import select
    from app.models import Category

    result = await db.execute(select(Category).where(Category.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    await db.delete(cat)
    await db.commit()
    return {"message": "Category deleted"}


@router.post("/books/{book_id}/categories")
async def assign_categories(
    book_id: int,
    data: CategoryAssignRequest,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Assign categories to a book (replaces existing assignments)."""
    from app.models import BookCategory

    # Remove existing assignments
    await db.execute(
        BookCategory.__table__.delete().where(BookCategory.book_id == book_id)
    )

    # Add new assignments
    for cat_id in data.category_ids:
        db.add(BookCategory(book_id=book_id, category_id=cat_id))

    await db.commit()
    return {"message": "Categories updated", "category_ids": data.category_ids}


@router.delete("/books/{book_id}/categories/{category_id}")
async def remove_category_from_book(
    book_id: int,
    category_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Remove a category from a book."""
    from app.models import BookCategory
    from sqlalchemy import select

    result = await db.execute(
        select(BookCategory).where(
            BookCategory.book_id == book_id,
            BookCategory.category_id == category_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Assignment not found")

    await db.delete(link)
    await db.commit()
    return {"message": "Category removed from book"}


# ============================================
# DIRECTORY BROWSING ENDPOINTS
# ============================================


@router.get("/library/directories")
async def list_directories(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List unique source directories with book counts.

    Returns the top 20 directories (by book count) derived from
    book file paths. Each entry includes the full directory path,
    display name, and book count.
    """
    from collections import Counter
    from os.path import dirname

    from sqlalchemy import select

    from app.models import Book

    result = await db.execute(
        select(Book.path).where(Book.is_hidden == False)
    )
    paths = [row[0] for row in result.all()]

    dir_counts = Counter(dirname(p) for p in paths)

    directories = [
        {
            "directory": d,
            "name": d.rsplit("/", 1)[-1] if "/" in d else d,
            "book_count": count,
        }
        for d, count in dir_counts.most_common(20)
    ]
    return directories


@router.get("/library/formats")
async def list_formats(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List unique file formats with book counts."""
    from sqlalchemy import func, select

    from app.models import Book

    result = await db.execute(
        select(Book.format, func.count(Book.id))
        .where(Book.is_hidden == False)
        .group_by(Book.format)
        .order_by(func.count(Book.id).desc())
    )
    return [{"format": row[0], "book_count": row[1]} for row in result.all()]


# ============================================
# HIDDEN BOOKS ENDPOINTS
# ============================================

@router.post("/books/{book_id}/hide")
async def toggle_book_hidden(
    book_id: int,
    request: dict = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Toggle book hidden status. Requires password verification."""
    from app.repositories import BookRepository, SettingsRepository
    from app.security import verify_password as check_password

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")

    if not stored:
        raise HTTPException(status_code=400, detail="No password set. Set a password first.")

    password = (request or {}).get("password", "")
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    if not check_password(password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password")

    repo = BookRepository(db)
    book = await repo.get_by_id_or_404(book_id)

    book.is_hidden = not book.is_hidden
    await db.commit()
    return {"is_hidden": book.is_hidden, "message": "Book hidden" if book.is_hidden else "Book unhidden"}


@router.get("/hidden/status")
async def get_hidden_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Check if hidden books password is set."""
    from app.repositories import SettingsRepository

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")
    return {"password_set": stored is not None and bool(stored)}


@router.post("/hidden/set-password")
async def set_hidden_password(
    request: dict,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Set or update the hidden books password."""
    from app.repositories import SettingsRepository
    from app.security import encrypt_password

    password = request.get("password")
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    encrypted = encrypt_password(password)
    settings = SettingsRepository(db)
    await settings.set("hidden_password", encrypted)
    await db.commit()
    return {"message": "Password set successfully"}


@router.post("/hidden/verify-password")
async def verify_hidden_password(
    request: dict,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Verify the hidden books password."""
    from app.repositories import SettingsRepository
    from app.security import verify_password as check_password

    password = request.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")
    if not stored:
        raise HTTPException(status_code=400, detail="No password set")

    if not check_password(password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password")

    return {"verified": True}


@router.post("/hidden/reset-password")
async def reset_hidden_password(
    request: dict,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Reset hidden books password. Requires current password."""
    from app.repositories import SettingsRepository
    from app.security import verify_password as check_password

    password = request.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Current password required")

    settings = SettingsRepository(db)
    stored = await settings.get("hidden_password")
    if not stored:
        raise HTTPException(status_code=400, detail="No password set")

    if not check_password(password, stored):
        raise HTTPException(status_code=401, detail="Incorrect password")

    await settings.delete("hidden_password")
    await db.commit()
    return {"message": "Password reset successfully"}


@router.post("/books/{book_id}/auto-categorize")
async def auto_categorize_book(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Auto-categorize a single book using hybrid rule-based + AI approach."""
    from app.repositories import BookRepository
    from app.services.categorization_service import CategorizationService

    repo = BookRepository(db)
    book = await repo.get_by_id_or_404(book_id)

    cat_service = CategorizationService(db)
    return await cat_service.auto_categorize(book)


@router.post("/library/auto-categorize-all")
async def auto_categorize_all(db: AsyncSession = Depends(get_db)) -> dict:
    """Auto-categorize all books in the library."""
    from app.services.categorization_service import CategorizationService

    cat_service = CategorizationService(db)
    result = await cat_service.auto_categorize_all()
    return result


@router.get("/library/auto-categorize-stream")
async def auto_categorize_stream(db: AsyncSession = Depends(get_db)):
    """SSE stream for real-time categorization progress."""
    from app.services.categorization_service import CategorizationService
    from app.models import Book
    from sqlalchemy import select

    async def generate():
        cat_service = CategorizationService(db)
        db_result = await db.execute(select(Book))
        books = list(db_result.scalars().all())
        total = len(books)
        categorized = 0
        categories_added = 0

        yield f"data: {json.dumps({'type': 'start', 'total': total})}\n\n"

        for i, book in enumerate(books):
            try:
                result = await cat_service.ai_categorize(book)
                added = result.get("categories_added", 0)
                cats = result.get("categories", [])
                categorized += 1 if added > 0 else 0
                categories_added += added

                yield f"data: {json.dumps({
                    'type': 'progress',
                    'current': i + 1,
                    'total': total,
                    'book': book.title,
                    'categories': cats,
                    'categories_added': added,
                    'running_categorized': categorized,
                    'running_total_added': categories_added,
                })}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({
                    'type': 'error',
                    'current': i + 1,
                    'total': total,
                    'book': book.title,
                    'error': str(e),
                })}\n\n"

            await asyncio.sleep(0)

        yield f"data: {json.dumps({
            'type': 'done',
            'total': total,
            'categorized': categorized,
            'categories_added': categories_added,
        })}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
