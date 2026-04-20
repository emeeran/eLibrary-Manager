# SPEC-008: File Parsers

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15
- **Depends On:** None (foundational spec)

## Purpose

File Parsers provide the foundational content extraction layer for eLibrary Manager. The `LibraryScanner` orchestrates format-specific parsers (EPUB, PDF, MOBI) to discover ebook files on the local filesystem, extract metadata and cover images, retrieve chapter content, and build tables of contents. Every higher-level feature — library import, reader display, AI summarization, bookmarks, and text-to-speech — depends on this module to correctly parse and structure ebook content. The three parsers share a unified interface so the scanner can route any supported format through identical method calls without format-specific branching at the call site.

---

## Behavior

### Scanner

#### AC-008.01: Scan Directory for Ebook Files

**Given** a valid directory path exists on the filesystem
**When** `LibraryScanner.scan_directory(directory)` is called
**Then** the scanner recursively walks the directory tree using `os.walk`
**And** it matches files by extension against `{".epub", ".pdf", ".mobi"}` (case-insensitive comparison via `suffix.lower()`)
**And** for each matched file, it calls `extract_metadata()` to produce a `BookCreate` object
**And** it returns `list[BookCreate]` containing all successfully parsed books
**And** it logs a summary: `"{N} indexed, {N} skipped (DRM), {N} errors"`

#### AC-008.02: Scan Nonexistent Directory

**Given** the provided directory path does not exist on the filesystem
**When** `LibraryScanner.scan_directory()` is called with that path
**Then** the scanner raises `LibraryScannerError` with message `"Library directory does not exist: {path}"`
**And** the error `details` dict contains `{"directory": path}`

#### AC-008.03: Scan Empty Directory

**Given** the target directory exists but contains no files with `.epub`, `.pdf`, or `.mobi` extensions
**When** `LibraryScanner.scan_directory()` is called
**Then** the scanner returns an empty `list[BookCreate]` (`[]`)
**And** the log summary reports `0 indexed, 0 skipped, 0 errors`

#### AC-008.04: Scan Skips Unsupported Files

**Given** the target directory contains files with extensions other than `.epub`, `.pdf`, `.mobi` (e.g. `.txt`, `.docx`, `.jpg`)
**When** `LibraryScanner.scan_directory()` processes each file
**Then** files with unsupported extensions are silently skipped (not counted in any total)

#### AC-008.05: Scan Handles DRM Files Gracefully

**Given** the scanner encounters a file that raises a `LibraryScannerError` containing `"DRM"` in its `details`
**When** the error is caught during scan iteration
**Then** the file is counted as `skipped_count` (not `error_count`)
**And** a warning is logged: `"Skipped DRM file: {path}"`
**And** scanning continues processing remaining files

#### AC-008.06: Scan Handles Corrupt Files Gracefully

**Given** the scanner encounters a file that raises a non-DRM `LibraryScannerError` or any other `Exception`
**When** the error is caught during scan iteration
**Then** the file is counted in `error_count`
**And** a warning (for `LibraryScannerError`) or error (for other exceptions) is logged
**And** scanning continues processing remaining files

#### AC-008.07: Scan Defaults to Configured Library Path

**Given** no `directory` argument is passed to `scan_directory()`
**When** the method executes
**Then** it uses `self.config.library_path` as the target directory

#### AC-008.08: Scanner Routes to Correct Parser by Extension

**Given** an ebook file path with extension `.epub`, `.pdf`, or `.mobi`
**When** `extract_metadata()`, `extract_cover()`, `get_chapters()`, `count_chapters()`, or `get_table_of_contents()` is called on the scanner
**Then** the scanner dispatches to `EPUBParser`, `PDFParser`, or `MOBIParser` respectively based on `Path.suffix.lower()`
**And** if the extension is unsupported, `extract_metadata()` raises `LibraryScannerError` with message `"Unsupported file format: {ext}"`
**And** if the extension is unsupported, `get_chapters()` raises `EbookParsingError`
**And** if the extension is unsupported, `count_chapters()` returns `0`
**And** if the extension is unsupported, `extract_cover()` returns `None`

#### AC-008.09: Scanner Initializes All Three Parsers

