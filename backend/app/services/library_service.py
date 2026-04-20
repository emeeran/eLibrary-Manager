"""Library management service.

Coordinates between repositories, scanner, and business logic
for library operations.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.logging_config import get_logger
from app.models import Book
from app.repositories import BookRepository
from app.scanner import LibraryScanner
from app.schemas import BookUpdate
from app.storage.factory import get_storage_backend

logger = get_logger(__name__)


class LibraryService:
    """Service for library management operations.

    Coordinates between repositories, scanner, and business logic.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            session: Database session
        """
        self.session = session
        self.book_repo = BookRepository(session)
        self.scanner = LibraryScanner()

    async def scan_and_import(
        self,
        directory: Optional[str] = None,
        scan_id: Optional[str] = None,
    ) -> dict:
        """Scan library directory and import new books.

        If NAS is enabled and healthy, scans both local and NAS directories.

        Args:
            directory: Directory to scan
            scan_id: Optional scan ID for progress tracking

        Returns:
            Dictionary with import statistics
        """
        logger.info("Starting library import")

        # Scan local library
        local_stats = await self._scan_source(
            scanner=self.scanner,
            directory=directory,
            scan_id=scan_id,
        )

        # Scan NAS if enabled
        config = get_config()
        nas_stats: dict | None = None
        if config.nas_enabled and config.nas_mount_path:
            nas_storage = get_storage_backend("nas")
            health = await nas_storage.health_check()
            if health["healthy"]:
                nas_scanner = LibraryScanner(
                    storage=nas_storage,
                    storage_type="nas",
                )
                nas_stats = await self._scan_source(
                    scanner=nas_scanner,
                    directory=config.nas_mount_path,
                )
            else:
                logger.warning(f"NAS not available: {health['details']}")
                nas_stats = {"imported": 0, "skipped": 0, "errors": 0, "total": 0, "unavailable": True}

        result = {"local": local_stats}
        if nas_stats is not None:
            result["nas"] = nas_stats
        return result

    async def fast_index(
        self,
        directory: Optional[str] = None,
        scan_id: Optional[str] = None,
    ) -> dict:
        """Fast-index library directory — filename-based metadata, no file opening.

        Ideal for large NAS collections (thousands of books).  Full metadata
        and covers are extracted on-demand when a book is first opened.

        Args:
            directory: Directory to scan.
            scan_id: Optional scan ID for progress tracking.

        Returns:
            Dictionary with import statistics.
        """
        import asyncio

        logger.info("Starting fast library index")

        # Build progress callback for the scanner
        progress_cb = None
        if scan_id:
            from app.scan_progress import scan_store

            async def progress_cb(count: int, filename: str) -> None:
                scan_store.update(
                    scan_id,
                    processed=count,
                    current_file=filename,
                    message=f"Scanning: {count} files found",
                )

        scanner = self.scanner
        books_data = await scanner.fast_index_directory(directory, progress_callback=progress_cb)

        if scan_id:
            from app.scan_progress import scan_store
            scan_store.update(scan_id, total_found=len(books_data))

        # Load all existing paths in one query for O(1) lookup
        from sqlalchemy import select
        from app.models import Book as BookModel
        result = await self.session.execute(select(BookModel.path))
        existing_paths = {row[0] for row in result.all()}
        logger.info(f"Found {len(existing_paths)} existing books in DB")

        imported = 0
        skipped = 0
        errors = 0
        batch_count = 0

        for i, book_data in enumerate(books_data):
            try:
                if book_data.path in existing_paths:
                    skipped += 1
                    continue

                # Extract cover for new books
                cover_path = await scanner.extract_cover(book_data.path)
                if cover_path:
                    book_data.cover_path = cover_path

                await self.book_repo.create(book_data)
                existing_paths.add(book_data.path)
                imported += 1
                batch_count += 1

                # Commit in batches of 100
                if batch_count >= 100:
                    await self.session.commit()
                    batch_count = 0
                    await asyncio.sleep(0)

            except Exception as e:
                errors += 1
                logger.error(f"Failed to index {book_data.path}: {e}")

            if scan_id and i % 50 == 0:
                scan_store.update(
                    scan_id,
                    processed=i + 1,
                    imported=imported,
                    skipped=skipped,
                    errors=errors,
                    current_file=book_data.path.split("/")[-1] if book_data.path else "",
                )

        # Final commit
        if batch_count > 0:
            await self.session.commit()

        logger.info(
            f"Fast index complete: {imported} added, {skipped} skipped, {errors} errors"
        )

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total": len(books_data),
        }

    async def _scan_source(
        self,
        scanner: LibraryScanner,
        directory: Optional[str] = None,
        scan_id: Optional[str] = None,
    ) -> dict:
        """Scan a single source directory and import books.

        Args:
            scanner: Configured scanner instance.
            directory: Directory to scan.
            scan_id: Optional scan ID for progress tracking.

        Returns:
            Dictionary with import statistics.
        """
        books_data = await scanner.scan_directory(directory)

        if scan_id:
            from app.scan_progress import scan_store
            scan_store.update(scan_id, total_found=len(books_data))

        imported = 0
        skipped = 0
        errors = 0

        for i, book_data in enumerate(books_data):
            try:
                existing = await self.book_repo.get_by_path(book_data.path)
                if existing:
                    skipped += 1
                    logger.debug(f"Skipping existing book: {book_data.title}")
                    continue

                cover_path = await scanner.extract_cover(book_data.path)
                if cover_path:
                    book_data.cover_path = cover_path

                await self.book_repo.create(book_data)
                imported += 1
                logger.info(f"Imported: {book_data.title}")

            except Exception as e:
                errors += 1
                logger.error(f"Failed to import {book_data.path}: {e}")

            if scan_id and i % 10 == 0:
                scan_store.update(
                    scan_id,
                    processed=i + 1,
                    imported=imported,
                    skipped=skipped,
                    errors=errors,
                    current_file=book_data.path.split("/")[-1] if book_data.path else "",
                )

        logger.info(
            f"Import complete: {imported} added, {skipped} skipped, {errors} errors"
        )

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total": len(books_data)
        }

    async def import_book(self, file_path: str) -> Book:
        """Import a single book file.

        Args:
            file_path: Absolute path to book file

        Returns:
            Imported Book instance or existing one

        Raises:
            LibraryScannerError: If file not supported or scan fails
        """
        book_data = await self.scanner.extract_metadata(file_path)

        existing = await self.book_repo.get_by_path(book_data.path)
        if existing:
            logger.info(f"Book already exists: {book_data.title}")
            return existing

        cover_path = await self.scanner.extract_cover(book_data.path)
        if cover_path:
            book_data.cover_path = cover_path

        book = await self.book_repo.create(book_data)
        logger.info(f"Imported book: {book.title}")

        # Auto-categorize if subjects extracted
        if hasattr(book_data, 'subjects') and book_data.subjects:
            from app.services.categorization_service import CategorizationService
            cat_service = CategorizationService(self.session)
            await cat_service.rule_based_categorize(book, book_data.subjects)

        return book

    async def get_book(self, book_id: int) -> Book:
        """Get a book by ID.

        Args:
            book_id: Book primary key

        Returns:
            Book instance

        Raises:
            ResourceNotFoundError: If book not found
        """
        book = await self.book_repo.get_by_id_or_404(book_id)
        book.last_read_date = datetime.utcnow()
        await self.session.flush()
        return book

    async def list_books(
        self,
        page: int = 1,
        page_size: int = 20,
        favorite_only: bool = False,
        recent_only: bool = False,
        search: Optional[str] = None,
        format_filter: Optional[str] = None,
        sort_by: str = "added_date",
        sort_order: str = "desc",
        source_filter: Optional[str] = None,
        category_id: Optional[int] = None,
        hidden_only: bool = False,
        show_hidden: bool = False,
        directory_filter: Optional[str] = None,
    ) -> tuple[list[Book], int]:
        """List books with pagination, filters, and sorting."""
        skip = (page - 1) * page_size

        return await self.book_repo.list_with_count(
            skip=skip,
            limit=page_size,
            favorite_only=favorite_only,
            recent_only=recent_only,
            search=search,
            format_filter=format_filter,
            sort_by=sort_by,
            sort_order=sort_order,
            source_filter=source_filter,
            category_id=category_id,
            hidden_only=hidden_only,
            show_hidden=show_hidden,
            directory_filter=directory_filter,
        )

    async def update_book(self, book_id: int, update_data: BookUpdate) -> Book:
        """Update book metadata.

        Args:
            book_id: Book primary key
            update_data: Update data

        Returns:
            Updated Book instance
        """
        return await self.book_repo.update(book_id, update_data)

    async def delete_book(self, book_id: int) -> None:
        """Delete a book.

        Args:
            book_id: Book primary key
        """
        await self.book_repo.delete(book_id)
        logger.info(f"Book deleted: {book_id}")

    async def get_library_stats(self) -> dict:
        """Get library statistics using aggregate queries."""
        from sqlalchemy import func, select
        from app.models import Book

        result = await self.session.execute(
            select(
                func.count(Book.id),
                func.count().filter(Book.is_favorite == True),
                func.count().filter(Book.is_recent == True),
                func.count().filter(Book.progress > 0),
                func.coalesce(func.sum(Book.file_size), 0),
                func.count().filter(Book.is_hidden == True),
            )
        )
        row = result.one()

        return {
            "total_books": row[0] or 0,
            "favorite_books": row[1] or 0,
            "recent_books": row[2] or 0,
            "reading_books": row[3] or 0,
            "total_size_bytes": row[4] or 0,
            "deleted_books": 0,
            "hidden_books": row[5] or 0,
        }

    async def refresh_covers(self, force: bool = False) -> dict:
        """Re-extract covers for books missing them or all books if forced.

        Args:
            force: If True, re-extract all covers. If False, only missing ones.

        Returns:
            Dictionary with refresh statistics
        """
        all_books = await self.book_repo.list_all(limit=10000)
        updated = 0
        skipped = 0
        errors = []

        for book in all_books:
            # Skip if book already has cover and not forcing
            if book.cover_path and not force:
                skipped += 1
                continue

            try:
                cover_path = await self.scanner.extract_cover(book.path)
                if cover_path:
                    book.cover_path = cover_path
                    await self.session.flush()
                    updated += 1
                    logger.info(f"Updated cover for: {book.title}")
                else:
                    skipped += 1
            except Exception as e:
                errors.append({"book_id": book.id, "error": str(e)})
                logger.warning(f"Failed to extract cover for {book.title}: {e}")

        await self.session.commit()
        return {
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "total": len(all_books)
        }
