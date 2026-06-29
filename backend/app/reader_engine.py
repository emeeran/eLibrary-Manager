"""Reader engine for extracting content from various ebook formats."""

from __future__ import annotations

import os

from app.chapter_cache import get_chapter_cache
from app.logging_config import get_logger
from app.scanner import LibraryScanner

logger = get_logger(__name__)


class ReaderEngine:
    """Unified reader for extracting content from all supported formats.

    Provides a consistent interface for reading chapters regardless of
    the underlying ebook format (EPUB, PDF, MOBI).

    Features server-side caching for fast page loads.
    """

    def __init__(self) -> None:
        """Initialize reader engine with scanner and cache."""
        self.scanner = LibraryScanner()
        self._cache = get_chapter_cache()

    def _get_file_mtime(self, path: str) -> float | None:
        """Get file modification time for cache invalidation."""
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    async def get_chapter_content(
        self, ebook_path: str, chapter_index: int
    ) -> tuple[str, str, int]:
        """Get content for a specific chapter with caching.

        Args:
            ebook_path: Path to ebook file
            chapter_index: Zero-based chapter index

        Returns:
            Tuple of (content, title, total_chapters)

        Raises:
            ResourceNotFoundError: If chapter not found
            EbookParsingError: If parsing fails
        """
        file_mtime = self._get_file_mtime(ebook_path)

        # Try cache first
        cached = await self._cache.get(ebook_path, chapter_index, file_mtime)
        if cached:
            logger.debug(f"Cache HIT for {ebook_path} ch{chapter_index}")
            return cached.content, cached.title, cached.total_chapters

        logger.debug(f"Cache MISS for {ebook_path} ch{chapter_index}")

        # Extract only the requested chapter (avoids full-book parse)
        content, title, total = await self.scanner.get_single_chapter(ebook_path, chapter_index)

        # Store in cache
        if file_mtime:
            await self._cache.put(ebook_path, chapter_index, content, title, total, file_mtime)

        return content, title, total

    @staticmethod
    def estimate_chapter_pages(content: str) -> int:
        """Estimate the number of readable pages in a chapter.

        Uses ~1800 characters per page as a reasonable average for
        typical reading material.

        Args:
            content: HTML content of the chapter.

        Returns:
            Estimated page count (minimum 1).
        """
        return max(1, len(content) // 1800)

    async def get_table_of_contents(self, ebook_path: str) -> list[dict]:
        """Get table of contents for an ebook.

        Args:
            ebook_path: Path to ebook file

        Returns:
            List of TOC items with index, title, level

        Raises:
            EbookParsingError: If parsing fails
        """
        return await self.scanner.get_table_of_contents(ebook_path)


# Module-level singleton — avoids re-creating scanner + parsers on every request
_reader_engine: ReaderEngine | None = None


def get_reader_engine() -> ReaderEngine:
    """Get the global ReaderEngine singleton."""
    global _reader_engine
    if _reader_engine is None:
        _reader_engine = ReaderEngine()
    return _reader_engine