**Given** a `LibraryScanner` is instantiated
**When** `__init__` completes
**Then** `self.epub_parser` is an `EPUBParser` instance
**And** `self.pdf_parser` is a `PDFParser` instance
**And** `self.mobi_parser` is a `MOBIParser` instance
**And** all three parsers share the same `covers_path` from configuration

---

### EPUB Parser

#### AC-008.10: EPUB Metadata Extraction

**Given** a valid EPUB file at `epub_path`
**When** `EPUBParser.extract_metadata(epub_path)` is called
**Then** it opens the file with `ebooklib.epub.read_epub()`
**And** it extracts `title` from `DC:title` metadata, falling back to the filename stem (hyphens/underscores replaced with spaces, `.title()` cased)
**And** it extracts `author` from `DC:creator` metadata, falling back to `"Unknown"`
**And** it extracts `publisher` from `DC:publisher` metadata, falling back to `None`
**And** it extracts `publish_date` from `DC:date` metadata, falling back to `None`
**And** it extracts `description` from `DC:description` metadata, falling back to `None`
**And** it extracts `language` from `DC:language` metadata, falling back to `None`
**And** it extracts `isbn` from `DC:identifier` metadata by checking for `"isbn"` in the value or all-digit (after stripping hyphens), falling back to `None`
**And** it computes `file_size` via `os.path.getsize()`
**And** it estimates `total_pages` as `max(1, file_size // 2048)`
**And** it returns a `BookCreate` with `format="EPUB"`

#### AC-008.11: EPUB Metadata Extraction Failure

**Given** a corrupt or invalid EPUB file at `epub_path`
**When** `EPUBParser.extract_metadata(epub_path)` is called
**Then** it raises `EbookParsingError` with message `"Failed to parse EPUB: {original_error}"`
**And** the error `details` dict contains `{"path": epub_path, "error": str(original_error)}`

#### AC-008.12: EPUB Cover Extraction — Standard Image

**Given** a valid EPUB file containing a cover image of type `ITEM_COVER` or `ITEM_IMAGE` with `"cover"` in the item name
**When** `EPUBParser.extract_cover(epub_path)` is called
**Then** it searches for cover items in this order: `ITEM_COVER` items, then items with `"cover"` in name
**And** it loads the image with PIL, converts to RGB if necessary
**And** it resizes to fit within 600x900 using `Image.thumbnail()` with `LANCZOS` resampling
**And** it generates a filename using the first 32 hex chars of `SHA256(epub_path.encode())`
**And** it saves as JPEG with quality=85 and `optimize=True`
**And** it returns the string path to the saved cover file

#### AC-008.13: EPUB Cover Extraction — SVG

**Given** a valid EPUB file where the cover is an SVG image (`image/svg+xml` media type or `.svg` filename)
**When** `EPUBParser.extract_cover(epub_path)` is called
**Then** it writes the raw SVG content to `{covers_path}/{hash}.svg`
**And** it returns the string path to the saved SVG file (no PIL conversion)

#### AC-008.14: EPUB Cover Extraction — No Cover Found

**Given** a valid EPUB file that contains no cover image
**When** `EPUBParser.extract_cover(epub_path)` is called
**Then** it returns `None`
**And** logs a debug message: `"No cover found for {epub_path}"`

#### AC-008.15: EPUB Cover Extraction Failure

**Given** any exception occurs during cover extraction
**When** `EPUBParser.extract_cover(epub_path)` catches the exception
**Then** it logs a warning and returns `None` (never raises)

#### AC-008.16: EPUB Chapter Extraction

**Given** a valid EPUB file
**When** `EPUBParser.get_chapters(epub_path)` is called
**Then** it opens the EPUB and iterates all items of type `ITEM_DOCUMENT`
**And** for each document item, it parses the content with `BeautifulSoup(content, 'lxml')`
**And** it decomposes all `<script>` tags
**And** it extracts plain text via `soup.get_text(strip=True)`
**And** it skips items where plain text is shorter than 200 characters
**And** it extracts a chapter title using `_extract_chapter_title()`: searching `h1` through `h6` tags in order, falling back to `"Untitled Chapter"`
**And** it preserves the original HTML content (including images and formatting) as `chapter_content`
**And** it returns `list[tuple[int, str, str]]` where each tuple is `(chapter_index, chapter_title, html_content)`
**And** `chapter_index` is a zero-based sequential integer

