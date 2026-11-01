"""CBZ (comic book zip) format parser (spec 008 v1.2, Moon+ parity formats).

A CBZ is a ZIP archive of page images, optionally with a ``ComicInfo.xml``
metadata file. Each page becomes one reader chapter rendered as a data-URI
image so the existing EPUB-style reader displays it unchanged. Metadata
falls back to the filename when ``ComicInfo.xml`` is absent.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.exceptions import EbookParsingError
from app.logging_config import get_logger
from app.schemas import BookCreate

logger = get_logger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class CBZParser:
    """Parser for CBZ comic archives.

    Every image in the archive (natural sort order) becomes one chapter whose
    content embeds the image as a data URI.
    """

    SUPPORTED_FORMAT = "CBZ"

    def __init__(self, covers_path: str = "./static_covers") -> None:
        """Initialize the parser.

        Args:
            covers_path: Directory to store extracted cover images.
        """
        self.covers_path = Path(covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)

    def _open(self, cbz_path: str) -> zipfile.ZipFile:
        """Open the archive, translating failures to EbookParsingError.

        Args:
            cbz_path: Path to the .cbz file.

        Returns:
            An open ZipFile (caller closes it).

        Raises:
            EbookParsingError: If the archive is unreadable.
        """
        try:
            return zipfile.ZipFile(cbz_path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise EbookParsingError(
                f"Failed to open CBZ archive: {exc}", {"path": cbz_path}
            ) from exc

    @staticmethod
    def _natural_key(name: str) -> list[Any]:
        """Sort key producing natural page order (page2 < page10)."""
        return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]

    def _image_names(self, archive: zipfile.ZipFile) -> list[str]:
        """List member names that are page images, naturally sorted."""
        names = [
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
            and Path(info.filename).suffix.lower() in _IMAGE_EXTENSIONS
            and not Path(info.filename).name.startswith(".")
        ]
        names.sort(key=self._natural_key)
        return names

    def _read_comic_info(self, archive: zipfile.ZipFile) -> dict[str, str]:
        """Read optional ComicInfo.xml metadata.

        Args:
            archive: Open archive.

        Returns:
            Dict of the recognized string fields (possibly empty).
        """
        for info in archive.infolist():
            if Path(info.filename).name.lower() == "comicinfo.xml":
                try:
                    root = ElementTree.fromstring(archive.read(info))
                except (ElementTree.ParseError, zipfile.BadZipFile):
                    return {}
                fields = {}
                for key in (
                    "Title",
                    "Series",
                    "Number",
                    "Writer",
                    "Publisher",
                    "Genre",
                    "LanguageISO",
                    "Summary",
                ):
                    el = root.find(key)
                    if el is not None and (el.text or "").strip():
                        fields[key] = el.text.strip()
                return fields
        return {}

    @staticmethod
    def _chapter_html(data: bytes, mime: str) -> str:
        """Render one page as a centered data-URI image document."""
        encoded = base64.b64encode(data).decode("ascii")
        return (
            f'<div class="cbz-page"><img src="data:{mime};base64,{encoded}" '
            'alt="comic page" style="max-width:100%;height:auto;"/></div>'
        )

    # ------------------------------------------------------------------ #
    # Unified parser interface
    # ------------------------------------------------------------------ #

    async def extract_metadata(self, cbz_path: str) -> BookCreate:
        """Extract metadata from ComicInfo.xml (filename fallback).

        Args:
            cbz_path: Path to the .cbz file.

        Returns:
            BookCreate with title/author/description when available.

        Raises:
            EbookParsingError: If the archive is unreadable.
        """
        archive = self._open(cbz_path)
        try:
            info = self._read_comic_info(archive)
        finally:
            archive.close()

        path = Path(cbz_path)
        title = info.get("Title") or (
            f"{info['Series']} #{info['Number']}"
            if "Series" in info and "Number" in info
            else info.get("Series") or path.stem
        )
        return BookCreate(
            title=title,
            author=info.get("Writer"),
            path=str(path.resolve()),
            file_size=path.stat().st_size,
            format=self.SUPPORTED_FORMAT,
            publisher=info.get("Publisher"),
            language=info.get("LanguageISO"),
            description=info.get("Summary"),
            subjects=(
                [g.strip() for g in info["Genre"].split(",") if g.strip()]
                if "Genre" in info
                else []
            ),
        )

    async def extract_cover(self, cbz_path: str) -> str | None:
        """Write the first page image out as the cover.

        Args:
            cbz_path: Path to the .cbz file.

        Returns:
            Path to the written cover image, or None when there are no pages.
        """
        archive = self._open(cbz_path)
        try:
            names = self._image_names(archive)
            if not names:
                return None
            data = archive.read(names[0])
        finally:
            archive.close()

        mime = mimetypes.guess_type(names[0])[0] or "image/jpeg"
        ext = mimetypes.guess_extension(mime) or ".jpg"
        digest = hashlib.sha256(data).hexdigest()[:16]
        cover_file = self.covers_path / f"cbz_{digest}{ext}"
        cover_file.write_bytes(data)
        return str(cover_file)

    async def get_chapters(self, cbz_path: str) -> list[tuple[int, str, str]]:
        """Return one chapter per page image.

        Args:
            cbz_path: Path to the .cbz file.

        Returns:
            List of (chapter_index, "Page N", page_html).

        Raises:
            EbookParsingError: If the archive has no page images.
        """
        archive = self._open(cbz_path)
        try:
            names = self._image_names(archive)
            if not names:
                raise EbookParsingError(
                    "CBZ archive contains no page images", {"path": cbz_path}
                )
            chapters: list[tuple[int, str, str]] = []
            for i, name in enumerate(names):
                data = archive.read(name)
                mime = mimetypes.guess_type(name)[0] or "image/jpeg"
                chapters.append((i, f"Page {i + 1}", self._chapter_html(data, mime)))
            return chapters
        finally:
            archive.close()

    async def count_chapters(self, cbz_path: str) -> int:
        """Count pages.

        Args:
            cbz_path: Path to the .cbz file.

        Returns:
            Number of page images.
        """
        archive = self._open(cbz_path)
        try:
            return len(self._image_names(archive))
        finally:
            archive.close()

    async def get_table_of_contents(self, cbz_path: str) -> list[dict[str, Any]]:
        """Build a flat page TOC.

        Args:
            cbz_path: Path to the .cbz file.

        Returns:
            TOC item dicts with index/title/level.
        """
        count = await self.count_chapters(cbz_path)
        return [
            {"index": i, "title": f"Page {i + 1}", "level": 1} for i in range(count)
        ]

    async def get_single_chapter(self, cbz_path: str, chapter_index: int) -> tuple[str, str, int]:
        """Extract one page as a chapter.

        Args:
            cbz_path: Path to the .cbz file.
            chapter_index: Zero-based page index.

        Returns:
            Tuple of (page_html, "Page N", total_pages).
        """
        archive = self._open(cbz_path)
        try:
            names = self._image_names(archive)
            if chapter_index < 0 or chapter_index >= len(names):
                from app.exceptions import ResourceNotFoundError

                raise ResourceNotFoundError(
                    f"Page {chapter_index} not found (total: {len(names)})",
                    {"path": cbz_path, "index": chapter_index},
                )
            name = names[chapter_index]
            data = archive.read(name)
            mime = mimetypes.guess_type(name)[0] or "image/jpeg"
            return self._chapter_html(data, mime), f"Page {chapter_index + 1}", len(names)
        finally:
            archive.close()
