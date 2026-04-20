"""Reader routes for chapter content, bookmarks, notes, and annotations."""

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import ResourceNotFoundError
from app.schemas import (
    AnnotationCreate,
    AnnotationResponse,
    AnnotationsResponse,
    BookmarkCreate,
    BookmarkResponse,
    BookmarksResponse,
    NoteCreate,
    NoteResponse,
    NotesResponse,
    TOCResponse,
)
from app.services import LibraryService, ReaderService

router = APIRouter(prefix="/api", tags=["reader"])


async def _check_nas_available(book, request: Request) -> JSONResponse | None:
    """Check if a NAS-sourced book is accessible.

    Returns a JSONResponse error if NAS is offline, or None if OK.
    """
    if getattr(book, "storage_type", "local") != "nas":
        return None

    nas_backend = getattr(request.app.state, "nas_backend", None)
    if nas_backend and nas_backend.is_healthy:
        return None

    # NAS is offline — check offline cache
    from app.nas_cache import get_nas_cache
    cache = get_nas_cache()
    if cache and await cache.get(book.path):
        return None  # Available from cache

    return JSONResponse(
        status_code=503,
        content={
            "error": "NAS Offline",
            "message": "The NAS is currently unreachable and this book is not cached locally. "
                       "Connect to your network or make the book available offline first.",
            "storage_type": "nas",
        },
    )


