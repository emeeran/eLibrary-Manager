"""Background content-index backfill (spec 012).

Extracts the full text of every book and indexes it in ``books_content_fts`` so
the library search box matches book CONTENT, not just title/author. Reuses the
scan-progress machinery (SSE + cooperative cancel) via the route wrapper.

The job is resumable: ``book_contents.extract_status`` is the checkpoint, so a
crash or cancel leaves a mix of ``extracted``/``pending`` and a restart picks up
the remaining ``pending`` books.

Extraction runs sequentially via ``asyncio.to_thread`` (correctness first); the
``extract_text`` function is module-level/picklable so a ``ProcessPoolExecutor``
can be swapped in later to parallelize across cores for very large libraries.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.repositories import BookContentRepository
from app.services.content_extractor import extract_text

logger = get_logger(__name__)


async def run_content_backfill(
    session: AsyncSession,
    *,
    batch_size: int = 50,
    progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Extract and index all pending books' content.

    Args:
        session: DB session (committed per batch).
        batch_size: Books processed before each commit (checkpoint cadence).
        progress_callback: ``async (processed, total_pending, current_path)``.
        cancel_check: raises (e.g. ``ScanCancelledError``) to abort cooperatively.

    Returns:
        Aggregate stats ``{extracted, empty, failed, total}``.
    """
    repo = BookContentRepository(session)
    await repo.seed_missing()
    counts = await repo.status_counts()
    total_pending = counts.get("pending", 0)

    extracted = empty = failed = 0
    processed = 0
    while True:
        if cancel_check:
            cancel_check()
        batch = await repo.pending_batch(batch_size)
        if not batch:
            break
        for book_id, path, fmt in batch:
            if cancel_check:
                cancel_check()
            try:
                text = await asyncio.to_thread(extract_text, path, fmt)
                if text.strip():
                    mtime = await asyncio.to_thread(_safe_mtime, path)
                    await repo.upsert_extracted(book_id, text, len(text), mtime)
                    extracted += 1
                else:
                    await repo.mark_status(book_id, "empty")
                    empty += 1
            except Exception as e:  # noqa: BLE001 — keep backfill running on per-book errors
                logger.warning("Content extract failed (book %s, %s): %s", book_id, path, e)
                await repo.mark_status(book_id, "failed")
                failed += 1
            processed += 1
            if progress_callback:
                await progress_callback(processed, total_pending, path)
        await session.commit()

    total = extracted + empty + failed
    logger.info(
        "Content backfill complete: %d extracted, %d empty, %d failed",
        extracted,
        empty,
        failed,
    )
    return {"extracted": extracted, "empty": empty, "failed": failed, "total": total}


def _safe_mtime(path: str) -> float | None:
    """File mtime for the content row (future re-extract trigger), or None."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


__all__ = ["run_content_backfill"]
