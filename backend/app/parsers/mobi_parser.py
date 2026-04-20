"""MOBI format parser using pymobi."""

import os
import re
import struct
from pathlib import Path
from typing import Optional

try:
    from pymobi.mobi import BookMobi
    MOBI_AVAILABLE = True
except ImportError:
    MOBI_AVAILABLE = False
    BookMobi = None

from bs4 import BeautifulSoup

from app.exceptions import EbookParsingError
from app.logging_config import get_logger
from app.schemas import BookCreate

logger = get_logger(__name__)


class MOBIParser:
    """Parser for MOBI format ebooks.

    Handles MOBI file parsing, metadata extraction, and content retrieval.
    Supports HTML extraction for richer formatting preservation.

    Note: DRM-protected MOBI files will be skipped.
    """

    SUPPORTED_FORMAT = "MOBI"

    def __init__(self, covers_path: str = "./static_covers") -> None:
        """Initialize MOBI parser.

        Args:
            covers_path: Directory to store cover images

        Raises:
            ImportError: If pymobi is not installed.
        """
        if not MOBI_AVAILABLE:
            raise ImportError(
                "pymobi is not installed. "
                "Install it with: pip install pymobi"
            )

        self.covers_path = Path(covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)

    async def extract_metadata(self, mobi_path: str) -> BookCreate:
        """Extract metadata from MOBI file.

        Args:
            mobi_path: Path to MOBI file

        Returns:
            BookCreate object with extracted metadata

        Raises:
            EbookParsingError: If parsing fails or DRM detected
        """
        try:
            # Check if file is DRM-protected
            if self._is_drm_protected(mobi_path):
                raise EbookParsingError(
                    "DRM-protected MOBI files are not supported",
                    {"path": mobi_path, "reason": "DRM protection"}
                )

            mobi = BookMobi(mobi_path)

            # Extract metadata from EXTH headers or metadata records
            title = self._get_metadata_value(mobi, 'title') or None
            if not title:
                # Use filename as fallback
                title = Path(mobi_path).stem.replace("-", " ").replace("_", " ").title()

            author = self._get_metadata_value(mobi, 'author') or "Unknown"

            # Extract subject/category from EXTH record type 105
            subjects = []
            try:
                if hasattr(mobi, 'mobi_exth') and mobi.mobi_exth:
                    for record in mobi.mobi_exth.get_records():
                        if record.get_type() == 105:
                            subject = record.get_data().decode('utf-8', errors='ignore')
                            if subject:
                                subjects = [s.strip() for s in subject.split(';') if s.strip()]
                                break
            except Exception:
                pass

            # Get file size
            file_size = os.path.getsize(mobi_path)

            logger.info(f"Extracted MOBI metadata: {title} by {author}")

            return BookCreate(
                title=title,
                author=author,
                path=mobi_path,
                format="MOBI",
                file_size=file_size,
                subjects=subjects
            )

        except EbookParsingError:
            raise
        except Exception as e:
            raise EbookParsingError(
                f"Failed to parse MOBI: {str(e)}",
                {"path": mobi_path, "error": str(e)}
            ) from e

    def _get_metadata_value(self, mobi: BookMobi, key: str) -> str | None:
        """Get metadata value from MOBI file.

        Args:
            mobi: BookMobi instance
            key: Metadata key to retrieve

        Returns:
            Metadata value or None
        """
        try:
            if hasattr(mobi, 'mobi_exth') and mobi.mobi_exth:
                # EXTH record types: 100=author, 101=publisher, 106=title
                record_types = {
                    'author': 100,
                    'title': 106,
                    'publisher': 101
                }

                record_type = record_types.get(key)
                if record_type:
                    for record in mobi.mobi_exth.get_records():
                        if record.get_type() == record_type:
                            return record.get_data().decode('utf-8', errors='ignore')
            return None
        except Exception:
            return None

    def _is_drm_protected(self, mobi_path: str) -> bool:
        """Check if MOBI file has DRM protection.

        Args:
            mobi_path: Path to MOBI file

        Returns:
            True if DRM detected, False otherwise
        """
        try:
            with open(mobi_path, 'rb') as f:
                header = f.read(100)

            # Check for DRM markers
            drm_markers = [
                b'DRM',
                b'Protected',
                b'encryption'
            ]

            return any(marker in header for marker in drm_markers)

        except Exception:
            return False

    async def extract_cover(self, mobi_path: str) -> Optional[str]:
        """Extract cover from MOBI.

        Args:
            mobi_path: Path to MOBI file

        Returns:
            Path to extracted cover or None
        """
        try:
            mobi = BookMobi(mobi_path)

            # Try to get cover image from records
            import hashlib
            epub_hash = hashlib.md5(mobi_path.encode()).hexdigest()
            cover_filename = f"{epub_hash}.jpg"
            cover_path = self.covers_path / cover_filename

            # Extract first image record (usually cover)
            try:
                mobi.saveRecordImage(0, str(cover_path))
                if cover_path.exists():
                    logger.debug(f"Cover extracted: {cover_path}")
                    return str(cover_path)
            except Exception:
                pass

            logger.debug(f"No cover found for {mobi_path}")
            return None

        except Exception as e:
            logger.warning(f"Cover extraction failed: {e}")
            return None

    def _extract_html_content(self, mobi_path: str) -> str:
        """Extract raw HTML content from MOBI file.

        MOBI internally stores HTML. This method replicates the
        decompression logic from pymobi's unpackMobi to extract
        raw HTML instead of plain text.

        Args:
            mobi_path: Path to MOBI file.

        Returns:
            Raw HTML string from the MOBI file.
        """
        mobi = BookMobi(mobi_path)

        rec_num = mobi.palmdoc['recordCount']
        text_length = mobi.palmdoc['textLength']

        # Get the decompression function
        try:
            from pymobi.compression import Palmdoc, Uncompression, Huffcdic
            compression_type = mobi.palmdoc['compressionType']
            if compression_type == 2:
                unpack = Palmdoc.decompress
            elif compression_type == 17480:
                unpack = Huffcdic(mobi).decompress
            else:
                unpack = Uncompression.decompress
        except Exception:
            # Fallback to the parser's own unpack function
            unpack = mobi.unpackFunction()

        data_parts: list[bytes] = []
        for rn in range(1, rec_num + 1):
            record = mobi.loadRecord(rn)

            # Strip trailing entry data (MOBI-specific)
            extraflags = mobi.mobi['extraRecordDataFlags'] >> 1
            while extraflags & 0x1:
                from pymobi.util import decodeVarint
                vint, = struct.unpack_from('>L', record[-4:], 0)
                fint = decodeVarint(vint)
                record = record[:-fint]
                extraflags >>= 1

            if mobi.mobi['extraRecordDataFlags'] & 0x1:
                mb_num, = struct.unpack_from('>B', record[-1:], 0)
                mb_num = (mb_num & 0x3) + 1
                record = record[:-mb_num]

            record = mobi.decrypt(record)
            data_parts.append(unpack(record))

        data_text = b''.join(data_parts)
        # Trim to text length (rest is CSS)
        data_text = data_text[:text_length]

        # Decode
        text_encoding = mobi.mobi.get('textEncoding', 1252)
        if text_encoding == 65001:
            html = data_text.decode('utf-8', errors='replace')
        else:
            html = data_text.decode(f'cp{text_encoding}', errors='replace')

        return html

    async def get_chapters(self, mobi_path: str) -> list[tuple[int, str, str]]:
        """Extract chapters from MOBI with HTML formatting preserved.

        Attempts HTML extraction first for richer formatting.
        Falls back to plain text with basic chapter splitting.

        Args:
            mobi_path: Path to MOBI file

        Returns:
            List of tuples: (chapter_index, chapter_title, chapter_content)

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            # Try HTML extraction first
            try:
                return self._get_chapters_from_html(mobi_path)
            except Exception as html_err:
                logger.warning(
                    f"MOBI HTML extraction failed, falling back to text: {html_err}"
                )

            # Fallback to plain text
            return self._get_chapters_from_text(mobi_path)

        except Exception as e:
            raise EbookParsingError(
                f"Failed to extract chapters: {str(e)}",
                {"path": mobi_path}
            ) from e

    def _get_chapters_from_html(self, mobi_path: str) -> list[tuple[int, str, str]]:
        """Extract chapters from MOBI HTML content.

        Args:
            mobi_path: Path to MOBI file.

        Returns:
            List of (index, title, html_content) tuples.
        """
        html = self._extract_html_content(mobi_path)
        soup = BeautifulSoup(html, 'html.parser')

        # Remove harmful elements
        for tag in soup.find_all(['script', 'style']):
            tag.decompose()

        body = soup.find('body')
        if body:
            content_soup = body
        else:
            content_soup = soup

        # Try splitting by heading tags (h1, h2, h3)
        # First check if there are any headings
        headings = content_soup.find_all(['h1', 'h2', 'h3'])
        chapters: list[tuple[int, str, str]] = []

        if len(headings) >= 2:
            # Split by headings
            current_parts: list[str] = []
            current_title = "Chapter 1"

            for child in content_soup.children:
                if hasattr(child, 'name') and child.name in ('h1', 'h2', 'h3'):
                    # Save previous chapter if it has content
                    if current_parts:
                        chapter_html = "\n".join(current_parts)
                        text = BeautifulSoup(chapter_html, 'html.parser').get_text(strip=True)
                        if len(text) >= 50:
                            chapters.append((len(chapters), current_title, chapter_html))

                    current_title = child.get_text(strip=True) or f"Chapter {len(chapters) + 1}"
                    current_parts = [str(child)]
                else:
                    if hasattr(child, 'name') and child.name:
                        current_parts.append(str(child))
                    elif hasattr(child, 'strip') and child.strip():
                        current_parts.append(f'<p>{child.strip()}</p>')

            # Don't forget the last chapter
            if current_parts:
                chapter_html = "\n".join(current_parts)
                text = BeautifulSoup(chapter_html, 'html.parser').get_text(strip=True)
                if len(text) >= 50:
                    chapters.append((len(chapters), current_title, chapter_html))

        if not chapters:
            # No headings found — try splitting by anchor tags with names
            # or return entire content as one chapter
            html_parts: list[str] = []
            for child in content_soup.children:
                if hasattr(child, 'name') and child.name:
                    html_parts.append(str(child))
                elif hasattr(child, 'strip') and child.strip():
                    html_parts.append(f'<p>{child.strip()}</p>')

            if html_parts:
                full_html = "\n".join(html_parts)
                title = self._extract_mobi_title(content_soup)
                chapters.append((0, title, full_html))

        logger.info(f"Extracted {len(chapters)} chapters from MOBI (HTML mode)")
        return chapters

    def _get_chapters_from_text(self, mobi_path: str) -> list[tuple[int, str, str]]:
        """Fallback: Extract chapters from MOBI as plain text.

        Args:
            mobi_path: Path to MOBI file.

        Returns:
            List of (index, title, content) tuples.
        """
        mobi = BookMobi(mobi_path)
        text_content = mobi.get_text()

        chapters: list[tuple[int, str, str]] = []

        # Split by common chapter markers
        chapter_pattern = r'(?:^|\n)\s*(Chapter|CHAPTER|Part|PART)\s+[IVXLCDM\d]+'
        parts = re.split(chapter_pattern, text_content, flags=re.MULTILINE)

        for i, part in enumerate(parts):
            if len(part.strip()) < 200:
                continue

            # Extract chapter title
            lines = part.strip().split('\n')
            title = f"Chapter {i + 1}"
            if lines:
                first_line = lines[0].strip()
                if len(first_line) < 100:
                    title = first_line

            chapters.append((i, title, part.strip()))

        if not chapters:
            chapters.append((0, "Full Content", text_content))

        logger.info(f"Extracted {len(chapters)} chapters from MOBI (text fallback)")
        return chapters

    def _extract_mobi_title(self, soup: BeautifulSoup) -> str:
        """Extract a title from MOBI HTML content.

        Args:
            soup: BeautifulSoup object.

        Returns:
            Title string.
        """
        for tag_name in ['h1', 'h2', 'h3', 'title']:
            tag = soup.find(tag_name)
            if tag:
                text = tag.get_text(strip=True)
                if text and len(text) < 200:
                    return text
        return "Full Content"

    async def count_chapters(self, mobi_path: str) -> int:
        """Count the number of chapters in a MOBI.

        Args:
            mobi_path: Path to MOBI file

        Returns:
            Number of chapters
        """
        chapters = await self.get_chapters(mobi_path)
        return len(chapters)

    async def get_table_of_contents(self, mobi_path: str) -> list[dict]:
        """Get table of contents for MOBI.

        Note: MOBI TOC is limited, falls back to chapter list.

        Args:
            mobi_path: Path to MOBI file

        Returns:
            List of TOC items with index, title, level

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            mobi = BookMobi(mobi_path)
            toc_items: list[dict] = []

            # Try to extract TOC from MOBI if available
            if hasattr(mobi, 'mobi_exth') and mobi.mobi_exth:
                pass

            if toc_items:
                return toc_items

            # Fall back to chapter list
            chapters = await self.get_chapters(mobi_path)
            return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]

        except Exception:
            # Fall back to basic chapter list on error
            chapters = await self.get_chapters(mobi_path)
            return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]
