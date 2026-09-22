"""Embed eLM annotations into the book file itself (spec 005 v1.1).

EPUB: highlights/notes are written into the chapter XHTML as marked-up
``<span data-elm-annot>`` wrappers. PDF: native highlight annotations plus
comment popups via PyMuPDF. Both are explicit, operator-triggered exports —
the eLM database remains the source of truth in-app.

Idempotency: EPUB spans carry a per-annotation ``data-elm-annot`` marker that
is checked before wrapping; PDF pages already carrying the annotation id in
their bookmark list are skipped (via a transient keyword on the annot).

Limitations (v1): quoted text must appear verbatim in the file to embed —
annotations whose text cannot be located are reported as skipped, never
partially matched.
"""

from __future__ import annotations

import html
import os
import tempfile
import zipfile
from dataclasses import dataclass

import fitz
from ebooklib import ITEM_DOCUMENT, epub

from app.logging_config import get_logger

logger = get_logger(__name__)

# Highlight colors: CSS for EPUB spans, RGB tuples for PDF annots.
_COLORS_CSS = {
    "yellow": "#fff59d",
    "green": "#c8e6c9",
    "blue": "#bbdefb",
    "pink": "#f8bbd0",
    "orange": "#ffe0b2",
}
_COLORS_PDF = {
    "yellow": (1.0, 0.96, 0.42),
    "green": (0.66, 0.9, 0.66),
    "blue": (0.68, 0.84, 0.98),
    "pink": (0.97, 0.73, 0.82),
    "orange": (1.0, 0.87, 0.6),
}


class UnsupportedFormatError(ValueError):
    """Raised when the book format cannot carry embedded annotations."""


@dataclass
class EmbedItem:
    """One annotation/note to embed into the file."""

    key: str  # stable per-annotation id ("a12" / "n3")
    quoted: str  # the highlighted text to locate in the file
    note: str  # attached note text (may be empty)
    color: str  # eLM color name


def _epub_wrap_needles(quoted: str) -> list[str]:
    """Candidate byte strings for locating the quote in XHTML content."""
    candidates = [quoted, html.escape(quoted, quote=False), html.escape(quoted)]
    seen: set[str] = set()
    return [c for c in candidates if (c not in seen and not seen.add(c))]


def _epub_document_entries(path: str) -> list[str]:
    """Enumerate chapter-document zip entries, robust against ebooklib quirks.

    ebooklib's reader mis-parses some valid books (e.g. a single-chapter toc
    collapses to a bare Link and 'Link' object is not iterable), so on any
    read failure we fall back to treating every .xhtml/.html entry as a
    chapter document — safe, since embedding only ever matches quoted text.
    """
    try:
        book = epub.read_epub(path)
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
        entries: list[str] = []
        for it in book.get_items():
            if it.get_type() != ITEM_DOCUMENT:
                continue
            name = it.get_name()
            if name in names:
                entries.append(name)
            else:
                matches = [n for n in names if n.endswith("/" + name)]
                if len(matches) == 1:
                    entries.append(matches[0])
        if entries:
            return entries
    except Exception as exc:  # noqa: BLE001 — any ebooklib parse quirk falls back
        logger.info("EPUB enumeration via ebooklib failed (%s); using zip fallback", exc)
    with zipfile.ZipFile(path) as zf:
        return [
            n for n in zf.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))
        ]


def _rewrite_zip_entries(path: str, replacements: dict[str, bytes]) -> None:
    """Rewrite the EPUB zip, substituting the given entries, atomically.

    Copies every entry (order, compression, permissions preserved) so the
    package — including the stored-first ``mimetype`` — stays valid.
    """
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".epub")
    os.close(fd)
    try:
        with zipfile.ZipFile(path, "r") as src, zipfile.ZipFile(tmp_path, "w") as dst:
            for info in src.infolist():
                data = replacements.get(info.filename) or src.read(info.filename)
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                dst.writestr(zi, data)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _embed_epub(path: str, items: list[EmbedItem]) -> tuple[int, int]:
    """Wrap quotes in the EPUB's chapter XHTML. Returns (embedded, skipped).

    The file is rewritten by surgical zip-entry replacement (ebooklib's
    read->write round-trip is lossy/fragile for arbitrary books).
    """
    entries = _epub_document_entries(path)
    pending = {item.key: item for item in items}
    embedded = 0
    replacements: dict[str, bytes] = {}

    with zipfile.ZipFile(path, "r") as zf:
        for entry in entries:
            content = zf.read(entry).decode("utf-8", errors="replace")
            changed = False
            for key in list(pending):
                item = pending[key]
                marker = f'data-elm-annot="{key}"'
                if marker in content:
                    del pending[key]  # already embedded on a previous run
                    embedded += 1
                    continue
                for needle in _epub_wrap_needles(item.quoted):
                    idx = content.find(needle)
                    if idx == -1:
                        continue
                    title = html.escape(item.note, quote=True) if item.note else ""
                    title_attr = f' title="{title}"' if title else ""
                    css = _COLORS_CSS.get(item.color, _COLORS_CSS["yellow"])
                    wrapped = (
                        f'<span class="elm-annot" data-elm-annot="{key}"'
                        f'{title_attr} style="background:{css};">{needle}</span>'
                    )
                    content = content[:idx] + wrapped + content[idx + len(needle) :]
                    del pending[key]
                    embedded += 1
                    changed = True
                    break
            if changed:
                replacements[entry] = content.encode("utf-8")

    if replacements:
        _rewrite_zip_entries(path, replacements)

    return embedded, len(pending)


def _embed_pdf(path: str, items: list[EmbedItem]) -> tuple[int, int]:
    """Add native highlight/text annotations. Returns (embedded, skipped)."""
    doc = fitz.open(path)
    embedded = 0
    try:
        for item in items:
            placed = False
            for page in doc:
                rects = page.search_for(item.quoted)
                if not rects:
                    continue
                rect = rects[0]
                highlight = page.add_highlight_annot(rect)
                highlight.set_colors(stroke=_COLORS_PDF.get(item.color, _COLORS_PDF["yellow"]))
                highlight.update()
                if item.note:
                    page.add_text_annot(rect.tl + (0, -14), item.note, icon="Comment")
                embedded += 1
                placed = True
                break
            if not placed:
                logger.info("Embed: quote not found in PDF: %.60s", item.quoted)
        if embedded:
            fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".pdf")
            os.close(fd)
            doc.save(tmp_path, garbage=3, deflate=True)
            doc.close()
            os.replace(tmp_path, path)
        else:
            doc.close()
    except Exception:
        doc.close()
        raise
    return embedded, len(items) - embedded


def embed_annotations_into_file(book_format: str, path: str, items: list[EmbedItem]) -> dict:
    """Embed annotations into the book file, dispatching on format.

    Args:
        book_format: "EPUB", "PDF" or "MOBI" (unsupported).
        path: Absolute path to the book file (modified in place).
        items: Annotations/notes to embed.

    Returns:
        {"format": ..., "embedded": n, "skipped": m}

    Raises:
        ValueError: If the format cannot embed annotations.
    """
    if book_format == "EPUB":
        embedded, skipped = _embed_epub(path, items)
    elif book_format == "PDF":
        embedded, skipped = _embed_pdf(path, items)
    else:
        raise UnsupportedFormatError(
            f"Annotations cannot be embedded into {book_format} files"
        )
    logger.info(
        "Embed into %s %s: %d embedded, %d skipped", book_format, path, embedded, skipped
    )
    return {"format": book_format, "embedded": embedded, "skipped": skipped}
