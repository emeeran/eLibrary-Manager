"""Background content-index backfill (spec 012).

Extracts the full text of every book and indexes it in ``books_content_fts`` so
the library search box matches book CONTENT, not just title/author. Reuses the
scan-progress machinery (SSE + cooperative cancel) via the route wrapper.

The job is resumable: ``book_contents.extract_status`` is the checkpoint, so a
crash or cancel leaves a mix of ``extracted``/``pending`` and a restart picks up
the remaining ``pending`` books.

Extraction is CPU-bound parsing, so each batch is fanned out across a
:class:`~concurrent.futures.ProcessPoolExecutor` (``extract_text`` is a
module-level pure function — picklable). DB writes stay sequential on the main
async thread to honour SQLite's single-writer constraint. Pass ``max_workers=1``
to force the sequential ``asyncio.to_thread`` path (used in tests).
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
from collections.abc import Awaitable, Callable
from concurrent.futures import ProcessPoolExecutor

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.repositories import BookContentRepository
from app.services.content_extractor import extract_text

logger = get_logger(__name__)

#: Default worker count for parallel extraction. Capped at 4 — parsing is
#: CPU-bound but the gains plateau and each worker holds a book's text in memory.
_DEFAULT_WORKERS = min(4, os.cpu_count() or 2)


async def run_content_backfill(
    session: AsyncSession,
    *,
    batch_size: int = 50,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Extract and index all pending books' content.

    Args:
        session: DB session (committed per batch).
        batch_size: Books processed before each commit (checkpoint cadence).
        max_workers: ProcessPool size for parallel extraction. ``None`` uses
            ``_DEFAULT_WORKERS``; ``1`` (or less) uses the sequential path.
        progress_callback: ``async (processed, total_pending, current_path)``.
        cancel_check: raises (e.g. ``ScanCancelledError``) to abort cooperatively.

    Returns:
        Aggregate stats ``{extracted, empty, failed, total}``.
    """
    repo = BookContentRepository(session)
    await repo.seed_missing()
    counts = await repo.status_counts()
    total_pending = counts.get("pending", 0)

    workers = max(1, max_workers or _DEFAULT_WORKERS)
    use_pool = workers > 1
    loop = asyncio.get_running_loop()
    # forkserver (not the default "fork") avoids forking the multi-threaded
    # async process, which can deadlock. Workers re-import modules to resolve
    # the picklable ``extract_text`` reference.
    pool = (
        ProcessPoolExecutor(
            max_workers=workers, mp_context=multiprocessing.get_context("forkserver")
        )
        if use_pool
        else None
    )

    extracted = empty = failed = 0
    processed = 0
    try:
        while True:
            if cancel_check:
                cancel_check()
            batch = await repo.pending_batch(batch_size)
            if not batch:
                break

            texts = await _extract_batch(batch, loop, pool)

            # Sequential DB writes (SQLite single-writer).
            for book_id, path, _fmt in batch:
                if cancel_check:
                    cancel_check()
                text = texts.get(book_id)
                try:
                    if text is None:
                        await repo.mark_status(book_id, "failed")
                        failed += 1
                    elif text.strip():
                        mtime = await asyncio.to_thread(_safe_mtime, path)
                        await repo.upsert_extracted(book_id, text, len(text), mtime)
                        extracted += 1
                    else:
                        await repo.mark_status(book_id, "empty")
                        empty += 1
                except Exception as e:  # noqa: BLE001 — keep backfill running
                    logger.warning("Content write failed (book %s, %s): %s", book_id, path, e)
                    await repo.mark_status(book_id, "failed")
                    failed += 1
                processed += 1
                if progress_callback:
                    await progress_callback(processed, total_pending, path)
            await session.commit()
    finally:
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    total = extracted + empty + failed
    logger.info(
        "Content backfill complete: %d extracted, %d empty, %d failed (workers=%d)",
        extracted,
        empty,
        failed,
        workers,
    )
    return {"extracted": extracted, "empty": empty, "failed": failed, "total": total}


async def _extract_batch(
    batch: list[tuple[int, str, str]], loop: asyncio.AbstractEventLoop, pool: ProcessPoolExecutor | None
) -> dict[int, str | None]:
    """Extract text for a batch in parallel (pool) or sequentially.

    Returns ``{book_id: text_or_None}``; ``None`` marks a worker-level failure.
    ``extract_text`` itself never raises (returns "" on parse failure / empty),
    so ``None`` only appears if a worker process died.
    """
    if pool is None:
        return {bid: await asyncio.to_thread(extract_text, path, fmt) for bid, path, fmt in batch}

    futures = [loop.run_in_executor(pool, extract_text, path, fmt) for _, path, fmt in batch]
    results = await asyncio.gather(*futures, return_exceptions=True)
    out: dict[int, str | None] = {}
    for (book_id, path, _fmt), res in zip(batch, results, strict=True):
        if isinstance(res, Exception):
            logger.warning("Content extract worker crashed (book %s, %s): %s", book_id, path, res)
            out[book_id] = None
        else:
            out[book_id] = res
    return out


def _safe_mtime(path: str) -> float | None:
    """File mtime for the content row (future re-extract trigger), or None."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


__all__ = ["run_content_backfill"]

