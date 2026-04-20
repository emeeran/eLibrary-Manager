"""Library scanner for ebook indexing and metadata extraction."""

import os
from pathlib import Path
from typing import Optional

from app.config import get_config
from app.exceptions import LibraryScannerError
from app.logging_config import get_logger
from app.parsers import EPUBParser, MOBIParser, PDFParser
from app.schemas import BookCreate
from app.storage import StorageBackend
from app.storage.local import LocalStorageBackend

logger = get_logger(__name__)


class LibraryScanner:
    """Scanner for ebook library indexing.

    Recursively scans a directory for EPUB, PDF, and MOBI files,
    extracts metadata using format-specific parsers, and prepares
    them for database insertion.
    """

    SUPPORTED_FORMATS = frozenset({".epub", ".pdf", ".mobi"})

    def __init__(
        self,
        storage: StorageBackend | None = None,
        storage_type: str = "local",
    ) -> None:
        """Initialize scanner with configuration and parsers.

        Args:
            storage: Storage backend for directory operations. Defaults to LocalStorageBackend.
            storage_type: Source type tag for scanned books ("local" or "nas").
        """
        self.config = get_config()
        self.covers_path = self.config.covers_path
        self.storage: StorageBackend = storage or LocalStorageBackend()
        self.storage_type = storage_type

        # Initialize format-specific parsers
        self.epub_parser = EPUBParser(
            covers_path=self.covers_path,
            book_images_path=self.config.book_images_path,
        )
        self.pdf_parser = PDFParser(
            covers_path=self.covers_path,
            book_images_path=self.config.book_images_path,
        )
        self.mobi_parser = MOBIParser(covers_path=self.covers_path)

    async def scan_directory(
        self,
        directory: str | None = None,
    ) -> list[BookCreate]:
        """Scan directory for ebook files.

        Args:
            directory: Directory to scan (defaults to config library_path)

        Returns:
            List of BookCreate objects for found ebooks

        Raises:
            LibraryScannerError: If scanning fails
        """
        target_dir = directory or self.config.library_path
        logger.info(f"Starting library scan: {target_dir}")

        if not await self.storage.file_exists(target_dir):
            raise LibraryScannerError(
                f"Library directory does not exist: {target_dir}",
                {"directory": target_dir}
            )

        books: list[BookCreate] = []
        processed_count = 0
        error_count = 0
        skipped_count = 0

        try:
            dir_tree = await self.storage.walk_directory(target_dir)
            for root, files in dir_tree:
                for filename in files:
                    file_path = Path(root) / filename
                    file_ext = file_path.suffix

                    if file_ext.lower() not in self.SUPPORTED_FORMATS:
                        continue

                    try:
                        book_data = await self.extract_metadata(str(file_path))
                        book_data.storage_type = self.storage_type
                        books.append(book_data)
                        processed_count += 1
                        logger.debug(f"Indexed: {book_data.title}")

                    except LibraryScannerError as e:
                        if "DRM" in str(e.details):
                            logger.warning(f"Skipped DRM file: {file_path}")
                            skipped_count += 1
                        else:
                            error_count += 1
                            logger.warning(f"Failed to parse {file_path}: {e}")
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Unexpected error processing {file_path}: {e}")

        except Exception as e:
            raise LibraryScannerError(
                f"Scanning failed: {str(e)}",
                {"directory": target_dir}
            ) from e

        logger.info(
            f"Scan complete: {processed_count} indexed, {skipped_count} skipped (DRM), {error_count} errors"
        )
        return books

    async def fast_index_directory(
        self,
        directory: str | None = None,
        progress_callback: object | None = None,
    ) -> list[BookCreate]:
        """Fast-index a directory by collecting file paths and basic metadata.

        Unlike ``scan_directory``, this does NOT open each file for full
        metadata extraction.  It derives title/author from the filename and
        path structure, and stores the full path for on-demand parsing later.

        Uses streaming os.scandir to avoid blocking on large directory trees.

        Args:
            directory: Directory to scan. Defaults to config library_path.
            progress_callback: Optional async callable ``(scanned, current_file)``
                invoked every 50 files for progress reporting.

        Returns:
            List of BookCreate objects with lightweight metadata.
        """
        import re
        import asyncio

        target_dir = directory or self.config.library_path
        logger.info(f"Starting fast index: {target_dir}")

        if not os.path.isdir(target_dir):
            raise LibraryScannerError(
                f"Library directory does not exist: {target_dir}",
                {"directory": target_dir},
            )

        SUPPORTED = self.SUPPORTED_FORMATS
        books: list[BookCreate] = []
        dirs_to_process = [target_dir]
        scanned = 0

        while dirs_to_process:
            # Process in small batches to yield control
            batch = dirs_to_process[:50]
            dirs_to_process = dirs_to_process[50:]

            for current_dir in batch:
                try:
                    with os.scandir(current_dir) as it:
                        for entry in it:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    dirs_to_process.append(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    ext = Path(entry.name).suffix.lower()
                                    if ext not in SUPPORTED:
                                        continue

                                    str_path = entry.path
                                    stem = Path(entry.name).stem

                                    # Clean filename for title
                                    clean = re.sub(
                                        r"\s*[\(\[].*?(?:z-lib|zlibrary|1lib|lib\.gen|retail).*?[\)\]]",
                                        "", stem, flags=re.IGNORECASE,
                                    ).strip()
                                    clean = re.sub(r"[\s._-]+$", "", clean).strip() or stem

                                    title = clean
                                    author = "Unknown"
                                    if " - " in clean:
                                        parts = clean.split(" - ", 1)
                                        title = parts[0].strip()
                                        author = parts[1].strip()

                                    try:
                                        file_size = entry.stat(follow_symlinks=False).st_size
                                    except OSError:
                                        file_size = 0

                                    books.append(BookCreate(
                                        title=title[:500],
                                        author=author[:200],
                                        path=str_path,
                                        format=ext.lstrip(".").upper(),
                                        file_size=file_size,
                                        total_pages=max(1, file_size // 2048),
                                        storage_type=self.storage_type,
                                    ))
                                    scanned += 1

                                    # Report progress every 50 files
                                    if progress_callback and scanned % 50 == 0:
                                        if asyncio.iscoroutinefunction(progress_callback):
                                            await progress_callback(scanned, entry.name)
                                        else:
                                            progress_callback(scanned, entry.name)

                            except OSError:
                                continue
                except PermissionError:
                    continue
                except OSError:
                    continue

            # Yield control every batch to keep server responsive
            if dirs_to_process:
                await asyncio.sleep(0.01)

        logger.info(f"Fast index complete: {scanned} files found")
        return books

    async def extract_metadata(self, ebook_path: str) -> BookCreate:
        """Extract metadata using the appropriate parser.

        Args:
            ebook_path: Path to ebook file

        Returns:
            BookCreate object with extracted metadata

        Raises:
            EbookParsingError: If parsing fails
            LibraryScannerError: If format is not supported
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".epub":
            parser = self.epub_parser
        elif ext == ".pdf":
            parser = self.pdf_parser
        elif ext == ".mobi":
            parser = self.mobi_parser
        else:
            raise LibraryScannerError(
                f"Unsupported file format: {ext}",
                {"path": ebook_path, "format": ext}
            )

        # Extract metadata using format-specific parser
        return await parser.extract_metadata(ebook_path)

    async def extract_cover(self, ebook_path: str) -> Optional[str]:
        """Extract cover image using the appropriate parser.

        Args:
            ebook_path: Path to ebook file

        Returns:
            Path to extracted cover or None
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".epub":
            return await self.epub_parser.extract_cover(ebook_path)
        elif ext == ".pdf":
            return await self.pdf_parser.extract_cover(ebook_path)
        elif ext == ".mobi":
            return await self.mobi_parser.extract_cover(ebook_path)

        return None

    async def get_chapters(self, ebook_path: str) -> list[tuple[int, str, str]]:
        """Get chapters using the appropriate parser.

        Args:
            ebook_path: Path to ebook file

        Returns:
            List of tuples: (chapter_index, chapter_title, chapter_content)

        Raises:
            EbookParsingError: If parsing fails
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".epub":
            return await self.epub_parser.get_chapters(ebook_path)
        elif ext == ".pdf":
            return await self.pdf_parser.get_chapters(ebook_path)
        elif ext == ".mobi":
            return await self.mobi_parser.get_chapters(ebook_path)

        raise EbookParsingError(
            f"Cannot extract chapters from {ext} files",
            {"path": ebook_path}
        )

    async def get_single_chapter(
        self, ebook_path: str, chapter_index: int
    ) -> tuple[str, str, int]:
        """Extract a single chapter without parsing the entire book.

        For PDF and EPUB, uses efficient single-page/chapter extraction.
        For MOBI, falls back to full-parse + index (MOBI requires full text
        for regex-based chapter splitting).

        Args:
            ebook_path: Path to ebook file.
            chapter_index: Zero-based chapter index.

        Returns:
            Tuple of (content_html, title, total_chapters).

        Raises:
            EbookParsingError: If parsing fails.
            ResourceNotFoundError: If chapter index is out of range.
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return await self.pdf_parser.get_single_chapter(ebook_path, chapter_index)
        elif ext == ".epub":
            return await self.epub_parser.get_single_chapter(ebook_path, chapter_index)
        elif ext == ".mobi":
            # MOBI requires full text for chapter splitting — no single-chapter shortcut
            chapters = await self.mobi_parser.get_chapters(ebook_path)
            if chapter_index < 0 or chapter_index >= len(chapters):
                from app.exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(
                    f"Chapter {chapter_index} not found (total: {len(chapters)})",
                    {"path": ebook_path, "index": chapter_index}
                )
            _, title, content = chapters[chapter_index]
            return content, title, len(chapters)

        raise EbookParsingError(
            f"Cannot extract chapters from {ext} files",
            {"path": ebook_path}
        )

    async def count_chapters(self, ebook_path: str) -> int:
        """Count chapters using the appropriate parser.

        Args:
            ebook_path: Path to ebook file

        Returns:
            Number of chapters/pages
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".epub":
            return await self.epub_parser.count_chapters(ebook_path)
        elif ext == ".pdf":
            return await self.pdf_parser.count_chapters(ebook_path)
        elif ext == ".mobi":
            return await self.mobi_parser.count_chapters(ebook_path)

        return 0

    async def get_smart_chapters(self, ebook_path: str) -> list[tuple[int, str, str]]:
        """Get smart-grouped chapters for PDF files.

        Falls back to regular get_chapters() for non-PDF formats.

        Args:
            ebook_path: Path to ebook file.

        Returns:
            List of tuples: (chapter_index, chapter_title, chapter_content)
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return await self.pdf_parser.get_smart_chapters(ebook_path)

        # Non-PDF formats: use regular chapters
        return await self.get_chapters(ebook_path)

    async def get_table_of_contents(self, ebook_path: str) -> list[dict]:
        """Get table of contents using the appropriate parser.

        Args:
            ebook_path: Path to ebook file

        Returns:
            List of TOC items with index, title, level

        Raises:
            EbookParsingError: If parsing fails
        """
        path = Path(ebook_path)
        ext = path.suffix.lower()

        if ext == ".epub":
            return await self.epub_parser.get_table_of_contents(ebook_path)
        elif ext == ".pdf":
            return await self.pdf_parser.get_table_of_contents(ebook_path)
        elif ext == ".mobi":
            return await self.mobi_parser.get_table_of_contents(ebook_path)

        # Return basic TOC for unsupported formats
        chapters = await self.get_chapters(ebook_path)
        return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]