#### AC-008.17: EPUB Chapter Extraction Failure

**Given** a corrupt EPUB file that cannot be opened or parsed
**When** `EPUBParser.get_chapters(epub_path)` fails
**Then** it raises `EbookParsingError` with message `"Failed to extract chapters: {original_error}"`

#### AC-008.18: EPUB Chapter Count

**Given** a valid EPUB file
**When** `EPUBParser.count_chapters(epub_path)` is called
**Then** it delegates to `get_chapters()` and returns `len(chapters)`

#### AC-008.19: EPUB Table of Contents — Hierarchical

**Given** a valid EPUB file with a structured TOC (from `book.get_table_of_contents()`)
**When** `EPUBParser.get_table_of_contents(epub_path)` is called
**Then** it recursively processes TOC items, assigning `level` starting at 1 and incrementing for children
**And** each TOC item is a `dict` with keys `{"index": int, "title": str, "level": int}`
**And** items with `title=None` use `"Untitled"` as the title
**And** it returns the list of TOC item dicts

#### AC-008.20: EPUB Table of Contents — Fallback

**Given** a valid EPUB file with no structured TOC (empty `book.get_table_of_contents()`)
**When** `EPUBParser.get_table_of_contents(epub_path)` is called
**Then** it falls back to the chapter list from `get_chapters()`
**And** returns `[{"index": i, "title": chapter_title, "level": 1}]` for each chapter
**And** if an exception occurs during TOC extraction, it also falls back to the chapter list

---

### PDF Parser

#### AC-008.21: PDF Metadata Extraction — From Document Info

**Given** a valid PDF file with embedded metadata (`/Title`, `/Author`, etc.)
**When** `PDFParser.extract_metadata(pdf_path)` is called
**Then** it opens the file with `pypdf.PdfReader`
**And** it extracts `title` from `/Title` metadata
**And** it extracts `author` from `/Author` metadata, falling back to `"Unknown"`
**And** it extracts `publisher` from `/Creator` metadata
**And** it extracts `publish_date` from `/CreationDate` metadata, extracting just the 4-digit year (characters 2-6 of the `D:YYYYMMDDHHmmss` format)
**And** it extracts `description` from `/Subject` metadata
**And** it computes `file_size` via `os.path.getsize()`
**And** it sets `total_pages` to `len(reader.pages)`
**And** it returns a `BookCreate` with `format="PDF"`

#### AC-008.22: PDF Metadata Extraction — Filename Fallback

**Given** a valid PDF file with no embedded metadata
**When** `PDFParser.extract_metadata(pdf_path)` is called
**Then** it derives `title` from the filename stem, replacing hyphens and underscores with spaces and applying `.title()` casing
**And** `author` defaults to `"Unknown"`
**And** `publisher`, `publish_date`, and `description` are all `None`

#### AC-008.23: PDF Metadata Extraction Failure

**Given** a corrupt or invalid PDF file
**When** `PDFParser.extract_metadata(pdf_path)` fails
**Then** it raises `EbookParsingError` with message `"Failed to parse PDF: {original_error}"`
**And** the error `details` dict contains `{"path": pdf_path, "error": str(original_error)}`

#### AC-008.24: PDF Cover Extraction — First Page Render

**Given** a valid PDF file with at least one page
**When** `PDFParser.extract_cover(pdf_path)` is called
**Then** it opens the file with PyMuPDF (`fitz.open`)
**And** it renders page 0 with a 2x zoom matrix (`fitz.Matrix(2, 2)`)
**And** it converts the pixmap to a PIL `Image` in RGB mode
**And** it resizes to fit within 600x900 using `Image.thumbnail()` with `LANCZOS` resampling
**And** it generates a filename using the first 32 hex chars of `SHA256(pdf_path.encode())`
**And** it saves as JPEG with quality=85 and `optimize=True`
**And** it returns the string path to the saved cover file

