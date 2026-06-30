"""Full-text extraction for the content search index (spec 012).

Extracts plain text from each supported ebook format so it can be indexed in the
``books_content_fts`` FTS5 table. Functions are module-level (picklable) so the
backfill job can move them to a :class:`~concurrent.futures.ProcessPoolExecutor`
without refactoring.

Reuses the same libraries the format parsers already depend on:

* EPUB → ``ebooklib`` spine walk + ``BeautifulSoup.get_text``
* PDF   → ``PyMuPDF`` (``fitz``) ``page.get_text("text")``
* MOBI  → ``pymobi`` (best-effort; returns "" if unavailable/unparseable)

Extraction is best-effort: a format that yields no text (e.g. a scanned PDF)
returns an empty string so the caller can mark it ``empty`` rather than looping.
"""

from __future__ import annotations

import re

from app.logging_config import get_logger

logger = get_logger(__name__)

#: Cap extracted text so a single enormous book can't dominate FTS storage.
#: ~2M chars ≈ a few MB; ample for search relevance while bounding disk use.
_MAX_TEXT_CHARS = 2_000_000


def extract_text(path: str, fmt: str) -> str:
    """Extract normalized plain text from an ebook for full-text indexing.

    Args:
        path: Absolute path to the ebook file.
        fmt: Format string ("EPUB" | "PDF" | "MOBI"); case-insensitive.

    Returns:
        Normalized whitespace-collapsed text (possibly empty), capped at
        ``_MAX_TEXT_CHARS``. Never raises — callers rely on a string return.
    """
    fmt_norm = (fmt or "").strip().upper()
    try:
        if fmt_norm == "EPUB":
            text = _extract_epub(path)
        elif fmt_norm == "PDF":
            text = _extract_pdf(path)
        elif fmt_norm == "MOBI":
            text = _extract_mobi(path)
        else:
            return ""
    except Exception as e:  # noqa: BLE001 — extraction must never crash the backfill
        logger.warning("Content extraction failed for %s (%s): %s", path, fmt_norm, e)
        return ""
    return _normalize(text)


def _normalize(text: str) -> str:
    """Collapse runs of whitespace and cap length."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:_MAX_TEXT_CHARS]


def _extract_epub(path: str) -> str:
    """Walk the EPUB spine and concatenate each document's text."""
    import warnings

    import ebooklib
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from ebooklib import epub

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    book = epub.read_epub(path)
    parts: list[str] = []
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        chunk = soup.get_text(separator=" ")
        if chunk:
            parts.append(chunk)
    return " ".join(parts)


def _extract_pdf(path: str) -> str:
    """Concatenate per-page text via PyMuPDF."""
    import fitz

    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def _extract_mobi(path: str) -> str:
    """Best-effort MOBI text via pymobi (returns "" if unavailable)."""
    try:
        from bs4 import BeautifulSoup
        from pymobi.mobi import BookMobi
    except ImportError:
        return ""
    try:
        reader = BookMobi(path)
        html = ""
        for attr in ("get_html", "get_html_stream", "content"):
            fn = getattr(reader, attr, None)
            if callable(fn):
                try:
                    html = fn() or ""
                except Exception:  # noqa: BLE001
                    html = ""
                if html:
                    break
            elif isinstance(fn, str):
                html = fn
                break
        if not html:
            return ""
        return BeautifulSoup(html, "html.parser").get_text(separator=" ")
    except Exception as e:  # noqa: BLE001
        logger.debug("MOBI text extraction unsuccessful for %s: %s", path, e)
        return ""


__all__ = ["extract_text"]
