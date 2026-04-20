"""Shared image extraction, storage, and URL service for PDF and EPUB."""

import hashlib
import os
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.logging_config import get_logger

logger = get_logger(__name__)

# Safe characters for filenames
_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]")


class BookImageService:
    """Manages extracted book images on disk.

    Images are stored in per-book directories under ``book_images_path``.
    Directory names use a SHA-256 hash of the book path (first 32 hex chars),
    matching the cover-naming convention in the parsers.
    """

    def __init__(self, book_images_path: str = "./static_book_images") -> None:
        self._base_path = Path(book_images_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_image_dir(self, book_path: str) -> Path:
        """Return (and create) the per-book image directory.

        Args:
            book_path: Absolute path to the ebook file.

        Returns:
            Path to ``{book_images_path}/{sha256_hash[:32]}/``.
        """
        path_hash = hashlib.sha256(book_path.encode()).hexdigest()[:32]
        img_dir = self._base_path / path_hash
        img_dir.mkdir(parents=True, exist_ok=True)
        return img_dir

    def get_image_url(self, book_path: str, filename: str) -> str:
        """Return the URL that maps to a saved image file.

        Args:
            book_path: Absolute path to the ebook file.
            filename: Filename inside the per-book image directory.

        Returns:
            URL string like ``/book-images/{hash}/{filename}``.
        """
        path_hash = hashlib.sha256(book_path.encode()).hexdigest()[:32]
        return f"/book-images/{path_hash}/{filename}"

    # ------------------------------------------------------------------
    # PDF image extraction
    # ------------------------------------------------------------------

    def save_pdf_image(self, doc: "fitz.Document", xref: int, output_dir: Path) -> str | None:  # noqa: F821
        """Extract a single image from a PyMuPDF document by its xref.

        Args:
            doc: Open ``fitz.Document``.
            xref: The xref number of the image.
            output_dir: Directory to save the image into.

        Returns:
            Filename of the saved image, or ``None`` on failure.
        """
        try:
            base_image = doc.extract_image(xref)
            if not base_image:
                return None

            image_bytes = base_image.get("image")
            ext = base_image.get("ext", "png")

            if not image_bytes:
                return None

            # Convert to JPEG for consistency and size savings
            filename = f"img_{xref}.jpg"
            filepath = output_dir / filename

            try:
                img = Image.open(BytesIO(image_bytes))
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.save(filepath, "JPEG", quality=85, optimize=True)
            except Exception:
                # Fallback: save raw bytes with original extension
                filename = f"img_{xref}.{ext}"
                filepath = output_dir / filename
                filepath.write_bytes(image_bytes)

            return filename

        except Exception as e:
            logger.warning(f"Failed to extract PDF image xref={xref}: {e}")
            return None

    # ------------------------------------------------------------------
    # EPUB image extraction
    # ------------------------------------------------------------------

    def save_epub_image(
        self,
        item_name: str,
        content: bytes,
        output_dir: Path,
    ) -> str:
        """Save an EPUB image to disk.

        Uses a content hash for deterministic filenames so repeated
        saves of the same image produce the same filename.

        Args:
            item_name: Original item name from the EPUB (e.g. ``Images/photo.jpg``).
            content: Raw image bytes.
            output_dir: Directory to save into.

        Returns:
            Sanitized filename used on disk.
        """
        # Use content hash for deterministic naming
        content_hash = hashlib.sha256(content).hexdigest()[:12]
        is_svg = item_name.lower().endswith(".svg")

        if is_svg:
            safe_name = f"{content_hash}.svg"
            filepath = output_dir / safe_name
            if not filepath.exists():
                filepath.write_bytes(content)
        else:
            safe_name = f"{content_hash}.jpg"
            filepath = output_dir / safe_name
            if not filepath.exists():
                try:
                    img = Image.open(BytesIO(content))
                    if img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    img.save(filepath, "JPEG", quality=85, optimize=True)
                except Exception:
                    filepath.write_bytes(content)

        return safe_name

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_book_images(self, book_path: str) -> int:
        """Remove all extracted images for a book.

        Args:
            book_path: Absolute path to the ebook file.

        Returns:
            Number of files removed.
        """
        img_dir = self.get_image_dir(book_path)
        count = 0
        for f in img_dir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        if count:
            logger.debug(f"Cleaned up {count} images for {book_path}")
        return count
