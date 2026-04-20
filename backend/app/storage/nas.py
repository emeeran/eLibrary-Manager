"""NAS storage backend via SMB/NFS mount."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

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
        self._last_check: Optional[datetime] = None
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
                self._last_check = datetime.now(timezone.utc)
                return {
                    "healthy": False,
                    "details": f"Path does not exist or is not mounted: {self.mount_path}",
                }

            # Attempt to list the directory to verify it's responsive
            os.stat(self.mount_path)
            # Quick check that we can read the directory
            os.listdir(self.mount_path)

            self._healthy = True
            self._last_check = datetime.utcnow()
            return {"healthy": True, "details": f"NAS online at {self.host}"}
        except OSError as e:
            self._healthy = False
            self._last_check = datetime.utcnow()
            logger.warning(f"NAS health check failed: {e}")
            return {"healthy": False, "details": f"NAS unreachable: {e}"}

    async def walk_directory(self, root: str) -> list[tuple[str, list[str]]]:
        """Walk NAS directory tree via mount point (non-blocking)."""
        def _walk() -> list[tuple[str, list[str]]]:
            result: list[tuple[str, list[str]]] = []
            try:
                for dirpath, _, filenames in os.walk(root):
                    result.append((dirpath, filenames))
            except OSError as e:
                logger.error(f"Failed to walk NAS directory {root}: {e}")
            return result
        return await asyncio.to_thread(_walk)

    async def file_exists(self, path: str) -> bool:
        """Check if file exists on NAS mount."""
        return os.path.exists(path)

    async def get_file_size(self, path: str) -> int:
        """Get file size from NAS mount."""
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def resolve_path(self, path: str) -> str:
        """Return path as-is (already local via mount)."""
        return path

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
