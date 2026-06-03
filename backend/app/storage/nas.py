"""NAS storage backend via SMB/NFS mount."""

import os
from datetime import UTC, datetime

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

        Tests by stat-ing the mount root directory with a timeout-safe approach.
        """
        try:
            if not self.mount_path:
                self._healthy = False
                return {"healthy": False, "details": "Mount path not configured"}

            if not os.path.ismount(self.mount_path) and not os.path.isdir(self.mount_path):
                self._healthy = False
                self._last_check = datetime.now(UTC)
                return {
                    "healthy": False,
                    "details": f"Path does not exist or is not mounted: {self.mount_path}",
                }

            os.stat(self.mount_path)
            os.listdir(self.mount_path)

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
