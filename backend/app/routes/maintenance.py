"""Library maintenance and cleanup routes."""

import asyncio
import json
import uuid
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_config
from app.database import db_manager, get_db
from app.logging_config import get_logger
from app.routes.library import invalidate_book_list_cache
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
from app.services.backup_service import apply_restore, create_backup
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

                result = await service.dedup_books(dry_run=False, progress_callback=progress_cb)
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


@router.post("/reoptimize-covers")
async def reoptimize_covers(
    threshold_kb: int = Query(
        100, ge=10, le=2000, description="Re-encode covers larger than this many KB"
    ),
) -> dict:
    """Re-encode oversized cover images to the standard 600x900 / q85.

    Runs as a background task; poll progress via ``/api/maintenance/progress/{task_id}``.
    Returns a ``task_id`` immediately. Frees disk and speeds grid loads —
    MOBI covers in particular were previously stored at full embedded size.
    """
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
                        message=f"Re-optimizing covers: {processed}/{total}",
                    )

                result = await service.reoptimize_covers(
                    threshold_bytes=threshold_kb * 1024,
                    progress_callback=progress_cb,
                )
                scan_store.update(
                    task_id,
                    status="completed",
                    message=(
                        f"Optimized {result['optimized']} covers; "
                        f"freed {result['freed'] / 1048576:.1f} MB"
                    ),
                )
        except Exception as e:
            scan_store.update(task_id, status="failed", message=str(e))
        finally:
            _active_tasks.discard(task_id)

    asyncio.create_task(_run())
    return {"task_id": task_id, "status": "started"}


# ---- SSE Progress ----


@router.get("/progress/{task_id}")
async def maintenance_progress(task_id: str) -> StreamingResponse:
    """Stream background task progress via Server-Sent Events."""

    async def event_generator() -> AsyncGenerator[str, None]:
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


# ---- Backup / Restore (item 2.3) ----


def _db_file_path() -> Path:
    """Resolve the SQLite file path from the configured database URL."""
    from app.services.backup_service import db_path_from_url

    return db_path_from_url(get_config().database_url)


def _backups_dir(destination: str | None = None) -> Path:
    base = Path(destination) if destination else Path("./backups")
    base.mkdir(parents=True, exist_ok=True)
    return base


@router.get("/backups")
async def list_backup_files() -> dict:
    """List available backup ZIPs (newest first)."""
    from app.services.backup_service import list_backups

    return {"backups": list_backups(_backups_dir())}


@router.post("/backup")
async def create_library_backup(
    destination: str | None = None, db: AsyncSession = Depends(get_db)
) -> dict:
    """Create a backup ZIP: database (online backup) + covers + settings.

    Args:
        destination: Optional directory for the ZIP (e.g. a NAS mount).
            Defaults to ``./backups``.
        db: Database session (settings export).

    Returns:
        {"file", "size_bytes", "covers"}
    """
    from app.models import Setting

    result = await db.execute(select(Setting.key, Setting.value))
    settings_map = dict(result.all())

    try:
        db_path = _db_file_path()
        path = create_backup(
            db_path=db_path,
            covers_dir=Path(get_config().covers_path),
            settings_map=settings_map,
            dest_dir=_backups_dir(destination),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}") from e

    return {"file": str(path), "size_bytes": path.stat().st_size}


@router.post("/restore")
async def restore_library_backup(
    backup_name: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict:
    """Restore books, covers, and settings from a backup ZIP.

    Safety gate: an automatic pre-restore backup is taken FIRST — if that
    fails, the restore is refused. The engine is disposed so open connections
    never write into the replaced database file; new connections open the
    restored DB (no restart needed, a page reload suffices).
    """
    from app.services.library_service import invalidate_stats_cache

    backups_dir = _backups_dir()
    if file is not None:
        staged = backups_dir / f"uploaded-restore-{file.filename or 'archive.zip'}"
        staged = staged.with_name(staged.name.replace("/", "_"))
        content = await file.read()
        staged.write_bytes(content)
        zip_path = staged
    elif backup_name:
        if backup_name != Path(backup_name).name or not backup_name.endswith(".zip"):
            raise HTTPException(status_code=422, detail="Invalid backup name")
        zip_path = backups_dir / backup_name
    else:
        raise HTTPException(status_code=422, detail="Provide backup_name or a file")

    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail=f"Backup not found: {zip_path.name}")

    db_path = _db_file_path()

    # Belt and braces: automatic pre-restore backup, refuse to continue if it fails.
    try:
        pre = create_backup(
            db_path=db_path,
            covers_dir=Path(get_config().covers_path),
            settings_map={},
            dest_dir=backups_dir,
            label="pre-restore",
        )
    except (OSError, ValueError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Refusing to restore: pre-restore backup failed ({e})",
        ) from e

    # Close all pooled connections so nothing writes into the old file.
    if db_manager._engine is not None:
        await db_manager.engine.dispose()

    try:
        settings_map = apply_restore(zip_path, db_path, Path(get_config().covers_path))
    except (ValueError, zipfile.BadZipFile) as e:
        raise HTTPException(status_code=422, detail=f"Restore failed: {e}") from e

    # Re-apply settings into the restored DB via a fresh session.
    settings_applied = 0
    if settings_map:
        async with db_manager.get_session() as session:
            from app.models import Setting

            for key, value in settings_map.items():
                await session.merge(Setting(key=key, value=value))
                settings_applied += 1
            await session.commit()

    invalidate_book_list_cache()
    invalidate_stats_cache()
    logger.info(f"Library restored from {zip_path.name} (pre-restore: {pre.name})")
    return {
        "restored": True,
        "source": zip_path.name,
        "pre_restore_backup": pre.name,
        "settings_applied": settings_applied,
    }