#### AC-008.25: PDF Cover Extraction — Empty PDF

**Given** a valid PDF file with zero pages
**When** `PDFParser.extract_cover(pdf_path)` is called
**Then** it logs a warning: `"PDF has no pages: {pdf_path}"`
**And** it returns `None`

#### AC-008.26: PDF Cover Extraction Failure

**Given** any exception occurs during PDF cover extraction
**When** `PDFParser.extract_cover(pdf_path)` catches the exception
**Then** it logs a warning and returns `None` (never raises)

#### AC-008.27: PDF Chapter Extraction — Page-as-Chapter with Formatting

**Given** a valid PDF file
**When** `PDFParser.get_chapters(pdf_path)` is called
**Then** it opens the file with PyMuPDF (`fitz.open`)
**And** for each page, it extracts text using `page.get_text("dict")` to get structured block/line/span data
**And** it builds HTML output within a `<div class="pdf-page-text">` wrapper
**And** it detects headings by average font size: `>18px` becomes `<h2 class="pdf-heading">`, `>15px` becomes `<h3 class="pdf-subheading">`
**And** it detects bold via span flags (`flags & 2**4`) and applies `font-weight: bold`
**And** it detects italic via span flags (`flags & 2**1`) and applies `font-style: italic`
**And** it preserves non-default font sizes as inline `font-size` styles
**And** it calculates indentation from the x-position of each line: `indent_level = int((line_left - 72) / 36)` for lines starting past x=100
**And** it inserts `<div class="pdf-space"></div>` between blocks with vertical gaps exceeding 20 units
**And** it escapes all text content using `_escape_html()` (handles `&`, `<`, `>`, `"`, `'`)
**And** it titles each page as `"Page {page_num + 1}"`
**And** on per-page failure, it falls back to plain text extraction via `page.get_text("text")`
**And** it returns `list[tuple[int, str, str]]` where each tuple is `(page_index, page_title, formatted_html)`

#### AC-008.28: PDF Chapter Extraction Failure

**Given** a corrupt PDF file that cannot be opened
**When** `PDFParser.get_chapters(pdf_path)` fails at the top level
**Then** it raises `EbookParsingError` with message `"Failed to parse PDF: {original_error}"`

#### AC-008.29: PDF Chapter Count

**Given** a valid PDF file
**When** `PDFParser.count_chapters(pdf_path)` is called
**Then** it opens the file with `pypdf.PdfReader` and returns `len(reader.pages)`

#### AC-008.30: PDF Table of Contents — Bookmarks

**Given** a valid PDF file with an outline (bookmarks)
**When** `PDFParser.get_table_of_contents(pdf_path)` is called
**Then** it reads `reader.outline` from `pypdf.PdfReader`
**And** it recursively processes outline items, extracting `/Title` and incrementing `level` for children
**And** it returns a list of dicts with keys `{"index": int, "title": str, "level": int}`

#### AC-008.31: PDF Table of Contents — Fallback to Page List

**Given** a valid PDF file with no outline/bookmarks
**When** `PDFParser.get_table_of_contents(pdf_path)` is called
**Then** it falls back to the chapter list from `get_chapters()`
**And** returns `[{"index": i, "title": page_title, "level": 1}]` for each page
**And** if an exception occurs during TOC extraction, it also falls back to the page list

---

### MOBI Parser

#### AC-008.32: MOBI Metadata Extraction — EXTH Headers

**Given** a valid, non-DRM MOBI file with EXTH headers
**When** `MOBIParser.extract_metadata(mobi_path)` is called
**Then** it opens the file with `pymobi.BookMobi()`
**And** it extracts `title` from EXTH record type 106, falling back to the filename stem (hyphens/underscores replaced with spaces, `.title()` cased)
**And** it extracts `author` from EXTH record type 100, falling back to `"Unknown"`
**And** it computes `file_size` via `os.path.getsize()`
**And** it returns a `BookCreate` with `format="MOBI"`

#### AC-008.33: MOBI DRM Detection

**Given** a MOBI file that contains DRM protection markers
**When** `MOBIParser._is_drm_protected(mobi_path)` checks the file
**Then** it reads the first 100 bytes of the file
**And** it checks for the presence of any byte string in `{b'DRM', b'Protected', b'encryption'}`
**And** it returns `True` if any marker is found, `False` otherwise

