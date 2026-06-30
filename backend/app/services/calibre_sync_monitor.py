"""Background Calibre auto-sync (spec 011 v1.2).

An asyncio loop started in the app lifespan that, on a configurable interval,
runs an incremental Calibre sync (``sync_library``) against a saved library
path — so edits/deletes in Calibre propagate to eLM without a manual re-import.

It shares the library scan lock (``_active_scans``) so it never collides with a
manual scan/import. Failures are logged and swallowed so one bad run doesn't
kill the loop.
"""

from __future__ import annotations

import asyncio

from app.logging_config import get_logger

logger = get_logger(__name__)


class CalibreSyncMonitor:
    """Periodically sync a linked Calibre library into the index."""

    def __init__(self, interval_minutes: int) -> None:
        self.interval_minutes = max(1, interval_minutes)
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped = False
            self._task = asyncio.create_task(self._loop())
            logger.info("Calibre auto-sync monitor started (every %dm)", self.interval_minutes)

    async def stop(self) -> None:
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    async def _loop(self) -> None:
        # Delay the first run by one interval (the app just started).
        while not self._stopped:
            try:
                await asyncio.sleep(self.interval_minutes * 60)
            except asyncio.CancelledError:
                return
            if self._stopped:
                return
            try:
                await self._run_sync()
            except Exception as e:  # noqa: BLE001 — keep the loop alive
                logger.warning("Calibre auto-sync run failed: %s", e)

    async def _run_sync(self) -> None:
        from app.database import db_manager
        from app.repositories import SettingsRepository
        from app.routes.library import _active_scans  # noqa: E402
        from app.services.calibre_sync_service import sync_library

        # Re-read the library path each run so the operator can change it
        # without restarting.
        async with db_manager.get_session() as session:
            settings = await SettingsRepository(session).get_all()
            path = settings.get("calibre_library_path", "")
        if not path:
            return
        if _active_scans:  # don't collide with a manual scan/import
            logger.debug("Calibre auto-sync skipped — a scan is already running")
            return

        scan_id = "calibre-autosync"
        _active_scans.add(scan_id)
        try:
            logger.info("Calibre auto-sync starting for %s", path)
            async with db_manager.get_session() as session:
                summary = await sync_library(session, path, prune_missing=True)
                await session.commit()
            logger.info(
                "Calibre auto-sync done: %d imported, %d updated, %d unchanged",
                summary.imported,
                summary.updated,
                summary.skipped_existing,
            )
        finally:
            _active_scans.discard(scan_id)


__all__ = ["CalibreSyncMonitor"]
