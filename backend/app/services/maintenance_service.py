"""Service for library maintenance and cleanup operations."""

import asyncio
import os
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_manager
from app.logging_config import get_logger
from app.models import (
    Annotation,
    Book,
    BookCategory,
    Bookmark,
    BookSummary,
    ChapterSummary,
    Note,
)
from app.repositories import BookRepository
from app.schemas import (
    BulkDeleteResult,
    DuplicateBookItem,
    DuplicateDedupResult,
    DuplicateGroup,
    FKStatusResponse,
    MaintenanceSummary,
    OrphanDeleteResult,
    OrphansReport,
    StaleBookItem,
    VacuumResult,
)

logger = get_logger(__name__)

BATCH_SIZE = 100


class MaintenanceService:
    """Service for library maintenance and cleanup operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.book_repo = BookRepository(session)

    # ---- Stale Books ----

    async def detect_stale_books(
        self, page: int = 1, page_size: int = 50
    ) -> tuple[list[StaleBookItem], int]:
        """Detect books whose files are missing from disk."""
        stale_ids = await self.book_repo.get_stale_book_ids()
        total = len(stale_ids)

        # Paginate IDs
        start = (page - 1) * page_size
        page_ids = stale_ids[start : start + page_size]

        if not page_ids:
            return [], total

        books = await self.book_repo.get_books_by_ids(page_ids)
        id_order = {bid: i for i, bid in enumerate(page_ids)}
        books.sort(key=lambda b: id_order.get(b.id, 999))

        items = [
            StaleBookItem(
                id=b.id,
                title=b.title,
                author=b.author,
                path=b.path,
                format=b.format,
                file_size=b.file_size,
            )
            for b in books
        ]
        return items, total

    async def purge_stale_books(
        self,
        dry_run: bool = True,
        progress_callback: Callable | None = None,
    ) -> BulkDeleteResult:
        """Delete all books with missing files, cascading to children."""
        stale_ids = await self.book_repo.get_stale_book_ids()

        if dry_run:
            return BulkDeleteResult(
                dry_run=True,
                books_deleted=len(stale_ids),
                message=f"Would delete {len(stale_ids)} stale books",
            )

        totals = {
            "books": 0,
            "chapter_summaries": 0,
            "book_summaries": 0,
            "bookmarks": 0,
            "notes": 0,
            "annotations": 0,
            "book_categories": 0,
            "errors": 0,
        }
        batch_count = 0

        for i, book_id in enumerate(stale_ids):
            try:
                counts = await self._delete_book_cascade(book_id)
                for k, v in counts.items():
                    totals[k] += v
                totals["books"] += 1
                batch_count += 1

                if batch_count >= BATCH_SIZE:
                    await self.session.commit()
                    batch_count = 0
                    await asyncio.sleep(0)
            except Exception as e:
                totals["errors"] += 1
                logger.error(f"Failed to delete stale book {book_id}: {e}")

            if progress_callback:
                await progress_callback(i + 1, len(stale_ids))

        if batch_count > 0:
            await self.session.commit()

        return BulkDeleteResult(
            dry_run=False,
            books_deleted=totals["books"],
            chapter_summaries_deleted=totals["chapter_summaries"],
            book_summaries_deleted=totals["book_summaries"],
            bookmarks_deleted=totals["bookmarks"],
            notes_deleted=totals["notes"],
            annotations_deleted=totals["annotations"],
            book_categories_deleted=totals["book_categories"],
            errors=totals["errors"],
            message=f"Deleted {totals['books']} stale books",
        )

    # ---- Duplicates ----

    async def detect_duplicates(
        self, page: int = 1, page_size: int = 50
    ) -> tuple[list[DuplicateGroup], int, int]:
        """Find groups of books with the same title+author (case-insensitive)."""
        raw_groups = await self.book_repo.find_duplicate_groups()
        total_groups = len(raw_groups)
        total_extra = sum(g["count"] - 1 for g in raw_groups)

        # Paginate groups
        start = (page - 1) * page_size
        page_groups = raw_groups[start : start + page_size]

        groups: list[DuplicateGroup] = []
        for g in page_groups:
            books = await self.book_repo.get_books_by_ids(g["ids"])
            # Check file existence in a thread to avoid blocking
            book_paths = {b.id: b.path for b in books}
            exists_map = await asyncio.to_thread(
                lambda bp=book_paths: {bid: os.path.exists(p) for bid, p in bp.items()}
            )
            copies = [
                DuplicateBookItem(
                    id=b.id,
                    path=b.path,
                    format=b.format,
                    file_size=b.file_size,
                    file_exists=exists_map[b.id],
                )
                for b in books
            ]
            best_id, reason = self._select_best_copy(books, exists_map)
            groups.append(
                DuplicateGroup(
                    title=g["title"],
                    author=g["author"],
                    copies=copies,
                    recommended_keep_id=best_id,
                    recommended_keep_reason=reason,
                )
            )

        return groups, total_groups, total_extra

    async def dedup_books(
        self,
        dry_run: bool = True,
        progress_callback: Callable | None = None,
    ) -> DuplicateDedupResult:
        """Remove duplicate books, keeping the best copy in each group."""
        raw_groups = await self.book_repo.find_duplicate_groups()

        ids_to_remove: list[int] = []
        books_kept = 0

        for g in raw_groups:
            books = await self.book_repo.get_books_by_ids(g["ids"])
            # Check file existence in a thread to avoid blocking
            book_paths = {b.id: b.path for b in books}
            exists_map = await asyncio.to_thread(
                lambda bp=book_paths: {bid: os.path.exists(p) for bid, p in bp.items()}
            )
            best_id, _ = self._select_best_copy(books, exists_map)
            books_kept += 1
            for b in books:
                if b.id != best_id:
                    ids_to_remove.append(b.id)

        if dry_run:
            return DuplicateDedupResult(
                dry_run=True,
                books_deleted=len(ids_to_remove),
                duplicate_groups_processed=len(raw_groups),
                books_kept=books_kept,
                books_removed=len(ids_to_remove),
                message=f"Would remove {len(ids_to_remove)} duplicates across {len(raw_groups)} groups",
            )

        totals = {
            "chapter_summaries": 0,
            "book_summaries": 0,
            "bookmarks": 0,
            "notes": 0,
            "annotations": 0,
            "book_categories": 0,
            "errors": 0,
        }
        batch_count = 0

        for i, book_id in enumerate(ids_to_remove):
            try:
                counts = await self._delete_book_cascade(book_id)
                for k, v in counts.items():
                    totals[k] += v
                batch_count += 1

                if batch_count >= BATCH_SIZE:
                    await self.session.commit()
                    batch_count = 0
                    await asyncio.sleep(0)
            except Exception as e:
                totals["errors"] += 1
                logger.error(f"Failed to delete duplicate book {book_id}: {e}")

            if progress_callback:
                await progress_callback(i + 1, len(ids_to_remove))

        if batch_count > 0:
            await self.session.commit()

        return DuplicateDedupResult(
            dry_run=False,
            books_deleted=len(ids_to_remove),
            chapter_summaries_deleted=totals["chapter_summaries"],
            book_summaries_deleted=totals["book_summaries"],
            bookmarks_deleted=totals["bookmarks"],
            notes_deleted=totals["notes"],
            annotations_deleted=totals["annotations"],
            book_categories_deleted=totals["book_categories"],
            errors=totals["errors"],
            duplicate_groups_processed=len(raw_groups),
            books_kept=books_kept,
            books_removed=len(ids_to_remove),
            message=f"Removed {len(ids_to_remove)} duplicates from {len(raw_groups)} groups",
        )

    # ---- Orphans ----

    async def detect_orphans(self) -> OrphansReport:
        """Find child records whose book_id does not exist in the books table."""
        book_ids_subq = select(Book.id)

        async def _count(model: Any, col: str = "book_id") -> int:
            result = await self.session.execute(
                select(func.count())
                .select_from(model)
                .where(getattr(model, col).not_in(book_ids_subq))
            )
            return result.scalar() or 0

        return OrphansReport(
            orphaned_bookmarks=await _count(Bookmark),
            orphaned_notes=await _count(Note),
            orphaned_annotations=await _count(Annotation),
            orphaned_chapter_summaries=await _count(ChapterSummary),
            orphaned_book_summaries=await _count(BookSummary),
            orphaned_book_categories=await _count(BookCategory, "book_id"),
        )

    async def purge_orphans(self, dry_run: bool = True) -> OrphanDeleteResult:
        """Delete orphaned child records."""
        book_ids_subq = select(Book.id)

        async def _delete_orphans(model: Any, col: str = "book_id") -> int:
            stmt = (
                sql_delete(model)
                .where(getattr(model, col).not_in(book_ids_subq))
                .returning(model.id)
            )
            result = await self.session.execute(stmt)
            return len(result.all())

        if dry_run:
            report = await self.detect_orphans()
            return OrphanDeleteResult(
                dry_run=True,
                bookmarks_deleted=report.orphaned_bookmarks,
                notes_deleted=report.orphaned_notes,
                annotations_deleted=report.orphaned_annotations,
                chapter_summaries_deleted=report.orphaned_chapter_summaries,
                book_summaries_deleted=report.orphaned_book_summaries,
                book_categories_deleted=report.orphaned_book_categories,
            )

        result = OrphanDeleteResult(dry_run=False)
        result.bookmarks_deleted = await _delete_orphans(Bookmark)
        result.notes_deleted = await _delete_orphans(Note)
        result.annotations_deleted = await _delete_orphans(Annotation)
        result.chapter_summaries_deleted = await _delete_orphans(ChapterSummary)
        result.book_summaries_deleted = await _delete_orphans(BookSummary)
        result.book_categories_deleted = await _delete_orphans(BookCategory, "book_id")
        return result

    # ---- FK Enforcement ----

    async def get_fk_status(self) -> FKStatusResponse:
        """Check if PRAGMA foreign_keys is ON for the current connection."""
        result = await self.session.execute(text("PRAGMA foreign_keys"))
        val = result.scalar()
        enabled = val == 1
        return FKStatusResponse(
            foreign_keys_enabled=enabled,
            message="Foreign keys are enabled" if enabled else "Foreign keys are DISABLED",
        )

    # ---- VACUUM ----

    async def vacuum_database(self) -> VacuumResult:
        """Run VACUUM to compact the SQLite database."""
        db_path = db_manager.config.database_url.replace("sqlite+aiosqlite:///", "")
        size_before = os.path.getsize(db_path) if os.path.exists(db_path) else 0

        # VACUUM cannot run inside a transaction — use autocommit isolation level
        async with db_manager.engine.connect() as conn:
            await conn.execute(text("VACUUM"))
            await conn.commit()

        size_after = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        freed = size_before - size_after

        return VacuumResult(
            size_before_bytes=size_before,
            size_after_bytes=size_after,
            freed_bytes=freed,
            message=f"Freed {freed / (1024 * 1024):.1f} MB",
        )

    # ---- Summary ----

    async def get_maintenance_summary(self) -> MaintenanceSummary:
        """Quick counts for the maintenance dashboard."""
        total_books = await self.book_repo.count()

        # Stale count (filesystem check via optimized repo method)
        stale_ids = await self.book_repo.get_stale_book_ids()
        stale_count = len(stale_ids)

        # Duplicate count (DB only)
        raw_groups = await self.book_repo.find_duplicate_groups()
        extra_copies = sum(g["count"] - 1 for g in raw_groups)

        # Orphan count
        orphans = await self.detect_orphans()

        # FK status
        fk = await self.get_fk_status()

        # DB size
        db_path = db_manager.config.database_url.replace("sqlite+aiosqlite:///", "")
        db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0

        return MaintenanceSummary(
            total_books=total_books,
            stale_books_count=stale_count,
            duplicate_groups_count=len(raw_groups),
            extra_copies_count=extra_copies,
            orphaned_bookmarks=orphans.orphaned_bookmarks,
            orphaned_notes=orphans.orphaned_notes,
            orphaned_annotations=orphans.orphaned_annotations,
            foreign_keys_enabled=fk.foreign_keys_enabled,
            db_size_bytes=db_size,
        )

    # ---- Cover re-optimization ----

    async def reoptimize_covers(
        self,
        threshold_bytes: int = 300_000,
        progress_callback: "Callable[[int, int], object] | None" = None,
    ) -> dict:
        """Re-encode oversized cover images to the standard size/quality.

        Scans the covers directory for JPEGs larger than ``threshold_bytes``
        (default 300KB — the config cover ceiling) and re-encodes them at
        600x900 / q85. Covers already at that size are detailed images and are
        left alone; this targets genuinely bloated covers (e.g. legacy MOBI
        raw embedded images stored before the resize fix). Returns before/after
        byte totals so the caller can report freed space. Idempotent.
        """
        from pathlib import Path

        from app.config import get_config
        from app.parsers.image_service import optimize_cover_file

        config = get_config()
        covers_dir = Path(config.covers_path)
        if not covers_dir.is_dir():
            return {"optimized": 0, "bytes_before": 0, "bytes_after": 0, "freed": 0}

        # Gather candidate files (oversized JPEGs).
        candidates = [
            p
            for p in covers_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in (".jpg", ".jpeg")
            and p.stat().st_size > threshold_bytes
        ]
        total = len(candidates)
        bytes_before = sum(p.stat().st_size for p in candidates)

        optimized = 0
        bytes_after_total = 0
        for i, path in enumerate(candidates):
            # Run the (CPU-bound) PIL work in a thread to avoid blocking the loop.
            ok = await asyncio.to_thread(optimize_cover_file, path, path)
            if ok:
                optimized += 1
            bytes_after_total += path.stat().st_size
            if progress_callback:
                cb = progress_callback(i + 1, total)
                if asyncio.iscoroutine(cb):
                    await cb

        return {
            "optimized": optimized,
            "bytes_before": bytes_before,
            "bytes_after": bytes_after_total,
            "freed": max(0, bytes_before - bytes_after_total),
        }

    # ---- Internal helpers ----

    def _select_best_copy(
        self, books: list[Book], exists_map: dict[int, bool] | None = None
    ) -> tuple[int, str]:
        """Select the best book to keep from a duplicate group.

        Scoring:
            File exists:        +10000
            Has reading data:   +1000
            Format EPUB:        +100
            File size in KB:    +file_size / 1024
            Tiebreaker:         lowest id

        Args:
            books: List of Book instances in the duplicate group.
            exists_map: Optional precomputed {book_id: exists_bool} to avoid
                sync filesystem calls. Falls back to os.path.exists if not provided.

        Returns:
            Tuple of (best_book_id, reason_string)
        """
        best_id = None
        best_score = -1
        best_reason = ""

        for b in books:
            score = 0
            reasons = []

            if exists_map is not None:
                file_exists = exists_map.get(b.id, False)
            else:
                file_exists = os.path.exists(b.path)

            if file_exists:
                score += 10000
                reasons.append("file exists")
            else:
                reasons.append("file missing")

            if b.progress > 0:
                score += 1000
                reasons.append("has reading data")

            if b.format.upper() == "EPUB":
                score += 100
                reasons.append("EPUB format")

            score += b.file_size / 1024
            reasons.append(f"{b.file_size // 1024}KB")

            # Tiebreaker: prefer lower id
            if score == best_score and best_id is not None and b.id < best_id:
                best_id = b.id
                best_reason = ", ".join(reasons)
            elif score > best_score:
                best_score = score
                best_id = b.id
                best_reason = ", ".join(reasons)

        return best_id, best_reason

    async def _delete_book_cascade(self, book_id: int) -> dict[str, int]:
        """Explicitly delete a book and all its child records.

        Order: annotations → notes → bookmarks → chapter_summaries →
               book_summaries → book_categories → book
        """
        counts: dict[str, int] = {}

        for model, label in [
            (Annotation, "annotations"),
            (Note, "notes"),
            (Bookmark, "bookmarks"),
            (ChapterSummary, "chapter_summaries"),
            (BookSummary, "book_summaries"),
        ]:
            stmt = sql_delete(model).where(model.book_id == book_id).returning(model.id)
            result = await self.session.execute(stmt)
            counts[label] = len(result.all())

        # BookCategory is an association table (no `id` column)
        stmt = sql_delete(BookCategory).where(BookCategory.book_id == book_id)
        result = await self.session.execute(stmt)
        counts["book_categories"] = result.rowcount

        # Delete the book itself
        await self.session.execute(sql_delete(Book).where(Book.id == book_id))

        return counts
