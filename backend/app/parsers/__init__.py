"""Format-specific parsers for ebook files."""

from app.parsers.cbz_parser import CBZParser
from app.parsers.epub_parser import EPUBParser
from app.parsers.fb2_parser import FB2Parser
from app.parsers.md_parser import MDParser
from app.parsers.mobi_parser import MOBIParser
from app.parsers.pdf_parser import PDFParser

__all__ = ["CBZParser", "EPUBParser", "FB2Parser", "MDParser", "PDFParser", "MOBIParser"]
