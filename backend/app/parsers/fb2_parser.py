"""FictionBook2 (FB2) format parser (spec 008 v1.2, Moon+ parity formats).

FB2 is a single XML document: ``<description>`` carries metadata, the
``<binary>`` elements carry base64 images (including the cover), and each
``<body><section>`` maps naturally to a reader chapter. Parsing uses only the
standard library (``xml.etree.ElementTree``) plus BeautifulSoup for the
section-body → HTML conversion, so no new dependency is introduced.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.exceptions import EbookParsingError
from app.logging_config import get_logger
from app.schemas import BookCreate

logger = get_logger(__name__)


class FB2Parser:
    """Parser for FictionBook2 (.fb2) ebooks.

    Sections of the first ``<body>`` become chapters; inline FB2 markup
    (``<p>``, ``<emph>``, ``<strong>``, ``<subtitle>``, ``<empty-line>``) is
    converted to plain HTML.
    """

    SUPPORTED_FORMAT = "FB2"

    def __init__(self, covers_path: str = "./static_covers") -> None:
        """Initialize the parser.

        Args:
            covers_path: Directory to store extracted cover images.
        """
        self.covers_path = Path(covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    def _parse(self, fb2_path: str) -> ElementTree.Element:
        """Parse the FB2 XML document.

        Args:
            fb2_path: Path to the .fb2 file.

        Returns:
            The root ``FictionBook`` element.

        Raises:
            EbookParsingError: If the file is not well-formed FB2 XML.
        """
        try:
            tree = ElementTree.parse(fb2_path)
            return tree.getroot()
        except ElementTree.ParseError as exc:
            raise EbookParsingError(
                f"Failed to parse FB2: {exc}", {"path": fb2_path}
            ) from exc
        except OSError as exc:
            raise EbookParsingError(
                f"Cannot read FB2 file: {exc}", {"path": fb2_path}
            ) from exc

    @staticmethod
    def _local(tag: str) -> str:
        """Return an element tag's local name (namespaces stripped)."""
        return tag.rsplit("}", 1)[-1]

    def _find_child(self, element: ElementTree.Element, name: str) -> ElementTree.Element | None:
        """Find the first direct child with a local tag name."""
        for child in element:
            if self._local(child.tag) == name:
                return child
        return None

    def _find_descendant(
        self, element: ElementTree.Element, *names: str
    ) -> ElementTree.Element | None:
        """Walk a fixed descendant path of local tag names."""
        current: ElementTree.Element | None = element
        for name in names:
            current = self._find_child(current, name) if current is not None else None
        return current

    @staticmethod
    def _text(element: ElementTree.Element | None) -> str | None:
        """Return stripped text content of an element, or None."""
        if element is None or element.text is None:
            return None
        text = element.text.strip()
        return text or None

    def _render_inline(self, element: ElementTree.Element) -> str:
        """Render an FB2 paragraph's inline markup to HTML.

        Args:
            element: A ``p`` (or similar) element.

        Returns:
            HTML string with emph → <em>, strong → <strong>.
        """
        parts = [element.text or ""]
        for child in element:
            name = self._local(child.tag)
            inner = "".join(child.itertext())
            if name == "emph":
                parts.append(f"<em>{inner}</em>")
            elif name == "strong":
                parts.append(f"<strong>{inner}</strong>")
            else:
                parts.append(inner)
            parts.append(child.tail or "")
        return "".join(parts).strip()

    def _section_to_html(self, section: ElementTree.Element) -> str:
        """Convert a FB2 ``<section>`` body into simple HTML.

        Args:
            section: The section element (title + content elements).

        Returns:
            HTML string with p/em/strong/h4/hr elements. The ``<title>``
            subtree is excluded (it becomes the chapter title).
        """
        html_parts: list[str] = []
        for element in section:
            name = self._local(element.tag)
            if name == "title":
                continue  # handled as the chapter title
            if name == "p":
                text = self._render_inline(element)
                if text:
                    html_parts.append(f"<p>{text}</p>")
            elif name == "subtitle":
                text = "".join(element.itertext()).strip()
                if text:
                    html_parts.append(f"<h4>{text}</h4>")
            elif name == "empty-line":
                html_parts.append("<hr/>")
            elif name == "cite":
                text = "".join(element.itertext()).strip()
                if text:
                    html_parts.append(f"<blockquote>{text}</blockquote>")
            elif name in ("poem", "epigraph"):
                text = "".join(element.itertext()).strip()
                if text:
                    html_parts.append(f"<p><em>{text}</em></p>")
        return "\n".join(html_parts)

    # ------------------------------------------------------------------ #
    # Unified parser interface
    # ------------------------------------------------------------------ #

    async def extract_metadata(self, fb2_path: str) -> BookCreate:
        """Extract metadata from an FB2 file.

        Args:
            fb2_path: Path to the .fb2 file.

        Returns:
            BookCreate with title/author/description/language/genre subjects.

        Raises:
            EbookParsingError: If parsing fails.
        """
        root = self._parse(fb2_path)
        title_info = self._find_descendant(root, "description", "title-info")
        publish_info = self._find_descendant(root, "description", "publish-info")

        title = self._text(self._find_child(title_info, "book-title")) if title_info else None
        if not title:
            title = Path(fb2_path).stem

        author = None
        if title_info is not None:
            first = self._find_descendant(title_info, "author", "first-name")
            middle = self._find_descendant(title_info, "author", "middle-name")
            last = self._find_descendant(title_info, "author", "last-name")
            parts = [
                self._text(first),
                self._text(middle),
                self._text(last),
            ]
            author = " ".join(p for p in parts if p) or None

        genres = [
            self._text(g)
            for g in (title_info if title_info is not None else [])
            if self._local(g.tag) == "genre" and self._text(g)
        ]

        path = Path(fb2_path)
        return BookCreate(
            title=title,
            author=author,
            path=str(path.resolve()),
            file_size=path.stat().st_size,
            format=self.SUPPORTED_FORMAT,
            description=self._text(self._find_child(title_info, "annotation"))
            if title_info
            else None,
            language=self._text(self._find_child(title_info, "lang")) if title_info else None,
            publisher=self._text(self._find_child(publish_info, "publisher"))
            if publish_info is not None
            else None,
            publish_date=self._text(self._find_child(publish_info, "year"))
            if publish_info is not None
            else None,
            subjects=genres,
        )

    async def extract_cover(self, fb2_path: str) -> str | None:
        """Extract the cover image (``<binary id="cover.*">``) to disk.

        Args:
            fb2_path: Path to the .fb2 file.

        Returns:
            Path to the written cover image, or None when absent/corrupt.
        """
        root = self._parse(fb2_path)
        cover_id = None
        title_info = self._find_descendant(root, "description", "title-info")
        if title_info is not None:
            coverpage = self._find_child(title_info, "coverpage")
            if coverpage is not None:
                image = self._find_child(coverpage, "image")
                if image is not None:
                    cover_id = image.get("l:href") or image.get(
                        "{http://www.w3.org/1999/xlink}href"
                    )
                    if cover_id and cover_id.startswith("#"):
                        cover_id = cover_id[1:]
        if not cover_id:
            return None

        for binary in root:
            if self._local(binary.tag) != "binary" or binary.get("id") != cover_id:
                continue
            try:
                data = base64.b64decode(binary.text or "", validate=False)
            except (binascii.Error, ValueError):
                return None
            if not data:
                return None

            content_type = binary.get("content-type", "image/jpeg")
            ext = ".png" if "png" in content_type else ".jpg"
            digest = hashlib.sha256(data).hexdigest()[:16]
            cover_file = self.covers_path / f"fb2_{digest}{ext}"
            cover_file.write_bytes(data)
            return str(cover_file)
        return None

    async def get_chapters(self, fb2_path: str) -> list[tuple[int, str, str]]:
        """Return chapters: one per ``<section>`` of the first body.

        A book with no sections is treated as a single chapter.

        Args:
            fb2_path: Path to the .fb2 file.

        Returns:
            List of (chapter_index, title, content_html).

        Raises:
            EbookParsingError: If parsing fails.
        """
        root = self._parse(fb2_path)
        body = self._find_child(root, "body")
        if body is None:
            raise EbookParsingError("FB2 has no body element", {"path": fb2_path})

        chapters: list[tuple[int, str, str]] = []
        for element in body:
            if self._local(element.tag) != "section":
                continue
            title_el = self._find_descendant(element, "title", "p")
            if title_el is None:
                title_el = self._find_child(element, "title")
            title = self._text(title_el) or f"Section {len(chapters) + 1}"
            content = self._section_to_html(element)
            chapters.append((len(chapters), title, content))

        if not chapters:
            # Single-body book: the whole body is one chapter.
            content = self._section_to_html(body)
            chapters = [(0, Path(fb2_path).stem, content)]
        return chapters

    async def count_chapters(self, fb2_path: str) -> int:
        """Count chapters (sections).

        Args:
            fb2_path: Path to the .fb2 file.

        Returns:
            Number of sections (minimum 1).
        """
        return len(await self.get_chapters(fb2_path))

    async def get_table_of_contents(self, fb2_path: str) -> list[dict[str, Any]]:
        """Build a flat TOC from the section titles.

        Args:
            fb2_path: Path to the .fb2 file.

        Returns:
            TOC item dicts with index/title/level.
        """
        chapters = await self.get_chapters(fb2_path)
        return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]

    async def get_single_chapter(self, fb2_path: str, chapter_index: int) -> tuple[str, str, int]:
        """Extract one chapter without returning the whole list.

        Args:
            fb2_path: Path to the .fb2 file.
            chapter_index: Zero-based chapter index.

        Returns:
            Tuple of (content_html, title, total_chapters).
        """
        chapters = await self.get_chapters(fb2_path)
        if chapter_index < 0 or chapter_index >= len(chapters):
            from app.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError(
                f"Chapter {chapter_index} not found (total: {len(chapters)})",
                {"path": fb2_path, "index": chapter_index},
            )
        _, title, content = chapters[chapter_index]
        return content, title, len(chapters)
