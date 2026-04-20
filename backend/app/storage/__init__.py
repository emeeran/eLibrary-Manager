"""Storage backend abstraction for local and NAS file access."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class StorageBackend(ABC):
    """Abstract base class for storage backends.

    Provides a uniform interface for file system operations regardless
    of whether the underlying storage is local or a network mount.
    """

    @abstractmethod
    async def health_check(self) -> dict:
        """Check storage availability.

        Returns:
            Dict with "healthy" (bool) and "details" (str) keys.
        """

    @abstractmethod
    async def walk_directory(self, root: str) -> list[tuple[str, list[str]]]:
        """Recursively walk a directory tree.

        Args:
            root: Root directory path to walk.

        Returns:
            List of (dirpath, filenames) tuples.
        """

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if a file exists.

        Args:
            path: File path to check.

        Returns:
            True if the file exists.
        """

    @abstractmethod
    async def get_file_size(self, path: str) -> int:
        """Get file size in bytes.

        Args:
            path: File path.

        Returns:
            File size in bytes.
        """

    @abstractmethod
    def resolve_path(self, path: str) -> str:
        """Resolve to a locally-accessible path for parsers.

        Args:
            path: Original file path.

        Returns:
            Path that can be opened by local file APIs.
        """