@router.get("/books/{book_id}/chapter/{chapter_index}")
async def get_chapter(
    book_id: int,
    chapter_index: int,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get chapter content.

    Args:
        book_id: Book primary key
        chapter_index: Zero-based chapter index
        request: FastAPI request (for NAS health check)
        response: FastAPI response object
        db: Database session

    Returns:
        Chapter content dictionary
    """
    service = ReaderService(db)

    # NAS availability check
    from app.repositories import BookRepository
    book = await BookRepository(db).get_by_id(book_id)
    if book:
        nas_error = await _check_nas_available(book, request)
        if nas_error:
            return nas_error

    content, title, total = await service.get_chapter_content(
        book_id, chapter_index
    )

    # Auto-cache NAS books for offline access
    if book and getattr(book, "storage_type", "local") == "nas":
        from app.nas_cache import get_nas_cache
        cache = get_nas_cache()
        if cache:
            await cache.ensure_cached(book.path)

    # Estimate page count from content length
    from app.reader_engine import ReaderEngine
    estimated_pages = ReaderEngine.estimate_chapter_pages(content)

    # Aggressive caching for chapter content (1 hour)
    response.headers["Cache-Control"] = "public, max-age=3600, immutable"
    response.headers["ETag"] = f'"book-{book_id}-ch-{chapter_index}"'

    return {
        "content": content,
        "title": title,
        "total_chapters": total,
        "current_chapter": chapter_index,
        "estimated_pages": estimated_pages
    }


@router.get("/books/{book_id}/page-image/{page_index}")
async def get_page_image(
    book_id: int,
    page_index: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Render a PDF page as an image for faithful layout reproduction.

    Args:
        book_id: Book primary key.
        page_index: Zero-based page index.
        request: FastAPI request (for NAS health check).
        db: Database session.

    Returns:
        Dictionary with image URL.
    """
    from app.repositories import BookRepository

    repo = BookRepository(db)
    book = await repo.get_by_id(book_id)
    if not book:
        raise ResourceNotFoundError("Book not found", {"book_id": book_id})

    nas_error = await _check_nas_available(book, request)
    if nas_error:
        return nas_error

    from app.parsers import PDFParser
    from app.config import get_config
    config = get_config()
    parser = PDFParser(
        covers_path=config.covers_path,
        book_images_path=config.book_images_path,
    )
    image_url = await parser.render_page_as_image(book.path, page_index)
    if not image_url:
        raise ResourceNotFoundError(
            f"Page {page_index} not found",
            {"book_id": book_id, "page_index": page_index}
        )

    return {"image_url": image_url}


@router.get("/books/{book_id}/chapters")
async def get_batch_chapters(
    book_id: int,
    start: int = 0,
    end: int = 5,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get multiple chapters in a single request for continuous scroll.

    Args:
        book_id: Book primary key.
        start: Start chapter index (inclusive).
        end: End chapter index (exclusive).
        db: Database session.

    Returns:
        Dictionary with list of chapters.
    """
    from app.reader_engine import ReaderEngine

    service_obj = ReaderService(db)
    # Get book path
    from app.repositories import BookRepository
    repo = BookRepository(db)
    book = await repo.get_by_id(book_id)
    if not book:
        raise ResourceNotFoundError("Book not found", {"book_id": book_id})

    engine = ReaderEngine()
    chapters_data = []
    for idx in range(start, min(end, 100)):  # Cap at 100 chapters per request
        try:
            content, title, total = await engine.get_chapter_content(
                book.path, idx
            )
            from app.reader_engine import ReaderEngine as RE
            chapters_data.append({
                "index": idx,
                "title": title,
                "content": content,
                "estimated_pages": RE.estimate_chapter_pages(content)
            })
        except Exception:
            break

    return {
        "chapters": chapters_data,
        "total_chapters": total if chapters_data else 0
    }


@router.get("/books/{book_id}/summary/{chapter_index}")
async def get_summary(
    book_id: int,
    chapter_index: int,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get chapter summary.

    Args:
        book_id: Book primary key
        chapter_index: Chapter index
        refresh: Force regeneration
        db: Database session

    Returns:
        Summary dictionary
    """
    service = ReaderService(db)
    summary = await service.get_chapter_summary(
        book_id, chapter_index, force_refresh=refresh
    )

    return {
        "summary": summary.summary_text,
        "provider": summary.provider,
        "created_at": summary.created_at.isoformat()
    }


@router.get("/books/{book_id}/summary")
async def get_book_summary(
    book_id: int,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get entire book summary.

    Args:
        book_id: Book primary key
        refresh: Force regeneration
        db: Database session

    Returns:
        Book summary dictionary
    """
    service = ReaderService(db)
    summary = await service.get_book_summary(
        book_id, force_refresh=refresh
    )

    return {
        "summary": summary.summary_text,
        "provider": summary.provider,
        "created_at": summary.created_at.isoformat()
    }


@router.get("/books/{book_id}/toc", response_model=TOCResponse)
async def get_table_of_contents(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> TOCResponse:
    """Get table of contents for a book.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        Table of contents with chapters
    """
    service = ReaderService(db)
    toc_items = await service.get_table_of_contents(book_id)
    book = await LibraryService(db).get_book(book_id)

    # Use stored total, or derive from the maximum TOC index + 1
    total = book.total_chapters
    if not total and toc_items:
        # For PDFs where total_chapters wasn't stored, derive from TOC indices
        max_idx = max(item["index"] for item in toc_items)
        total = max_idx + 1

    return TOCResponse(items=toc_items, total_chapters=total)


# ============================================
# BOOKMARK ENDPOINTS
# ============================================

@router.get("/books/{book_id}/bookmarks", response_model=BookmarksResponse)
async def list_bookmarks(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> BookmarksResponse:
    """List all bookmarks for a book.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        List of bookmarks
    """
    service = ReaderService(db)
    bookmarks = await service.list_bookmarks(book_id)
    return BookmarksResponse(
        bookmarks=[BookmarkResponse.model_validate(b) for b in bookmarks]
    )


@router.post("/books/{book_id}/bookmarks", response_model=BookmarkResponse)
async def create_bookmark(
    book_id: int,
    bookmark_data: BookmarkCreate,
    db: AsyncSession = Depends(get_db)
) -> BookmarkResponse:
    """Create a new bookmark.

    Args:
        book_id: Book primary key
        bookmark_data: Bookmark data
        db: Database session

    Returns:
        Created bookmark
    """
    service = ReaderService(db)
    bookmark = await service.create_bookmark(
        book_id=book_id,
        chapter_index=bookmark_data.chapter_index,
        position_in_chapter=bookmark_data.position_in_chapter,
        title=bookmark_data.title,
        notes=bookmark_data.notes
    )
    return BookmarkResponse.model_validate(bookmark)


@router.delete("/bookmarks/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Delete a bookmark.

    Args:
        bookmark_id: Bookmark primary key
        db: Database session

    Returns:
        Success message
    """
    service = ReaderService(db)
    await service.delete_bookmark(bookmark_id)
    return {"message": "Bookmark deleted successfully"}


@router.get("/bookmarks/{bookmark_id}/jump")
async def jump_to_bookmark(
    bookmark_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get bookmark data for navigation.

    Args:
        bookmark_id: Bookmark primary key
        db: Database session

    Returns:
        Bookmark navigation data
    """
    service = ReaderService(db)
    bookmark = await service.get_bookmark(bookmark_id)
    return {
        "chapter_index": bookmark.chapter_index,
        "position_in_chapter": bookmark.position_in_chapter
    }


# ============================================
# NOTE ENDPOINTS
# ============================================

@router.get("/books/{book_id}/notes", response_model=NotesResponse)
async def list_notes(
    book_id: int,
    db: AsyncSession = Depends(get_db)
) -> NotesResponse:
    """List all notes for a book.

    Args:
        book_id: Book primary key
        db: Database session

    Returns:
        List of notes
    """
    service = ReaderService(db)
    notes = await service.list_notes(book_id)
    return NotesResponse(
        notes=[NoteResponse.model_validate(n) for n in notes]
    )


@router.post("/books/{book_id}/notes", response_model=NoteResponse)
async def create_note(
    book_id: int,
    note_data: NoteCreate,
    db: AsyncSession = Depends(get_db)
) -> NoteResponse:
    """Create a new note.

    Args:
        book_id: Book primary key
        note_data: Note data
        db: Database session

    Returns:
        Created note
    """
    service = ReaderService(db)
    note = await service.create_note(
        book_id=book_id,
        chapter_index=note_data.chapter_index,
        position_in_chapter=note_data.position_in_chapter,
        content=note_data.content,
        color=note_data.color,
        quoted_text=note_data.quoted_text
    )
    return NoteResponse.model_validate(note)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Delete a note.

    Args:
        note_id: Note primary key
        db: Database session

    Returns:
        Success message
    """
    service = ReaderService(db)
    await service.delete_note(note_id)
    return {"message": "Note deleted successfully"}


# ============================================
# ANNOTATION ENDPOINTS
# ============================================

@router.get("/books/{book_id}/annotations", response_model=AnnotationsResponse)
async def list_annotations(
    book_id: int,
    chapter_index: int | None = None,
    db: AsyncSession = Depends(get_db)
) -> AnnotationsResponse:
    """List annotations for a book.

    Args:
        book_id: Book primary key
        chapter_index: Optional chapter filter
        db: Database session

    Returns:
        List of annotations
    """
    service = ReaderService(db)
    annotations = await service.list_annotations(book_id, chapter_index)
    return AnnotationsResponse(
        annotations=[AnnotationResponse.model_validate(a) for a in annotations]
    )


@router.post("/books/{book_id}/annotations", response_model=AnnotationResponse)
async def create_annotation(
    book_id: int,
    annotation_data: AnnotationCreate,
    db: AsyncSession = Depends(get_db)
) -> AnnotationResponse:
    """Create a new annotation.

    Args:
        book_id: Book primary key
        annotation_data: Annotation data
        db: Database session

    Returns:
        Created annotation
    """
    service = ReaderService(db)
    annotation = await service.create_annotation(
        book_id=book_id,
        chapter_index=annotation_data.chapter_index,
        start_position=annotation_data.start_position,
        end_position=annotation_data.end_position,
        text=annotation_data.text,
        color=annotation_data.color,
        note=annotation_data.note
    )
    return AnnotationResponse.model_validate(annotation)


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: int,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Delete an annotation.

    Args:
        annotation_id: Annotation primary key
        db: Database session

    Returns:
        Success message
    """
    service = ReaderService(db)
    await service.delete_annotation(annotation_id)
    return {"message": "Annotation deleted successfully"}
