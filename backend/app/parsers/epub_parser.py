"""EPUB format parser using ebooklib."""

import hashlib
import os
from pathlib import Path
from typing import Optional

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from app.exceptions import EbookParsingError
from app.logging_config import get_logger
from app.parsers.image_service import BookImageService
from app.schemas import BookCreate

logger = get_logger(__name__)


class EPUBParser:
    """Parser for EPUB format ebooks.

    Handles EPUB file parsing, metadata extraction, cover image extraction,
    and chapter content retrieval.
    """

    SUPPORTED_FORMAT = "EPUB"

    def __init__(
        self,
        covers_path: str = "./static_covers",
        book_images_path: str = "./static_book_images",
    ) -> None:
        """Initialize EPUB parser.

        Args:
            covers_path: Directory to store extracted cover images.
            book_images_path: Directory for extracted inline images.
        """
        self.covers_path = Path(covers_path)
        self.covers_path.mkdir(parents=True, exist_ok=True)
        self._image_service = BookImageService(book_images_path)

    async def extract_metadata(self, epub_path: str) -> BookCreate:
        """Extract metadata from EPUB file.

        Args:
            epub_path: Path to EPUB file

        Returns:
            BookCreate object with extracted metadata

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            book = epub.read_epub(epub_path)

            # Extract title
            title_metadata = book.get_metadata('DC', 'title')
            title = title_metadata[0][0] if title_metadata else Path(epub_path).stem

            # Extract author
            author_metadata = book.get_metadata('DC', 'creator')
            author = author_metadata[0][0] if author_metadata else "Unknown"

            # Extract publisher
            publisher_metadata = book.get_metadata('DC', 'publisher')
            publisher = publisher_metadata[0][0] if publisher_metadata else None

            # Extract publish date
            date_metadata = book.get_metadata('DC', 'date')
            publish_date = date_metadata[0][0] if date_metadata else None

            # Extract description
            desc_metadata = book.get_metadata('DC', 'description')
            description = desc_metadata[0][0] if desc_metadata else None

            # Extract language
            lang_metadata = book.get_metadata('DC', 'language')
            language = lang_metadata[0][0] if lang_metadata else None

            # Extract ISBN (from identifier)
            isbn = None
            id_metadata = book.get_metadata('DC', 'identifier')
            for id_entry in id_metadata:
                id_value = id_entry[0] if id_entry else ""
                if id_value and ('isbn' in id_value.lower() or id_value.replace('-', '').isdigit()):
                    isbn = id_value
                    break

            # Extract subjects/tags
            subject_metadata = book.get_metadata('DC', 'subject')
            subjects = [s[0] for s in subject_metadata if s[0]]

            # Get file size
            file_size = os.path.getsize(epub_path)

            # Estimate pages (rough estimate: 1 page ≈ 2KB of content)
            total_pages = max(1, file_size // 2048)

            logger.info(f"Extracted EPUB metadata: {title} by {author}")

            return BookCreate(
                title=title,
                author=author,
                path=epub_path,
                format="EPUB",
                file_size=file_size,
                publisher=publisher,
                publish_date=publish_date,
                description=description,
                language=language,
                isbn=isbn,
                total_pages=total_pages,
                subjects=subjects
            )

        except Exception as e:
            raise EbookParsingError(
                f"Failed to parse EPUB: {str(e)}",
                {"path": epub_path, "error": str(e)}
            ) from e

    async def extract_cover(self, epub_path: str) -> Optional[str]:
        """Extract and save cover image from EPUB.

        Args:
            epub_path: Path to EPUB file

        Returns:
            Path to extracted cover or None

        Raises:
            EbookParsingError: If cover extraction fails
        """
        try:
            book = epub.read_epub(epub_path)
            cover_item = None
            is_svg = False

            # Try to get cover item
            cover_items = list(book.get_items_of_type(ebooklib.ITEM_COVER))
            if not cover_items:
                # Try common cover names (including SVG)
                for item in book.get_items():
                    name = item.get_name().lower()
                    if 'cover' in name:
                        # Check if it's an SVG
                        if name.endswith('.svg') or item.get_type() == ebooklib.ITEM_UNKNOWN:
                            cover_item = item
                            is_svg = True
                            break
                        elif item.get_type() == ebooklib.ITEM_IMAGE:
                            cover_item = item
                            break

            if cover_items and not cover_item:
                cover_item = cover_items[0]

            if not cover_item:
                logger.debug(f"No cover found for {epub_path}")
                return None

            cover_content = cover_item.get_content()

            # Generate unique cover filename (SHA256 for security)
            epub_hash = hashlib.sha256(epub_path.encode()).hexdigest()[:32]
            cover_path = self.covers_path / f"{epub_hash}.jpg"

            # Handle SVG covers
            if is_svg or (hasattr(cover_item, 'media_type') and cover_item.media_type == 'image/svg+xml'):
                svg_path = self.covers_path / f"{epub_hash}.svg"
                with open(svg_path, 'wb') as f:
                    f.write(cover_content)
                logger.debug(f"SVG cover extracted: {svg_path}")
                return str(svg_path)

            # Handle image covers with PIL
            try:
                from io import BytesIO

                from PIL import Image

                img = Image.open(BytesIO(cover_content))

                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Resize if too large
                max_size = (600, 900)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save optimized cover
                img.save(cover_path, "JPEG", quality=85, optimize=True)

                logger.debug(f"Cover extracted: {cover_path}")
                return str(cover_path)

            except Exception as e:
                logger.warning(f"Cover image processing failed: {e}")
                return None

        except Exception as e:
            logger.warning(f"Cover extraction failed: {e}")
            return None

    async def get_chapters(self, epub_path: str) -> list[tuple[int, str, str]]:
        """Extract all chapters from EPUB.

        Args:
            epub_path: Path to EPUB file

        Returns:
            List of tuples: (chapter_index, chapter_title, chapter_content)

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            import warnings
            from bs4 import XMLParsedAsHTMLWarning
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

            book = epub.read_epub(epub_path)
            spine_items = self._filter_spine_items(book)
            chapters: list[tuple[int, str, str]] = []

            for item, soup in spine_items:
                html_content, title = self._render_spine_item(item, soup, book, epub_path)
                chapters.append((len(chapters), title, html_content))

            logger.info(f"Extracted {len(chapters)} chapters from EPUB")
            return chapters

        except Exception as e:
            raise EbookParsingError(
                f"Failed to extract chapters: {str(e)}",
                {"path": epub_path}
            ) from e

    async def get_single_chapter(
        self, epub_path: str, chapter_index: int
    ) -> tuple[str, str, int]:
        """Extract a single chapter without parsing all EPUB content.

        Iterates spine items to find the target chapter index. Only the
        target item's content is parsed with BeautifulSoup.

        Args:
            epub_path: Path to EPUB file.
            chapter_index: Zero-based chapter index.

        Returns:
            Tuple of (content_html, title, total_chapters).

        Raises:
            EbookParsingError: If parsing fails.
            ResourceNotFoundError: If chapter index is out of range.
        """
        try:
            import warnings
            from bs4 import XMLParsedAsHTMLWarning
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

            book = epub.read_epub(epub_path)
            spine_items = self._filter_spine_items(book)
            total = len(spine_items)

            if chapter_index < 0 or chapter_index >= total:
                from app.exceptions import ResourceNotFoundError
                raise ResourceNotFoundError(
                    f"Chapter {chapter_index} not found (total: {total})",
                    {"path": epub_path, "index": chapter_index}
                )

            item, soup = spine_items[chapter_index]
            html_content, title = self._render_spine_item(item, soup, book, epub_path)

            return html_content, title, total

        except EbookParsingError:
            raise
        except Exception as e:
            raise EbookParsingError(
                f"Failed to extract chapter: {str(e)}",
                {"path": epub_path, "index": chapter_index}
            ) from e

    def _extract_epub_styles(self, soup: BeautifulSoup) -> str:
        """Extract and sanitize EPUB-embedded CSS.

        Preserves typography and layout styles while removing
        properties that could break the reader layout.

        Args:
            soup: BeautifulSoup object with potential <style> tags.

        Returns:
            Sanitized ``<style>`` block string, scoped to ``.ic-chapter-text``,
            or empty string if no styles found.
        """
        import re

        style_tags = soup.find_all('style')
        if not style_tags:
            return ""

        css_parts: list[str] = []
        for tag in style_tags:
            css = tag.get_text()
            if not css.strip():
                continue
            css_parts.append(css)

        if not css_parts:
            return ""

        raw_css = "\n".join(css_parts)

        # Scope all selectors to .ic-chapter-text to prevent style leaks
        # Remove dangerous properties
        dangerous_props = re.compile(
            r'(position|z-index|overflow|opacity|visibility|transform|'
            r'animation|transition|pointer-events|user-select)\s*:\s*[^;]+;?',
            re.IGNORECASE,
        )
        raw_css = dangerous_props.sub('', raw_css)

        # Prefix selectors with .ic-chapter-text
        # Simple approach: prepend .ic-chapter-text to each selector block
        def scope_selector(match: re.Match) -> str:
            selector = match.group(1).strip()
            if selector.startswith('.ic-chapter-text') or selector.startswith('@'):
                return match.group(0)  # Already scoped or at-rule
            # Handle multiple selectors separated by commas
            parts = [f".ic-chapter-text {s.strip()}" for s in selector.split(',')]
            return f"{', '.join(parts)} {{"

        scoped_css = re.sub(r'([^{}]+)\{', scope_selector, raw_css)

        return f'<style class="epub-style">{scoped_css}</style>'


    def _extract_chapter_title(self, soup: BeautifulSoup) -> str:
        """Extract chapter title from HTML.

        Args:
            soup: BeautifulSoup object

        Returns:
            Chapter title or default
        """
        # Try h1-h6 tags
        for tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            tag = soup.find(tag_name)
            if tag:
                return tag.get_text(strip=True)

        return "Untitled Chapter"

    def _filter_spine_items(
        self, book: "epub.EpubBook"
    ) -> list[tuple]:
        """Return filtered spine items with pre-parsed soup objects.

        Parses each document item once and caches the result so callers
        (render, TOC mapping, counting) don't need to re-read content.

        Args:
            book: Open EpubBook instance.

        Returns:
            List of (item, soup) tuples in reading order.
        """
        items: list[tuple] = []
        for idref, _linear in book.spine:
            item = book.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            raw = item.get_content()
            s = BeautifulSoup(raw, 'html.parser')
            body = s.find('body')
            check = body if body else s
            text = check.get_text(strip=True)
            has_img = bool(check.find('img'))
            if len(text) < 100 and not has_img:
                continue

            items.append((item, s))
        return items

    def _render_spine_item(
        self,
        item,
        soup: BeautifulSoup,
        book: "epub.EpubBook",
        epub_path: str,
    ) -> tuple[str, str]:
        """Render a pre-parsed spine item to clean HTML.

        Args:
            item: Spine document item (for metadata).
            soup: Pre-parsed BeautifulSoup object for this item.
            book: Open EpubBook instance for image resolution.
            epub_path: Path to EPUB for image URL generation.

        Returns:
            Tuple of (html_content, title).
        """
        for tag in soup.find_all(['script', 'link']):
            tag.decompose()

        epub_style = self._extract_epub_styles(soup)

        for tag in soup.find_all(['style']):
            tag.decompose()

        body = soup.find('body')
        content_soup = body if body else soup

        # Rewrite images directly on the soup before serializing
        self._rewrite_images_in_soup(content_soup, book, epub_path)

        html_parts: list[str] = []
        for child in content_soup.children:
            if hasattr(child, 'name') and child.name:
                html_parts.append(str(child))
            elif hasattr(child, 'strip') and child.strip():
                html_parts.append(f'<p>{child.strip()}</p>')

        html_content = "\n".join(html_parts)

        if epub_style:
            html_content = epub_style + "\n" + html_content

        title = self._extract_chapter_title(content_soup)
        return html_content, title

    def _rewrite_images_in_soup(
        self,
        soup: BeautifulSoup,
        book: "epub.EpubBook",
        epub_path: str,
    ) -> None:
        """Rewrite EPUB image src attributes in a parsed soup (in-place).

        Args:
            soup: Parsed BeautifulSoup element to modify.
            book: Open EpubBook instance for resolving image references.
            epub_path: Path to EPUB file for URL generation.
        """
        img_tags = soup.find_all('img')
        if not img_tags:
            return

        img_dir = self._image_service.get_image_dir(epub_path)

        for img_tag in img_tags:
            src = img_tag.get('src', '')
            if not src or src.startswith('/book-images/'):
                continue

            try:
                image_item = None

                if hasattr(book, 'get_item_with_href'):
                    try:
                        image_item = book.get_item_with_href(src)
                    except Exception:
                        pass

                if image_item is None:
                    src_normalized = src.lstrip('./')
                    for book_item in book.get_items():
                        if book_item.get_type() == ebooklib.ITEM_IMAGE:
                            item_name = book_item.get_name()
                            if (item_name == src or
                                item_name.endswith(src) or
                                item_name.endswith(src_normalized)):
                                image_item = book_item
                                break

                if image_item is None:
                    continue

                image_bytes = image_item.get_content()
                filename = self._image_service.save_epub_image(
                    image_item.get_name(), image_bytes, img_dir
                )

                url = self._image_service.get_image_url(epub_path, filename)
                img_tag['src'] = url
                img_tag['loading'] = 'lazy'

            except Exception as e:
                logger.warning(f"Failed to rewrite EPUB image '{src}': {e}")

    async def count_chapters(self, epub_path: str) -> int:
        """Count the number of chapters in an EPUB.

        Args:
            epub_path: Path to EPUB file

        Returns:
            Number of chapters
        """
        try:
            book = epub.read_epub(epub_path, options={"ignore_ncx": True})
            spine_items = self._filter_spine_items(book)
            return len(spine_items)
        except Exception:
            return 0

    async def get_table_of_contents(self, epub_path: str) -> list[dict]:
        """Extract table of contents from EPUB.

        Resolves TOC entries to actual spine-based chapter indices so that
        clicking a TOC item loads the correct chapter content.

        Args:
            epub_path: Path to EPUB file

        Returns:
            List of TOC items with index, title, level

        Raises:
            EbookParsingError: If parsing fails
        """
        try:
            book = epub.read_epub(epub_path)
            toc_items = []
            toc = book.toc if hasattr(book, 'toc') else []

            # Build spine → filtered-chapter-index mapping using shared filter
            spine_items = self._filter_spine_items(book)

            # Build href → filtered index map
            href_to_index: dict[str, int] = {}
            for idx, (item, _soup) in enumerate(spine_items):
                name = item.get_name()
                href_to_index[name] = idx
                # Also map without directory prefix
                if '/' in name:
                    href_to_index[name.split('/')[-1]] = idx

            def resolve_href(toc_item) -> int | None:
                """Resolve a TOC item's href to a spine index."""
                href = getattr(toc_item, 'href', '') or ''
                # Normalize: strip fragment, strip leading ./
                href = href.split('#')[0].lstrip('./')
                for key in [href, href.split('/')[-1]]:
                    if key in href_to_index:
                        return href_to_index[key]
                return None

            def process_toc_item(item, level=1):
                """Recursively process TOC items."""
                if isinstance(item, (tuple, list)):
                    for sub_item in item:
                        process_toc_item(sub_item, level)
                elif hasattr(item, 'title'):
                    spine_idx = resolve_href(item)
                    if spine_idx is not None:
                        toc_items.append({
                            "index": spine_idx,
                            "title": item.title or "Untitled",
                            "level": level
                        })

                    if hasattr(item, 'children') and item.children:
                        for child in item.children:
                            process_toc_item(child, level + 1)

            # Process TOC if it exists
            if toc:
                process_toc_item(toc)

            # Fall back to chapter list if no TOC or empty result
            if not toc_items:
                chapters = await self.get_chapters(epub_path)
                toc_items = [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]

            return toc_items

        except Exception:
            # Fall back to basic chapter list on error
            chapters = await self.get_chapters(epub_path)
            return [{"index": i, "title": title, "level": 1} for i, (_, title, _) in enumerate(chapters)]
