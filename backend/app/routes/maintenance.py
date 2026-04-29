"""Library maintenance and cleanup routes."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_manager, get_db
from app.logging_config import get_logger
from app.scan_progress import scan_store
from app.schemas import (
    BulkDeleteResult,
    DuplicateDedupResult,
    DuplicatesResponse,
    FKStatusResponse,
    MaintenanceSummary,
    OrphanDeleteResult,
    OrphansReport,
    StaleBooksResponse,
    VacuumResult,
)
from app.services.maintenance_service import MaintenanceService

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
logger = get_logger(__name__)

_active_tasks: set[str] = set()


# ---- Summary ----


@router.get("/summary", response_model=MaintenanceSummary)
async def maintenance_summary(
    db: AsyncSession = Depends(get_db),
) -> MaintenanceSummary:
    """Dashboard summary of all maintenance metrics."""
    service = MaintenanceService(db)
    return await service.get_maintenance_summary()


# ---- Stale Books ----


@router.get("/stale-books", response_model=StaleBooksResponse)
async def detect_stale_books(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> StaleBooksResponse:
    """Detect books whose files are missing from disk."""
    service = MaintenanceService(db)
    items, total = await service.detect_stale_books(page=page, page_size=page_size)
    return StaleBooksResponse(
        stale_books=items,
        total_stale=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/stale-books")
async def purge_stale_books(
    dry_run: bool = Query(True, description="Set false to execute deletion"),
) -> dict | BulkDeleteResult:
    """Purge stale books. Runs as background task when dry_run=false."""
    if dry_run:
        async with db_manager.get_session() as db:
            service = MaintenanceService(db)
            return await service.purge_stale_books(dry_run=True)

    if _active_tasks:
        raise HTTPException(
            status_code=409,
            detail="A maintenance task is already running. Wait for it to finish.",
        )

    task_id = uuid.uuid4().hex[:8]
    scan_store.create(task_id)
    _active_tasks.add(task_id)

    async def _run() -> None:
        try:
            async with db_manager.get_session() as db:
                service = MaintenanceService(db)

                async def progress_cb(processed: int, total: int) -> None:
                    scan_store.update(
                        task_id,
                        processed=processed,
                        total_found=total,
                        message=f"Purging stale books: {processed}/{total}",
                    )

                result = await service.purge_stale_books(
                    dry_run=False, progress_callback=progress_cb
                )
                scan_store.update(
                    task_id,
                    status="completed",
                    message=result.message,
                    errors=result.errors,
                )
        except Exception as e:
            logger.error(f"Stale purge task failed: {e}")
            scan_store.update(task_id, status="failed", message=str(e))
        finally:
            _active_tasks.discard(task_id)

    asyncio.create_task(_run())
    return {"task_id": task_id, "status": "started"}


# ---- Duplicates ----


@router.get("/duplicates", response_model=DuplicatesResponse)
async def detect_duplicates(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> DuplicatesResponse:
    """Detect duplicate title+author groups."""
    service = MaintenanceService(db)
    groups, total_groups, total_extra = await service.detect_duplicates(
        page=page, page_size=page_size
    )
    return DuplicatesResponse(
        duplicate_groups=groups,
        total_groups=total_groups,
        total_extra_copies=total_extra,
        page=page,
        page_size=page_size,
    )


@router.delete("/duplicates")
async def dedup_books(
    dry_run: bool = Query(True, description="Set false to execute dedup"),
) -> dict | DuplicateDedupResult:
    """Remove duplicate books, keeping the best copy."""
    if dry_run:
        async with db_manager.get_session() as db:
            service = MaintenanceService(db)
            return await service.dedup_books(dry_run=True)

    if _active_tasks:
        raise HTTPException(
            status_code=409,
            detail="A maintenance task is already running. Wait for it to finish.",
        )

    task_id = uuid.uuid4().hex[:8]
    scan_store.create(task_id)
    _active_tasks.add(task_id)

    async def _run() -> None:
        try:
            async with db_manager.get_session() as db:
                service = MaintenanceService(db)

                async def progress_cb(processed: int, total: int) -> None:
                    scan_store.update(
                        task_id,
                        processed=processed,
                        total_found=total,
                        message=f"Deduplicating: {processed}/{total}",
                    )

                result = await service.dedup_books(
                    dry_run=False, progress_callback=progress_cb
                )
                scan_store.update(
                    task_id,
                    status="completed",
                    message=result.message,
                    errors=result.errors,
                )
        except Exception as e:
            logger.error(f"Dedup task failed: {e}")
            scan_store.update(task_id, status="failed", message=str(e))
        finally:
            _active_tasks.discard(task_id)

    asyncio.create_task(_run())
    return {"task_id": task_id, "status": "started"}


# ---- Orphans ----


@router.get("/orphans", response_model=OrphansReport)
async def detect_orphans(
    db: AsyncSession = Depends(get_db),
) -> OrphansReport:
    """Detect orphaned child records (bookmarks, notes, etc.)."""
    service = MaintenanceService(db)
    return await service.detect_orphans()


@router.delete("/orphans", response_model=OrphanDeleteResult)
async def purge_orphans(
    dry_run: bool = Query(True, description="Set false to execute deletion"),
    db: AsyncSession = Depends(get_db),
) -> OrphanDeleteResult:
    """Delete orphaned child records."""
    service = MaintenanceService(db)
    return await service.purge_orphans(dry_run=dry_run)


# ---- FK Status ----


@router.get("/fk-status", response_model=FKStatusResponse)
async def fk_status(
    db: AsyncSession = Depends(get_db),
) -> FKStatusResponse:
    """Check if PRAGMA foreign_keys is ON."""
    service = MaintenanceService(db)
    return await service.get_fk_status()


# ---- VACUUM ----


@router.post("/vacuum", response_model=VacuumResult)
async def vacuum_database() -> VacuumResult:
    """Run VACUUM to compact the SQLite database."""
    if _active_tasks:
        raise HTTPException(
            status_code=409,
            detail="A maintenance task is running. Wait for it to finish before vacuuming.",
        )
    async with db_manager.get_session() as db:
        service = MaintenanceService(db)
        return await service.vacuum_database()


# ---- SSE Progress ----


@router.get("/progress/{task_id}")
async def maintenance_progress(task_id: str) -> StreamingResponse:
    """Stream background task progress via Server-Sent Events."""

    async def event_generator():
        while True:
            progress = scan_store.get(task_id)
            if not progress:
                yield f"data: {json.dumps({'status': 'unknown', 'message': 'Task not found'})}\n\n"
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
