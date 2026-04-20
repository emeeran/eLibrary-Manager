"""Reader engine for extracting content from various ebook formats."""

from __future__ import annotations

import os

from app.chapter_cache import get_chapter_cache
from app.exceptions import ResourceNotFoundError
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
        self,
        ebook_path: str,
        chapter_index: int
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
        content, title, total = await self.scanner.get_single_chapter(
            ebook_path, chapter_index
        )

        # Store in cache
        if file_mtime:
            await self._cache.put(
                ebook_path, chapter_index,
                content, title, total, file_mtime
            )

        return content, title, total

    async def get_total_chapters(self, ebook_path: str) -> int:
        """Get the total number of chapters in an ebook.

        Args:
            ebook_path: Path to ebook file

        Returns:
            Total number of chapters
        """
        return await self.scanner.count_chapters(ebook_path)

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

    async def get_all_chapters(self, ebook_path: str) -> list[tuple[int, str, str]]:
        """Get all chapters from an ebook.

        Args:
            ebook_path: Path to ebook file

        Returns:
            List of tuples: (chapter_index, chapter_title, chapter_content)
        """
        return await self.scanner.get_chapters(ebook_path)

    async def get_text_for_summary(
        self,
        ebook_path: str,
        chapter_index: int,
        max_chars: int = 15000
    ) -> str:
        """Get chapter text optimized for AI summarization.

        Args:
            ebook_path: Path to ebook file
            chapter_index: Zero-based chapter index
            max_chars: Maximum characters to return (for token limits)

        Returns:
            Text content truncated to max_chars if needed

        Raises:
            ResourceNotFoundError: If chapter not found
            EbookParsingError: If parsing fails
        """
        content, _, _ = await self.get_chapter_content(ebook_path, chapter_index)

        if len(content) > max_chars:
            content = content[:max_chars]
            logger.debug(f"Truncated content to {max_chars} chars for summarization")

        return content

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