#### AC-008.34: MOBI DRM Rejection

**Given** a DRM-protected MOBI file
**When** `MOBIParser.extract_metadata(mobi_path)` is called
**Then** it calls `_is_drm_protected()` which returns `True`
**And** it raises `EbookParsingError` with message `"DRM-protected MOBI files are not supported"`
**And** the error `details` dict contains `{"path": mobi_path, "reason": "DRM protection"}`

#### AC-008.35: MOBI Metadata Extraction Failure

**Given** a corrupt MOBI file (non-DRM related failure)
**When** `MOBIParser.extract_metadata(mobi_path)` fails
**Then** it re-raises `EbookParsingError` as-is
**And** for all other exceptions, it raises `EbookParsingError` with message `"Failed to parse MOBI: {original_error}"`
**And** the error `details` dict contains `{"path": mobi_path, "error": str(original_error)}`

#### AC-008.36: MOBI Parser Requires pymobi

**Given** the `pymobi` package is not installed
**When** `MOBIParser.__init__()` is called
**Then** it raises `ImportError` with message `"pymobi is not installed. Install it with: pip install pymobi"`

#### AC-008.37: MOBI Cover Extraction

**Given** a valid MOBI file with an embedded cover image
**When** `MOBIParser.extract_cover(mobi_path)` is called
**Then** it opens the file with `pymobi.BookMobi()`
**And** it generates a filename using `MD5(mobi_path.encode()).hexdigest()`
**And** it calls `mobi.saveRecordImage(0, cover_path)` to extract the first image record
**And** if the cover file exists on disk after saving, it returns the string path
**And** if extraction fails, it returns `None`

#### AC-008.38: MOBI Cover Extraction Failure

**Given** any exception occurs during MOBI cover extraction
**When** `MOBIParser.extract_cover(mobi_path)` catches the exception
**Then** it logs a warning and returns `None` (never raises)

#### AC-008.39: MOBI Chapter Extraction — Regex Splitting

**Given** a valid MOBI file with chapter-like markers in the text
**When** `MOBIParser.get_chapters(mobi_path)` is called
**Then** it opens the file with `pymobi.BookMobi()` and calls `mobi.get_text()`
**And** it splits the text using regex pattern `(?:^|\n)\s*(Chapter|CHAPTER|Part|PART)\s+[IVXLCDM\d]+` with `re.MULTILINE`
**And** it skips parts with fewer than 200 stripped characters
**And** for each remaining part, it attempts to extract a title from the first line if it is shorter than 100 characters
**And** untitled parts receive `"Chapter {i+1}"` as the title
**And** it returns `list[tuple[int, str, str]]` where each tuple is `(index, title, raw_text)`

#### AC-008.40: MOBI Chapter Extraction — Single-Chapter Fallback

**Given** a valid MOBI file whose text contains no recognizable chapter markers
**When** `MOBIParser.get_chapters(mobi_path)` finds zero chapters after regex splitting
**Then** it falls back to a single chapter: `[(0, "Full Content", text_content)]`

#### AC-008.41: MOBI Chapter Count

**Given** a valid MOBI file
**When** `MOBIParser.count_chapters(mobi_path)` is called
**Then** it delegates to `get_chapters()` and returns `len(chapters)`

#### AC-008.42: MOBI Table of Contents — Fallback

**Given** a valid MOBI file
**When** `MOBIParser.get_table_of_contents(mobi_path)` is called
**Then** it attempts to check EXTH headers for TOC data
**And** since MOBI TOC extraction is limited, it falls back to the chapter list from `get_chapters()`
**And** returns `[{"index": i, "title": chapter_title, "level": 1}]` for each chapter
**And** if an exception occurs, it also falls back to the chapter list

---

### Unified Parser Interface

#### AC-008.43: All Parsers Share Identical Method Signatures

