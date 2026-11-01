"""NAS storage backend via SMB/NFS mount."""

import asyncio
import os
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool

from app.logging_config import get_logger
from app.storage import StorageBackend

logger = get_logger(__name__)


class NASStorageBackend(StorageBackend):
    """Storage backend for NAS access via SMB/NFS mount.

    The NAS share must be mounted to a local path (e.g., /mnt/nas/ebooks).
    This backend delegates to standard OS calls but adds health checking
    and mount validation.
    """

    def __init__(self, mount_path: str, host: str = "") -> None:
        """Initialize NAS storage backend.

        Args:
            mount_path: Local mount point for the NAS share.
            host: NAS host IP or hostname (for status display).
        """
        self.mount_path = mount_path
        self.host = host
        self._last_check: datetime | None = None
        self._healthy: bool = False

    async def health_check(self) -> dict:
        """Check if the NAS mount is accessible.

        The filesystem probes (``os.stat`` / ``os.listdir``) run in the
        threadpool with a hard timeout. A stale or offline SMB/NFS mount can
        otherwise block inside the kernel for the full RPC timeout (often
        60s+), which freezes the event loop and freezes every concurrent
        SSE progress stream. We bound that to a few seconds instead.
        """
        try:
            if not self.mount_path:
                self._healthy = False
                return {"healthy": False, "details": "Mount path not configured"}

            async def _probe() -> bool:
                def _blocking() -> bool:
                    if not os.path.ismount(self.mount_path) and not os.path.isdir(self.mount_path):
                        return False
                    os.stat(self.mount_path)
                    os.listdir(self.mount_path)
                    return True

                return await run_in_threadpool(_blocking)

            try:
                ok = await asyncio.wait_for(
                    _probe(), timeout=float(os.environ.get("NAS_HEALTH_TIMEOUT", "5"))
                )
            except TimeoutError:
                self._healthy = False
                self._last_check = datetime.now(UTC)
                logger.warning("NAS health check timed out (mount stale?): %s", self.mount_path)
                return {
                    "healthy": False,
                    "details": f"NAS unreachable (timeout): {self.mount_path}",
                }

            if not ok:
                self._healthy = False
                self._last_check = datetime.now(UTC)
                return {
                    "healthy": False,
                    "details": f"Path does not exist or is not mounted: {self.mount_path}",
                }

            self._healthy = True
            self._last_check = datetime.now(UTC)
            return {"healthy": True, "details": f"NAS online at {self.host}"}
        except OSError as e:
            self._healthy = False
            self._last_check = datetime.now(UTC)
            logger.warning(f"NAS health check failed: {e}")
            return {"healthy": False, "details": f"NAS unreachable: {e}"}

    @property
    def is_healthy(self) -> bool:
        """Return last known health status."""
        return self._healthy

    @property
    def status(self) -> dict:
        """Return detailed status info."""
        return {
            "healthy": self._healthy,
            "last_check": self._last_check,
            "mount_path": self.mount_path,
            "host": self.host,
        }
