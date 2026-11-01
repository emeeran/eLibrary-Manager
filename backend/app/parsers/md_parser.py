"""Markdown (.md) format parser (spec 008 v1.2, Moon+ parity formats).

Renders Markdown to HTML with a small built-in converter (headings, emphasis,
inline code, fenced code blocks, lists, links, blockquotes, paragraphs) so no
new dependency is added. Top-level ``# `` headings split the document into
reader chapters; a document without them is a single chapter.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.exceptions import EbookParsingError
from app.logging_config import get_logger
from app.schemas import BookCreate

logger = get_logger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _md_inline(text: str) -> str:
    """Render inline Markdown (emphasis, code, links) to HTML.

    Args:
        text: A single line / paragraph of Markdown.

    Returns:
        HTML-escaped-ish inline HTML.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    return text


def _md_block_to_html(block_lines: list[str]) -> str:
    """Render one block of Markdown lines to HTML.

    Args:
        block_lines: Lines belonging to one logical block.

    Returns:
        HTML string for the block.
    """
    if not block_lines:
        return ""
    first = block_lines[0]

    fenced = re.match(r"^```(\w*)\s*$", first)
    if fenced:
        code_lines = block_lines[1:]
        if code_lines and code_lines[-1].startswith("```"):
            code_lines = code_lines[:-1]
        code = "\n".join(code_lines).replace("&", "&amp;").replace("<", "&lt;")
        return f"<pre><code>{code}</code></pre>"

    if first.lstrip().startswith("> "):
        quote = "<br/>".join(_md_inline(line.lstrip()[2:]) for line in block_lines)
        return f"<blockquote>{quote}</blockquote>"

    if re.match(r"^\s*[-*+]\s+", first):
        items = [
            f"<li>{_md_inline(re.sub(r'^\s*[-*+]\s+', '', line))}</li>"
            for line in block_lines
        ]
        return f"<ul>{''.join(items)}</ul>"

    if re.match(r"^\s*\d+\.\s+", first):
        items = [
            f"<li>{_md_inline(re.sub(r'^\s*\d+\.\s+', '', line))}</li>"
            for line in block_lines
        ]
        return f"<ol>{''.join(items)}</ol>"

    if first.strip().startswith(("---", "***")) and len(first.strip()) >= 3 and set(first.strip()) <= {"-", "*", "_"}:
        return "<hr/>"

    paragraph = " ".join(line.strip() for line in block_lines)
    return f"<p>{_md_inline(paragraph)}</p>"


def markdown_to_html(source: str) -> str:
    """Convert a Markdown document to HTML.

    Args:
        source: Full Markdown text.

    Returns:
        HTML string of block-level elements.
    """
    html_parts: list[str] = []
    block: list[str] = []
    in_fence = False

    for line in source.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            block.append(line)
            if not in_fence:
                html_parts.append(_md_block_to_html(block))
                block = []
            continue
        if in_fence:
            block.append(line)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            if block:
                html_parts.append(_md_block_to_html(block))
                block = []
            level = min(len(heading.group(1)) + 1, 6)  # doc title is h1
            html_parts.append(
                f"<h{level}>{_md_inline(heading.group(2))}</h{level}>"
            )
            continue

        if not line.strip():
            if block:
                html_parts.append(_md_block_to_html(block))
                block = []
            continue

        block.append(line)

    if block:
        html_parts.append(_md_block_to_html(block))
    return "\n".join(html_parts)


