"""Background health monitor for NAS mount connectivity."""

import asyncio
from datetime import datetime
from typing import Optional

from app.logging_config import get_logger
from app.storage.nas import NASStorageBackend

logger = get_logger(__name__)


class NASHealthMonitor:
    """Periodic health checker for NAS mount availability.

    Runs as a background asyncio task, checking mount status at regular
    intervals and storing the result for API consumption.
    """

    def __init__(
        self,
        backend: NASStorageBackend,
        check_interval: int = 60,
    ) -> None:
        """Initialize health monitor.

        Args:
            backend: NAS storage backend to monitor.
            check_interval: Seconds between health checks.
        """
        self.backend = backend
        self.check_interval = check_interval
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background health check loop."""
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"NAS health monitor started (interval={self.check_interval}s, "
            f"mount={self.backend.mount_path})"
        )

    async def stop(self) -> None:
        """Stop the background health check loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("NAS health monitor stopped")

    async def _run_loop(self) -> None:
        """Main health check loop."""
        while True:
            try:
                result = await self.backend.health_check()
                if not result["healthy"]:
                    logger.warning(f"NAS health check: {result['details']}")
            except Exception as e:
                logger.error(f"NAS health check exception: {e}")
            await asyncio.sleep(self.check_interval)

    @property
    def status(self) -> dict:
        """Return current health status from the backend."""
        return self.backend.status
