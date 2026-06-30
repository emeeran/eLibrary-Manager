"""Reusable Calibre sync (spec 011 v1.2).

The single source of truth for importing/syncing a Calibre library into the
index, used by both the manual import route and the auto-scheduler. Performs an
incremental sync (new / changed / unchanged via ``books.last_modified``),
re-categorizes changed books from Calibre tags, and optionally soft-deletes
volumes that have vanished from the Calibre catalog.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models import Book
from app.repositories import BookRepository
from app.services.calibre_importer import CalibreImporter, CalibreImportSummary
from app.services.categorization_service import CategorizationService

logger = get_logger(__name__)


async def sync_library(
    session: AsyncSession,
    library_root: str,
    *,
    progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
    cancel_check: Callable[[], None] | None = None,
    prune_missing: bool = False,
) -> CalibreImportSummary:
    """Incrementally sync a Calibre library into the index.

    Args:
        session: DB session (caller commits).
        library_root: Path to the Calibre library (folder with metadata.db).
        progress_callback: ``async (processed, total, current_title)``.
        cancel_check: raises to abort cooperatively.
        prune_missing: soft-delete eLM Calibre books no longer in the catalog.

    Returns:
        Aggregate :class:`CalibreImportSummary`.
    """
    book_repo = BookRepository(session)

    # Load existing state once so per-volume resolution is O(1).
    rows = (
        await session.execute(
            select(Book.path, Book.calibre_id, Book.id, Book.calibre_last_modified)
        )
    ).all()
    existing_paths = {r[0] for r in rows if r[0]}
    calibre_state: dict[int, tuple[int, str | None]] = {
        r[1]: (r[2], r[3]) for r in rows if r[1] is not None
    }
    seen_calibre_ids: set[int] = set()

    importer = CalibreImporter(library_root)

    def _lookup(volume: Any) -> str:  # noqa: ANN401
        if volume.calibre_id is not None:
            seen_calibre_ids.add(volume.calibre_id)
        if volume.calibre_id is not None and volume.calibre_id in calibre_state:
            _, stored_lm = calibre_state[volume.calibre_id]
            if stored_lm is None or (
                volume.last_modified is not None and volume.last_modified != stored_lm
            ):
                return "changed"
            return "unchanged"
        if volume.file_path in existing_paths:
            return "unchanged"
        return "new"

    async def _commit_one(volume: Any, book_data: Any) -> None:  # noqa: ANN401
        book = await book_repo.create(book_data)
        book.calibre_last_modified = volume.last_modified
        if getattr(book_data, "subjects", None):
            await CategorizationService(session).rule_based_categorize(book, book_data.subjects)
        existing_paths.add(book_data.path)
        if volume.calibre_id is not None:
            calibre_state[volume.calibre_id] = (book.id, volume.last_modified)

    async def _update_one(volume: Any, book_data: Any) -> None:  # noqa: ANN401
        state = calibre_state.get(volume.calibre_id) if volume.calibre_id is not None else None
        if state is None:
            await _commit_one(volume, book_data)
            return
        book_id, _ = state
        book = await book_repo.get_by_id(book_id)
        if book is None:
            await _commit_one(volume, book_data)
            return
        # A previously-pruned volume that reappeared in Calibre: restore it.
        book.is_deleted = False
        book.title = book_data.title
        book.author = book_data.author
        book.publisher = book_data.publisher
        book.publish_date = book_data.publish_date
        book.description = book_data.description
        book.language = book_data.language
        book.isbn = book_data.isbn
        book.rating = book_data.rating
        book.series = book_data.series
        book.series_index = book_data.series_index
        if book_data.cover_path:
            book.cover_path = book_data.cover_path
        book.calibre_last_modified = volume.last_modified
        # Re-categorize from the (possibly changed) Calibre tags — idempotent.
        if getattr(book_data, "subjects", None):
            await CategorizationService(session).rule_based_categorize(book, book_data.subjects)
        calibre_state[volume.calibre_id] = (book_id, volume.last_modified)

    summary = await importer.import_library(
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        lookup_check=_lookup,
        commit_one=_commit_one,
        update_one=_update_one,
    )

    # Prune: soft-delete eLM Calibre books absent from the catalog.
    if prune_missing and seen_calibre_ids:
        pruned = (
            await session.execute(
                update(Book)
                .where(
                    Book.calibre_id.isnot(None),
                    ~Book.calibre_id.in_(seen_calibre_ids),
                    Book.is_deleted.is_(False),
                )
                .values(is_deleted=True)
            )
        ).rowcount or 0
        if pruned:
            logger.info("Calibre sync pruned %d vanished volume(s)", pruned)

    return summary


__all__ = ["sync_library"]