**Given** any parser instance (`EPUBParser`, `PDFParser`, or `MOBIParser`)
**When** a caller invokes any of the five core methods
**Then** each method accepts the same parameter types and returns the same types:
- `extract_metadata(path: str) -> BookCreate`
- `extract_cover(path: str) -> Optional[str]`
- `get_chapters(path: str) -> list[tuple[int, str, str]]`
- `count_chapters(path: str) -> int`
- `get_table_of_contents(path: str) -> list[dict]`

**And** all five methods are `async` on all three parsers

#### AC-008.44: All Parsers Initialize with covers_path

**Given** any parser class
**When** instantiated with `covers_path` argument
**Then** it creates the covers directory (including parents) if it does not exist
**And** stores `self.covers_path` as a `Path` object

#### AC-008.45: All Parsers Support Specific Format Constant

**Given** any parser instance
**When** `SUPPORTED_FORMAT` is accessed
**Then** `EPUBParser` returns `"EPUB"`, `PDFParser` returns `"PDF"`, `MOBIParser` returns `"MOBI"`

---

## API Contract

### Unified Parser Interface

| Method | Parameters | Return Type | Errors |
|--------|-----------|-------------|--------|
| `extract_metadata` | `path: str` | `BookCreate` | `EbookParsingError` |
| `extract_cover` | `path: str` | `Optional[str]` | None (returns `None` on failure) |
| `get_chapters` | `path: str` | `list[tuple[int, str, str]]` | `EbookParsingError` |
| `count_chapters` | `path: str` | `int` | `EbookParsingError` (PDF) |
| `get_table_of_contents` | `path: str` | `list[dict]` | None (falls back to chapter list) |

### Scanner Interface

| Method | Parameters | Return Type | Errors |
|--------|-----------|-------------|--------|
| `scan_directory` | `directory: str \| None = None` | `list[BookCreate]` | `LibraryScannerError` |
| `extract_metadata` | `ebook_path: str` | `BookCreate` | `LibraryScannerError`, `EbookParsingError` |
| `extract_cover` | `ebook_path: str` | `Optional[str]` | None |
| `get_chapters` | `ebook_path: str` | `list[tuple[int, str, str]]` | `EbookParsingError` |
| `count_chapters` | `ebook_path: str` | `int` | None |
| `get_table_of_contents` | `ebook_path: str` | `list[dict]` | `EbookParsingError` |

### Return Shape: `BookCreate`

```
BookCreate(BaseModel):
  title: str               # min_length=1, max_length=500
  author: Optional[str]    # max_length=300
  format: str              # "EPUB" | "PDF" | "MOBI"
  path: str                # min_length=1, max_length=1000
  file_size: int           # ge=0
  cover_path: Optional[str]  # max_length=1000
  publisher: Optional[str]   # max_length=300
  publish_date: Optional[str] # max_length=50
  description: Optional[str]
  language: Optional[str]     # max_length=20
  isbn: Optional[str]         # max_length=30
  total_pages: int            # ge=0, default=0
```

### Return Shape: Chapter Tuple

```
(chapter_index: int, chapter_title: str, chapter_content: str)
```
- `chapter_index`: zero-based sequential integer
- `chapter_title`: human-readable title string
- `chapter_content`: HTML string (EPUB, PDF) or raw text string (MOBI)

### Return Shape: TOC Item

```
{"index": int, "title": str, "level": int}
```
- `index`: zero-based chapter index
- `title`: chapter or section title
- `level`: nesting depth, `1` for top-level

### Error Shape

```
DawnstarError:
  message: str
  details: dict
```
- `LibraryScannerError(DawnstarError)`: scanner-level failures (bad directory, unsupported format)
- `EbookParsingError(DawnstarError)`: parser-level failures (corrupt file, DRM, parse errors)

---

## Implementation Map

| Component | File | Key Classes/Functions | External Libraries |
|-----------|------|-----------------------|--------------------|
| Scanner | `app/scanner.py` | `LibraryScanner` | — |
| EPUB Parser | `app/parsers/epub_parser.py` | `EPUBParser` | ebooklib, BeautifulSoup4, Pillow |
| PDF Parser | `app/parsers/pdf_parser.py` | `PDFParser` | PyMuPDF (fitz), pypdf, Pillow |
| MOBI Parser | `app/parsers/mobi_parser.py` | `MOBIParser` | pymobi |
| Parser Package | `app/parsers/__init__.py` | Re-exports `EPUBParser`, `PDFParser`, `MOBIParser` | — |
| Schemas | `app/schemas.py` | `BookCreate` | Pydantic |
| Exceptions | `app/exceptions.py` | `LibraryScannerError`, `EbookParsingError` | — |

