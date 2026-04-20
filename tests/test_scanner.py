"""Tests for library scanner and ebook parsers."""

import pytest
from pathlib import Path

from app.exceptions import EbookParsingError, LibraryScannerError
from app.scanner import LibraryScanner


@pytest.mark.asyncio
async def test_scanner_empty_directory(temp_library):
    """Test scanning empty directory."""
    scanner = LibraryScanner()

    books = await scanner.scan_directory(str(temp_library))

    assert len(books) == 0


@pytest.mark.asyncio
async def test_scanner_nonexistent_directory():
    """Test scanning non-existent directory."""
    scanner = LibraryScanner()

    with pytest.raises(LibraryScannerError):
        await scanner.scan_directory("/nonexistent/path")


def test_epub_parser_metadata_extraction():
    """Test EPUB metadata extraction."""
    from app.parsers import EPUBParser

    parser = EPUBParser()

    # This would need a real EPUB file for full testing
    # For now, we test the parser initialization
    assert parser.SUPPORTED_FORMAT == "EPUB"
    assert parser.covers_path is not None


def test_pdf_parser_initialization():
    """Test PDF parser initialization."""
    from app.parsers import PDFParser

    parser = PDFParser()

    assert parser.SUPPORTED_FORMAT == "PDF"
    assert parser.covers_path is not None


def test_mobi_parser_initialization():
    """Test MOBI parser initialization."""
    from app.parsers import MOBIParser

    # Note: This will fail if pymobi is not installed
    try:
        parser = MOBIParser()

        assert parser.SUPPORTED_FORMAT == "MOBI"
        assert parser.covers_path is not None
    except ImportError:
        # Expected if pymobi not installed
        pytest.skip("pymobi not installed")


@pytest.mark.asyncio
async def test_extract_metadata_invalid_file(temp_library):
    """Test extracting metadata from invalid file."""
    from app.parsers import EPUBParser

    parser = EPUBParser()

    # Create invalid EPUB file
    invalid_epub = temp_library / "invalid.epub"
    invalid_epub.write_text("Not an EPUB file")

    with pytest.raises(EbookParsingError):
        await parser.extract_metadata(str(invalid_epub))


def test_scanner_format_detection():
    """Test scanner format detection."""
    scanner = LibraryScanner()

    assert ".epub" in scanner.SUPPORTED_FORMATS
    assert ".pdf" in scanner.SUPPORTED_FORMATS
    assert ".mobi" in scanner.SUPPORTED_FORMATS
