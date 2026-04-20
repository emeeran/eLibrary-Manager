"""PDF format parser using PyMuPDF (fitz) for text and image extraction."""

import hashlib
import html
import os
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image
from pypdf import PdfReader

from app.exceptions import EbookParsingError
from app.logging_config import get_logger
from app.parsers.image_service import BookImageService
from app.schemas import BookCreate

logger = get_logger(__name__)


class PDFParser:
    """Parser for PDF format ebooks.

    Handles PDF file parsing, metadata extraction, and page-by-page
    content retrieval with formatting preservation.
    """

    SUPPORTED_FORMAT = "PDF"

    def __init__(
        self,
        covers_path: str = "./static_covers",
        book_images_path: str = "./static_book_images",
    ) -> None:
        """Initialize PDF parser.

        Args:
            covers_path: Directory to store cover images.
            book_images_path: Directory for extracted inline images.
        """
        self.covers_path = Path(covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)
        self._image_service = BookImageService(book_images_path)

    async def extract_metadata(self, pdf_path: str) -> BookCreate:
        """Extract metadata from PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            BookCreate object with extracted metadata

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            reader = PdfReader(pdf_path)

            # PDF metadata is often limited, use filename as title
            filename = Path(pdf_path).stem
            title = filename.replace("-", " ").replace("_", " ").title()

            # Initialize metadata
            author = "Unknown"
            publisher = None
            publish_date = None
            description = None

            # Try to get metadata from PDF info
            subjects = []
            if reader.metadata:
                if reader.metadata.get("/Title"):
                    title = reader.metadata.get("/Title")
                if reader.metadata.get("/Author"):
                    author = reader.metadata.get("/Author")
                if reader.metadata.get("/Creator"):
                    publisher = reader.metadata.get("/Creator")
                if reader.metadata.get("/CreationDate"):
                    # PDF dates are in format D:YYYYMMDDHHmmss
                    date_str = reader.metadata.get("/CreationDate", "")
                    if date_str.startswith("D:"):
                        publish_date = date_str[2:6]  # Extract year
                subject_val = reader.metadata.get("/Subject")
                if subject_val:
                    description = subject_val
                if reader.metadata.get("/Keywords"):
                    keywords = reader.metadata.get("/Keywords", "")
                    subjects = [k.strip() for k in keywords.split(",") if k.strip()]
                if subject_val and subject_val not in subjects:
                    subjects.append(subject_val)

            # Get file size and page count
            file_size = os.path.getsize(pdf_path)
            total_pages = len(reader.pages)

            logger.info(f"Extracted PDF metadata: {title} by {author} ({total_pages} pages)")

            return BookCreate(
                title=title,
                author=author,
                path=pdf_path,
                format="PDF",
                file_size=file_size,
                publisher=publisher,
                publish_date=publish_date,
                description=description,
                total_pages=total_pages,
                subjects=subjects
            )

        except Exception as e:
            raise EbookParsingError(
                f"Failed to parse PDF: {str(e)}",
                {"path": pdf_path, "error": str(e)}
            ) from e

    async def extract_cover(self, pdf_path: str) -> Optional[str]:
        """Extract cover from PDF by rendering the first page.

        Uses PyMuPDF to render the first page as an image for
        use as the book cover.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Path to saved cover image, or None if extraction fails
        """
        try:
            # Open PDF with PyMuPDF
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                logger.warning(f"PDF has no pages: {pdf_path}")
                doc.close()
                return None

            # Get the first page
            page = doc[0]

            # Render page to image (2x resolution for quality)
            mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()

            # Resize to standard cover dimensions (max 600x900)
            max_width = 600
            max_height = 900
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            # Generate unique filename using path hash (SHA256 for security)
            path_hash = hashlib.sha256(pdf_path.encode()).hexdigest()[:32]
            cover_filename = f"{path_hash}.jpg"
            cover_path = self.covers_path / cover_filename

            # Save as JPEG with good quality
            img.save(cover_path, "JPEG", quality=85, optimize=True)

            logger.info(f"Extracted PDF cover from first page: {pdf_path}")
            return str(cover_path)

        except Exception as e:
            logger.warning(f"Failed to extract PDF cover: {e}")
            return None

    async def get_chapters(self, pdf_path: str) -> list[tuple[int, str, str]]:
        """Extract and format PDF text for readable, selectable display.

        Note: PDFs don't have native chapters, so we treat each page
        as a "chapter" for reading progress. Text is extracted with
        formatting preserved, making it fully selectable, searchable,
        and compatible with screen readers.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of tuples: (page_index, page_title, formatted_html)

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            doc = fitz.open(pdf_path)
            pages: list[tuple[int, str, str]] = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                try:
                    html_content = self._render_page_to_html(
                        page, page_num, doc=doc, pdf_path=pdf_path
                    )
                    title = f"Page {page_num + 1}"
                    pages.append((page_num, title, html_content))
                except Exception as e:
                    logger.warning(f"Failed to parse page {page_num}: {e}")
                    try:
                        plain_text = page.get_text("text")
                        if plain_text.strip():
                            html_content = f'<div class="pdf-page-text"><p class="pdf-text">{self._escape_html(plain_text)}</p></div>'
                            pages.append((page_num, f"Page {page_num + 1}", html_content))
                        else:
                            pages.append((page_num, f"Page {page_num + 1}", '<div class="pdf-page-text"><p class="pdf-empty-page"></p></div>'))
                    except Exception:
                        pages.append((page_num, f"Page {page_num + 1}", '<div class="pdf-page-text"><p class="pdf-empty-page"></p></div>'))

            doc.close()
            logger.info(f"Parsed {len(pages)} pages from PDF with formatting")
            return pages

        except Exception as e:
            raise EbookParsingError(
                f"Failed to parse PDF: {str(e)}",
                {"path": pdf_path}
            )

    async def get_single_chapter(
        self, pdf_path: str, chapter_index: int
    ) -> tuple[str, str, int]:
        """Extract a single chapter (page) without parsing the entire PDF.

        Args:
            pdf_path: Path to PDF file.
            chapter_index: Zero-based page index.

        Returns:
            Tuple of (content_html, title, total_pages).

        Raises:
            EbookParsingError: If parsing fails.
            ResourceNotFoundError: If page index is out of range.
        """
        try:
            doc = fitz.open(pdf_path)
            total = len(doc)

            if chapter_index < 0 or chapter_index >= total:
                doc.close()
                from app.exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(
                    f"Page {chapter_index} not found (total: {total})",
                    {"path": pdf_path, "index": chapter_index}
                )

            page = doc[chapter_index]
            try:
                html_content = self._render_page_to_html(
                    page, chapter_index, doc=doc, pdf_path=pdf_path
                )
            except Exception as e:
                logger.warning(f"Failed to parse page {chapter_index}: {e}")
                plain_text = page.get_text("text")
                if plain_text.strip():
                    html_content = f'<div class="pdf-page-text"><p class="pdf-text">{self._escape_html(plain_text)}</p></div>'
                else:
                    html_content = '<div class="pdf-page-text"><p class="pdf-empty-page"></p></div>'

            title = f"Page {chapter_index + 1}"
            doc.close()
            return html_content, title, total

        except EbookParsingError:
            raise
        except Exception as e:
            raise EbookParsingError(
                f"Failed to parse PDF page: {str(e)}",
                {"path": pdf_path, "index": chapter_index}
            ) from e

    def _render_page_to_html(
        self,
        page: "fitz.Page",
        page_num: int,
        doc: "fitz.Document | None" = None,
        pdf_path: str | None = None,
    ) -> str:
        """Render a single PDF page to formatted HTML.

        Extracts text with formatting (bold, italic, headings, indentation),
        inline images, and preserves reading order.  Consecutive lines that
        share the same left-edge and font-size are merged into a single
        paragraph for cleaner rendering.

        Args:
            page: PyMuPDF Page object.
            page_num: Page number (0-based) for logging.
            doc: Open PyMuPDF Document (needed for image extraction).
            pdf_path: Path to PDF file (needed for image URL generation).

        Returns:
            HTML string of the page content.
        """
        text_dict = page.get_text("dict")

        # Collect image positions for interleaving with text
        image_insertions: list[tuple[float, str]] = []
        if doc is not None and pdf_path is not None:
            image_insertions = self._extract_page_images(page, doc, pdf_path)

        # Detect tables and their bounding boxes (skip text inside tables)
        table_bboxes: list[tuple[float, float, float, float]] = []
        table_insertions: list[tuple[float, str]] = []
        try:
            tables = page.find_tables()
            for table in tables:
                table_html = self._render_table_to_html(table)
                if table_html:
                    bbox = table.bbox
                    table_bboxes.append(bbox)
                    table_insertions.append((bbox[1], table_html))
        except Exception:
            pass

        def _is_in_table(bbox: list | tuple) -> bool:
            bx0, by0, bx1, by1 = bbox[0], bbox[1], bbox[2], bbox[3]
            for tx0, ty0, tx1, ty1 in table_bboxes:
                if bx0 < tx1 and bx1 > tx0 and by0 < ty1 and by1 > ty0:
                    return True
            return False

        # --- Phase 1: collect all lines as flat records -------------------
        LineRec = dict  # typed for readability
        lines: list[LineRec] = []

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            block_bbox = block.get("bbox", [0, 0, 0, 0])
            if table_bboxes and _is_in_table(block_bbox):
                continue
            for line in block.get("lines", []):
                line_bbox = line.get("bbox", [0, 0, 0, 0])
                spans = line.get("spans", [])
                if not spans:
                    continue

                # Build line text with formatting
                span_parts: list[str] = []
                total_size = 0.0
                size_count = 0
                all_bold = True
                all_italic = True
                has_text = False

                for span in spans:
                    text = span.get("text", "")
                    # Keep trailing space for word-joining across spans
                    stripped = text.strip()
                    if not stripped:
                        continue
                    has_text = True
                    size = span.get("size", 12)
                    flags = span.get("flags", 0)
                    is_bold = bool(flags & 2**4)
                    is_italic = bool(flags & 2**1)
                    if not is_bold:
                        all_bold = False
                    if not is_italic:
                        all_italic = False

                    css_classes: list[str] = []
                    if is_bold:
                        css_classes.append("pdf-bold")
                    if is_italic:
                        css_classes.append("pdf-italic")
                    class_attr = f' class="{" ".join(css_classes)}"' if css_classes else ''
                    span_parts.append(f'<span{class_attr}>{self._escape_html(stripped)}</span>')
                    total_size += size
                    size_count += 1

                if not has_text:
                    continue

                avg_size = total_size / size_count if size_count > 0 else 12
                plain_text = " ".join(
                    s.get("text", "").strip()
                    for s in spans
                    if s.get("text", "").strip()
                )

                lines.append({
                    "y": line_bbox[1],
                    "x": line_bbox[0],
                    "x1": line_bbox[2],
                    "y1": line_bbox[3],
                    "html": " ".join(span_parts),
                    "size": avg_size,
                    "bold": all_bold,
                    "italic": all_italic,
                    "text": plain_text,
                })

        # --- Phase 2: determine dominant font size -----------------------
        size_counts: dict[float, int] = {}
        for rec in lines:
            rounded = round(rec["size"] * 2) / 2  # round to 0.5
            size_counts[rounded] = size_counts.get(rounded, 0) + 1
        dominant_size = max(size_counts, key=size_counts.get) if size_counts else 12

        # --- Phase 3: group consecutive lines into paragraphs ------------
        # Lines are grouped when they share similar x-position, font-size,
        # and are close vertically (within 1.5x line-height).
        groups: list[list[LineRec]] = []
        current_group: list[LineRec] = []

        for rec in lines:
            if not current_group:
                current_group.append(rec)
                continue

            prev = current_group[-1]
            y_gap = rec["y"] - prev["y1"]
            same_x = abs(rec["x"] - prev["x"]) < 15
            same_size = abs(rec["size"] - prev["size"]) < 2
            line_height_est = prev["size"] * 1.4
            is_close = y_gap < max(line_height_est * 1.5, 8)

            if same_x and same_size and is_close:
                current_group.append(rec)
            else:
                groups.append(current_group)
                current_group = [rec]

        if current_group:
            groups.append(current_group)

        # --- Phase 4: render groups into HTML ----------------------------
        block_positions: list[tuple[float, str]] = []

        for group in groups:
            if not group:
                continue
            top_y = group[0]["y"]
            avg_size = sum(r["size"] for r in group) / len(group)
            left_x = min(r["x"] for r in group)
            group_text = " ".join(r["text"] for r in group)
            group_html = " ".join(r["html"] for r in group)
            is_bold = all(r["bold"] for r in group)
            is_all_caps = group_text == group_text.upper() and len(group_text) > 4

            # Determine element type based on font size relative to dominant
            size_ratio = avg_size / dominant_size if dominant_size > 0 else 1

            if size_ratio > 1.4 or (size_ratio > 1.2 and is_bold and is_all_caps):
                block_positions.append((top_y, f'<h2 class="pdf-heading">{group_html}</h2>'))
            elif size_ratio > 1.15 or (size_ratio > 1.05 and is_bold):
                block_positions.append((top_y, f'<h3 class="pdf-subheading">{group_html}</h3>'))
            else:
                # Normal paragraph — calculate indent level (0, 1, 2, 3...)
                # based on position relative to the leftmost content on the page
                indent_level = 0
                if left_x > 72:
                    indent_level = min(4, int((left_x - 36) / 72))
                indent_style = f' style="margin-left: {indent_level * 1.5}em;"' if indent_level > 0 else ''
                block_positions.append((top_y, f'<p class="pdf-line"{indent_style}>{group_html}</p>'))

        # --- Phase 5: interleave with images and tables ------------------
        all_elements = block_positions + image_insertions + table_insertions
        all_elements.sort(key=lambda x: x[0])

        html_parts = ['<div class="pdf-page-text">']
        for _pos, element_html in all_elements:
            html_parts.append(element_html)
        html_parts.append('</div>')

        html_content = "\n".join(html_parts)

        text_only = html_content.replace('<div class="pdf-page-text">', '').replace('</div>', '').strip()
        if not text_only:
            return '<div class="pdf-page-text"><p class="pdf-empty-page"></p></div>'

        return html_content

    def _extract_page_images(
        self,
        page: "fitz.Page",
        doc: "fitz.Document",
        pdf_path: str,
    ) -> list[tuple[float, str]]:
        """Extract images from a PDF page and return positioned HTML fragments.

        Args:
            page: PyMuPDF Page object.
            doc: Open PyMuPDF Document.
            pdf_path: Path to the PDF file.

        Returns:
            List of (y_position, html_string) tuples for interleaving.
        """
        insertions: list[tuple[float, str]] = []

        try:
            images = page.get_images(full=True)
            if not images:
                return insertions

            img_dir = self._image_service.get_image_dir(pdf_path)

            for img_info in images:
                xref = img_info[0]

                filename = self._image_service.save_pdf_image(doc, xref, img_dir)
                if not filename:
                    continue

                url = self._image_service.get_image_url(pdf_path, filename)

                # Get image position on page for correct interleaving
                y_pos = 0.0
                try:
                    rects = page.get_image_rects(xref)
                    if rects:
                        y_pos = rects[0].y0
                except Exception:
                    pass

                insertions.append((
                    y_pos,
                    f'<figure class="pdf-image"><img src="{url}" alt="Page image" loading="lazy" /></figure>'
                ))

        except Exception as e:
            logger.warning(f"Failed to extract images from page: {e}")

        return insertions

    def _render_table_to_html(self, table: "fitz.Table") -> str:
        """Convert a PyMuPDF Table to structured HTML.

        Args:
            table: PyMuPDF Table object from ``page.find_tables()``.

        Returns:
            HTML ``<table>`` string, or empty string on failure.
        """
        try:
            rows = table.extract()
            if not rows:
                return ""

            html_parts = ['<table class="pdf-table">']

            for i, row in enumerate(rows):
                tag = "th" if i == 0 else "td"
                html_parts.append("<tr>")
                for cell in row:
                    cell_text = self._escape_html(str(cell or "").strip())
                    html_parts.append(f"<{tag}>{cell_text}</{tag}>")
                html_parts.append("</tr>")

            html_parts.append("</table>")
            return "\n".join(html_parts)

        except Exception as e:
            logger.warning(f"Failed to render PDF table: {e}")
            return ""

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return html.escape(text, quote=True)

    async def count_chapters(self, pdf_path: str) -> int:
        """Count the number of pages in a PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Number of pages
        """
        try:
            reader = PdfReader(pdf_path)
            return len(reader.pages)
        except Exception as e:
            raise EbookParsingError(
                f"Failed to count pages: {str(e)}",
                {"path": pdf_path}
            ) from e

    async def get_smart_chapters(self, pdf_path: str) -> list[tuple[int, str, str]]:
        """Group PDF pages into logical chapters using outlines or font heuristics.

        Falls back to 1-page-per-chapter when no structure is detected.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            List of tuples: (chapter_index, chapter_title, concatenated_html).
        """
        try:
            doc = fitz.open(pdf_path)
            toc = doc.get_toc()  # [(level, title, page_number), ...]
            total_pages = len(doc)

            if len(toc) >= 2:
                chapters = self._group_by_outline(doc, toc, pdf_path)
            else:
                chapters = self._group_by_font_heuristic(doc, pdf_path)

            # Fallback: if no structure found, use per-page chapters
            if not chapters:
                doc.close()
                return await self.get_chapters(pdf_path)

            doc.close()
            logger.info(
                f"Smart-grouped PDF into {len(chapters)} chapters "
                f"(from {total_pages} pages)"
            )
            return chapters

        except Exception as e:
            raise EbookParsingError(
                f"Failed to smart-group PDF: {str(e)}",
                {"path": pdf_path}
            ) from e

    def _group_by_outline(
        self,
        doc: "fitz.Document",
        toc: list[tuple[int, str, int]],
        pdf_path: str,
    ) -> list[tuple[int, str, str]]:
        """Group pages by PDF outline/bookmarks.

        Args:
            doc: Open PyMuPDF Document.
            toc: Table of contents from ``doc.get_toc()``.
            pdf_path: Path to the PDF file.

        Returns:
            List of (index, title, html) tuples.
        """
        chapters: list[tuple[int, str, str]] = []

        # Build page ranges from top-level (level 1) TOC entries
        top_entries = [(lvl, title, pg) for lvl, title, pg in toc if lvl == 1]

        if len(top_entries) < 2:
            return []

        for i, (_lvl, title, start_page) in enumerate(top_entries):
            # Pages are 1-indexed in TOC
            start = start_page - 1
            if start < 0:
                start = 0

            # End is start of next entry, or last page
            if i + 1 < len(top_entries):
                end = top_entries[i + 1][2] - 1
            else:
                end = len(doc)

            # Render all pages in this chapter range
            page_htmls: list[str] = []
            for pg in range(start, end):
                try:
                    html = self._render_page_to_html(
                        doc[pg], pg, doc=doc, pdf_path=pdf_path
                    )
                    page_htmls.append(html)
                except Exception as e:
                    logger.warning(f"Failed to render page {pg}: {e}")

            if page_htmls:
                chapters.append((len(chapters), title, "\n".join(page_htmls)))

        return chapters

    def _group_by_font_heuristic(
        self,
        doc: "fitz.Document",
        pdf_path: str,
    ) -> list[tuple[int, str, str]]:
        """Group pages by detecting large font text (chapter headings).

        Scans each page looking for text with font size > 18 near the top
        of the page as a chapter boundary indicator.

        Args:
            doc: Open PyMuPDF Document.
            pdf_path: Path to the PDF file.

        Returns:
            List of (index, title, html) tuples.
        """
        total_pages = len(doc)
        if total_pages == 0:
            return []

        chapter_starts: list[tuple[int, str]] = []  # (page_index, title)

        for pg in range(total_pages):
            page = doc[pg]
            text_dict = page.get_text("dict")

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                block_top = block.get("bbox", [0, 0, 0, 0])[1]
                # Only check near the top of the page
                if block_top > 100:
                    continue

                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    for span in spans:
                        text = span.get("text", "").strip()
                        size = span.get("size", 12)
                        if size > 18 and len(text) > 2:
                            # This looks like a chapter heading
                            chapter_starts.append((pg, text))
                            break
                    if chapter_starts and chapter_starts[-1][0] == pg:
                        break
                if chapter_starts and chapter_starts[-1][0] == pg:
                    break

        # Need at least 2 chapter starts to be meaningful
        if len(chapter_starts) < 2:
            return []

        chapters: list[tuple[int, str, str]] = []
        for i, (start_pg, title) in enumerate(chapter_starts):
            end_pg = chapter_starts[i + 1][0] if i + 1 < len(chapter_starts) else total_pages

            page_htmls: list[str] = []
            for pg in range(start_pg, end_pg):
                try:
                    html = self._render_page_to_html(
                        doc[pg], pg, doc=doc, pdf_path=pdf_path
                    )
                    page_htmls.append(html)
                except Exception as e:
                    logger.warning(f"Failed to render page {pg}: {e}")

            if page_htmls:
                chapters.append((len(chapters), title, "\n".join(page_htmls)))

        return chapters

    async def render_page_as_image(
        self, pdf_path: str, page_index: int, dpi: int = 150
    ) -> str | None:
        """Render a PDF page as an image for faithful layout reproduction.

        Useful for complex layouts (multi-column, textbooks, magazines)
        where text extraction loses formatting.

        Args:
            pdf_path: Path to the PDF file.
            page_index: Zero-based page index.
            dpi: Resolution for rendering (default 150).

        Returns:
            URL to the rendered image, or None on failure.
        """
        try:
            doc = fitz.open(pdf_path)
            if page_index < 0 or page_index >= len(doc):
                doc.close()
                return None

            page = doc[page_index]
            scale = dpi / 72  # 72 is the PDF default DPI
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)

            img_dir = self._image_service.get_image_dir(pdf_path)
            filename = f"page_{page_index}.png"
            filepath = img_dir / filename

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            # Resize large images for web delivery
            max_width = 1200
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            img.save(filepath, "PNG", optimize=True)
            doc.close()

            return self._image_service.get_image_url(pdf_path, filename)

        except Exception as e:
            logger.warning(f"Failed to render PDF page {page_index} as image: {e}")
            return None

    async def get_table_of_contents(self, pdf_path: str) -> list[dict]:
        """Get table of contents for PDF.

        Resolves PDF outline/bookmark entries to actual page indices
        so that clicking a TOC item loads the correct page.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of TOC items with index, title, level

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            reader = PdfReader(pdf_path)
            toc_items = []

            # Cache named destinations (expensive to resolve repeatedly)
            _named_dests_cache: dict | None = None
            def _get_named_dests() -> dict:
                nonlocal _named_dests_cache
                if _named_dests_cache is None:
                    _named_dests_cache = reader.named_destinations
                return _named_dests_cache

            # Try to get PDF outline (bookmarks)
            if reader.outline:
                def resolve_page_index(item) -> int | None:
                    """Resolve an outline item to a 0-based page index."""
                    if not isinstance(item, dict):
                        return None

                    # Method 1: Direct /Page reference (most common)
                    page_ref = item.get('/Page')
                    if page_ref is not None:
                        try:
                            return reader.get_page_number(page_ref)
                        except Exception:
                            pass

                    # Method 2: /Dest string or array
                    dest = item.get('/Dest')
                    if dest is not None:
                        try:
                            if isinstance(dest, str):
                                named_dests = _get_named_dests()
                                if named_dests and dest in named_dests:
                                    page_obj = named_dests[dest]
                                    if hasattr(page_obj, 'page'):
                                        return reader.pages.index(page_obj.page)
                                    elif isinstance(page_obj, (list, tuple)):
                                        return reader.get_page_number(page_obj[0])
                            if isinstance(dest, (list, tuple)) and len(dest) > 0:
                                return reader.get_page_number(dest[0])
                        except Exception:
                            pass

                    # Method 3: /A dictionary with /D destination
                    action = item.get('/A')
                    if isinstance(action, dict):
                        a_dest = action.get('/D')
                        if a_dest is not None:
                            try:
                                if isinstance(a_dest, str):
                                    named_dests = _get_named_dests()
                                    if named_dests and a_dest in named_dests:
                                        page_obj = named_dests[a_dest]
                                        if hasattr(page_obj, 'page'):
                                            return reader.pages.index(page_obj.page)
                                        elif isinstance(page_obj, (list, tuple)):
                                            return reader.get_page_number(page_obj[0])
                                if isinstance(a_dest, (list, tuple)) and len(a_dest) > 0:
                                    return reader.get_page_number(a_dest[0])
                            except Exception:
                                pass

                    return None

                def process_outline_item(item, level=1):
                    """Recursively process outline items."""
                    if isinstance(item, list):
                        for sub_item in item:
                            process_outline_item(sub_item, level)
                    elif isinstance(item, dict) and '/Title' in item:
                        page_idx = resolve_page_index(item)
                        if page_idx is not None:
                            toc_items.append({
                                "index": page_idx,
                                "title": item.get('/Title', 'Untitled'),
                                "level": level
                            })

                        # Process children
                        if '/First' in item:
                            child = item['/First']
                            while child:
                                process_outline_item(child, level + 1)
                                child = child.get('/Next') if isinstance(child, dict) else None

                process_outline_item(reader.outline)

            if toc_items:
                return toc_items

            # Fall back to page list
            chapters = await self.get_chapters(pdf_path)
            return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]

        except Exception:
            # Fall back to basic chapter list on error
            chapters = await self.get_chapters(pdf_path)
            return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]