---

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|------------------|-----------|---------------|--------|
| AC-008.03: Empty directory scan | `tests/test_scanner.py` | `test_scanner_empty_directory` | Covered |
| AC-008.02: Nonexistent directory | `tests/test_scanner.py` | `test_scanner_nonexistent_directory` | Covered |
| AC-008.45: EPUB parser init + format constant | `tests/test_scanner.py` | `test_epub_parser_metadata_extraction` | Covered |
| AC-008.45: PDF parser init + format constant | `tests/test_scanner.py` | `test_pdf_parser_initialization` | Covered |
| AC-008.45: MOBI parser init + format constant | `tests/test_scanner.py` | `test_mobi_parser_initialization` | Covered |
| AC-008.11: Invalid EPUB raises EbookParsingError | `tests/test_scanner.py` | `test_extract_metadata_invalid_file` | Covered |
| AC-008.04: Format detection for .epub/.pdf/.mobi | `tests/test_scanner.py` | `test_scanner_format_detection` | Covered |
| AC-008.01: Scan with real EPUB files | — | — | GAP |
| AC-008.05: DRM file skip counting | — | — | GAP |
| AC-008.06: Corrupt file error counting | — | — | GAP |
| AC-008.07: Default library path usage | — | — | GAP |
| AC-008.10: EPUB metadata with all DC fields | — | — | GAP |
| AC-008.12: EPUB cover extraction (JPEG) | — | — | GAP |
| AC-008.13: EPUB cover extraction (SVG) | — | — | GAP |
| AC-008.16: EPUB chapter extraction + skip <200 chars | — | — | GAP |
| AC-008.19: EPUB hierarchical TOC | — | — | GAP |
| AC-008.20: EPUB TOC fallback to chapter list | — | — | GAP |
| AC-008.21: PDF metadata from document info | — | — | GAP |
| AC-008.22: PDF metadata filename fallback | — | — | GAP |
| AC-008.24: PDF cover from first page render | — | — | GAP |
| AC-008.27: PDF chapter formatting (headings, bold, italic, indent) | — | — | GAP |
| AC-008.30: PDF TOC from bookmarks | — | — | GAP |
| AC-008.33: MOBI DRM detection | — | — | GAP |
| AC-008.34: MOBI DRM rejection raises EbookParsingError | — | — | GAP |
| AC-008.36: MOBI parser ImportError without pymobi | — | — | GAP |
| AC-008.39: MOBI regex chapter splitting | — | — | GAP |
| AC-008.40: MOBI single-chapter fallback | — | — | GAP |

---

## Dependencies

### External Python Packages

| Package | Import Name | Used By | Purpose |
|---------|-------------|---------|---------|
| ebooklib | `ebooklib`, `ebooklib.epub` | `EPUBParser` | EPUB reading and metadata |
| BeautifulSoup4 | `bs4.BeautifulSoup` | `EPUBParser` | HTML parsing and cleaning |
| PyMuPDF | `fitz` | `PDFParser` | PDF rendering and text extraction |
| pypdf | `pypdf.PdfReader` | `PDFParser` | PDF metadata and page count |
| Pillow | `PIL.Image` | `EPUBParser`, `PDFParser` | Image processing and resizing |
| pymobi | `pymobi.mobi.BookMobi` | `MOBIParser` | MOBI reading (optional; `ImportError` if missing) |

### Internal Dependencies

| Module | Used By | Purpose |
|--------|---------|---------|
| `app/schemas.py` | All parsers | `BookCreate` Pydantic model |
| `app/exceptions.py` | All parsers, Scanner | `EbookParsingError`, `LibraryScannerError` |
| `app/config.py` | Scanner | `get_config()` for `library_path`, `covers_path` |
| `app/logging_config.py` | All modules | `get_logger()` for structured logging |

---

## Open Questions

- None