class MDParser:
    """Parser for Markdown (.md) documents.

    Top-level ``# `` headings become chapter boundaries (the document title
    heading starts chapter 1); a document without them is a single chapter.
    """

    SUPPORTED_FORMAT = "MD"

    def __init__(self, covers_path: str = "./static_covers") -> None:
        """Initialize the parser (covers_path kept for interface parity).

        Args:
            covers_path: Directory for cover images (unused for Markdown).
        """
        self.covers_path = Path(covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)

    def _read(self, md_path: str) -> str:
        """Read the Markdown file.

        Args:
            md_path: Path to the .md file.

        Returns:
            The document text.

        Raises:
            EbookParsingError: If the file cannot be decoded.
        """
        try:
            return Path(md_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise EbookParsingError(
                f"Cannot read Markdown file: {exc}", {"path": md_path}
            ) from exc

    # ------------------------------------------------------------------ #
    # Unified parser interface
    # ------------------------------------------------------------------ #

    async def extract_metadata(self, md_path: str) -> BookCreate:
        """Extract metadata: first ``# `` heading as title, filename fallback.

        Args:
            md_path: Path to the .md file.

        Returns:
            BookCreate with title and word estimate fields unset.

        Raises:
            EbookParsingError: If the file cannot be read.
        """
        source = self._read(md_path)
        title = None
        for line in source.splitlines():
            match = _HEADING_RE.match(line)
            if match and len(match.group(1)) == 1:
                title = match.group(2)
                break
        path = Path(md_path)
        return BookCreate(
            title=title or path.stem,
            path=str(path.resolve()),
            file_size=path.stat().st_size,
            format=self.SUPPORTED_FORMAT,
        )

    async def extract_cover(self, md_path: str) -> str | None:
        """Markdown documents have no cover image.

        Args:
            md_path: Path to the .md file.

        Returns:
            Always None.
        """
        return None

    async def get_chapters(self, md_path: str) -> list[tuple[int, str, str]]:
        """Split the document into chapters on top-level ``# `` headings.

        Args:
            md_path: Path to the .md file.

        Returns:
            List of (chapter_index, title, content_html).

        Raises:
            EbookParsingError: If the file cannot be read.
        """
        source = self._read(md_path)
        lines = source.splitlines()

        sections: list[tuple[str, list[str]]] = []
        doc_title: str | None = None
        current_title: str | None = None
        current_lines: list[str] = []

        for line in lines:
            match = _HEADING_RE.match(line)
            if match and len(match.group(1)) == 1:
                if doc_title is None:
                    # Document title heading — start chapter 1 beneath it.
                    doc_title = match.group(2)
                    current_title = doc_title
                else:
                    if current_lines:
                        sections.append((current_title or doc_title or "Section", current_lines))
                    current_title = match.group(2)
                    current_lines = []
                continue
            current_lines.append(line)

        if current_lines or current_title is not None:
            sections.append((current_title or doc_title or Path(md_path).stem, current_lines))

        if not sections:
            # No headings at all: single chapter from the whole document.
            sections = [(Path(md_path).stem, lines)]

        chapters: list[tuple[int, str, str]] = []
        for i, (title, section_lines) in enumerate(sections):
            chapters.append((i, title, markdown_to_html("\n".join(section_lines))))
        return chapters

    async def count_chapters(self, md_path: str) -> int:
        """Count chapters.

        Args:
            md_path: Path to the .md file.

        Returns:
            Number of chapters (minimum 1).
        """
        return len(await self.get_chapters(md_path))

    async def get_table_of_contents(self, md_path: str) -> list[dict[str, Any]]:
        """Build a flat TOC from chapter titles.

        Args:
            md_path: Path to the .md file.

        Returns:
            TOC item dicts with index/title/level.
        """
        chapters = await self.get_chapters(md_path)
        return [
            {"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)
        ]

    async def get_single_chapter(self, md_path: str, chapter_index: int) -> tuple[str, str, int]:
        """Extract one chapter.

        Args:
            md_path: Path to the .md file.
            chapter_index: Zero-based chapter index.

        Returns:
            Tuple of (content_html, title, total_chapters).
        """
        chapters = await self.get_chapters(md_path)
        if chapter_index < 0 or chapter_index >= len(chapters):
            from app.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError(
                f"Chapter {chapter_index} not found (total: {len(chapters)})",
                {"path": md_path, "index": chapter_index},
            )
        _, title, content = chapters[chapter_index]
        return content, title, len(chapters)
