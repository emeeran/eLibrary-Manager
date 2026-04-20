# SPEC-001: Library Management

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15
- **Depends On:** SPEC-008 (File Parsers)

## Purpose

Library Management is the core feature of eLibrary Manager. It provides all capabilities for discovering, importing, organizing, and querying ebook files on the local filesystem. Users can scan directories for `.epub`, `.pdf`, and `.mobi` files; import individual files or entire directories; upload files through the browser; list and filter their collection; update metadata and favorites; track reading progress; and view aggregate statistics. Every book record is backed by a SQLite row with extracted metadata, cover image path, and reading state.

---

## Behavior

### AC-001.01: Scan Library Directory

**Given** a configured `library_path` exists on the filesystem (default `./library`)
**When** the user sends `POST /api/library/scan`
**Then** the system recursively walks that directory for files with extensions `.epub`, `.pdf`, or `.mobi`
**And** for each discovered file, the scanner extracts metadata via the appropriate format parser
**And** the service checks each extracted book against the database by file path (unique constraint)
**And** new books are inserted; existing paths are skipped
**And** the response body contains `{ "imported": N, "skipped": N, "errors": N, "total": N }`
**And** the HTTP status code is `200`

### AC-001.02: Scan Nonexistent Library Directory

**Given** the configured `library_path` does not exist on the filesystem
**When** the user sends `POST /api/library/scan`
**Then** the scanner raises a `LibraryScannerError`
**And** the route returns HTTP `500` with an error detail message

### AC-001.03: Scan Empty Library Directory

**Given** the configured `library_path` exists but contains no supported ebook files
**When** the user sends `POST /api/library/scan`
**Then** the response body contains `{ "imported": 0, "skipped": 0, "errors": 0, "total": 0 }`
**And** the HTTP status code is `200`

### AC-001.04: Scan Skips Unsupported Files

**Given** the library directory contains files with extensions other than `.epub`, `.pdf`, `.mobi`
**When** a library scan is triggered
**Then** those files are silently ignored (not counted in `total`)

### AC-001.05: Scan Handles Corrupt or DRM Files Gracefully

**Given** the library directory contains a corrupt or DRM-protected ebook file
**When** a library scan encounters that file
**Then** the scanner catches the parsing error and increments the error count
**And** DRM files are counted separately as skipped
**And** the scan continues processing remaining files
**And** the final summary accurately reports the error and skip counts

### AC-001.06: Import from Specific Directory

**Given** a valid directory path is provided in the request body `{ "path": "/some/dir" }`
**When** the user sends `POST /api/library/import-dir`
**Then** the system validates that the path exists and is a directory
**And** scans that directory (instead of the default `library_path`) following the same logic as AC-001.01
**And** returns the import summary `{ "imported", "skipped", "errors", "total" }`

### AC-001.07: Import from Invalid Directory

**Given** the provided path does not exist or is not a directory
**When** the user sends `POST /api/library/import-dir`
**Then** the route returns HTTP `400` with detail `"Directory not found: {path}"`

### AC-001.08: Import Single File by Path

**Given** a valid file path is provided in the request body `{ "file_path": "/path/to/book.epub" }`
**And** the file has a supported extension (`.epub`, `.pdf`, `.mobi`)
**When** the user sends `POST /api/library/import-file`
**Then** the system extracts metadata and cover image for that file
**And** if the file path is not already in the database, creates a new Book record
**And** returns HTTP `200` with a `BookResponse` JSON body
**And** if the file path already exists in the database, returns the existing Book record without error

### AC-001.09: Import Single File Missing file_path

**Given** the request body does not contain a `file_path` key
**When** the user sends `POST /api/library/import-file`
**Then** the route returns HTTP `400` with detail `"file_path is required"`

### AC-001.10: Import Single File Not Found on Disk

**Given** the provided `file_path` does not exist on the filesystem
**When** the user sends `POST /api/library/import-file`
**Then** the route returns HTTP `404` with detail `"File not found: {file_path}"`

### AC-001.11: Import Single File Unsupported Format

**Given** the provided `file_path` has an extension other than `.epub`, `.pdf`, `.mobi`
**When** the user sends `POST /api/library/import-file`
**Then** the route returns HTTP `400` with detail `"Unsupported file format: {ext}"`

### AC-001.12: Import Single File Parsing Failure

**Given** the file exists and has a supported extension but cannot be parsed
**When** the import attempt fails
**Then** the route returns HTTP `500` with detail `"Import failed: {error_message}"`

### AC-001.13: Upload Book File

**Given** a multipart form upload with field `file` containing a supported ebook file
**When** the user sends `POST /api/library/upload`
**Then** the system validates the file extension is `.epub`, `.pdf`, or `.mobi`
**And** saves the uploaded file to `{parent_of_library_path}/uploads/{filename}`
**And** creates the uploads directory if it does not exist
**And** imports the saved file via the same logic as single-file import
**And** returns HTTP `200` with a `BookResponse` JSON body

### AC-001.14: Upload Unsupported File Format

**Given** a multipart form upload with a file whose extension is not `.epub`, `.pdf`, or `.mobi`
**When** the user sends `POST /api/library/upload`
**Then** the route returns HTTP `400` with detail `"Unsupported file format: {ext}"`

### AC-001.15: Upload Fails Cleans Up File

**Given** an uploaded file passes extension validation but fails during import
**When** the import raises an exception
**Then** the system deletes the partially saved file from the uploads directory
**And** returns HTTP `500` with detail `"Upload failed: {error_message}"`

### AC-001.16: Refresh Covers (Missing Only)

**Given** the library contains books, some with `cover_path` set and some without
**When** the user sends `POST /api/library/refresh-covers` (no query param, defaults `force=false`)
**Then** the system iterates all books
**And** skips books that already have a `cover_path`
**And** attempts cover extraction for books missing a `cover_path`
**And** returns `{ "updated": N, "skipped": N, "errors": [...], "total": N }`

### AC-001.17: Refresh Covers (Force All)

**Given** the library contains books
**When** the user sends `POST /api/library/refresh-covers?force=true`
**Then** the system re-extracts covers for all books regardless of existing `cover_path`
**And** overwrites existing cover paths with newly extracted covers
**And** returns the refresh summary with updated count

### AC-001.18: Refresh Covers Handles Extraction Errors

**Given** a book's cover extraction fails (e.g., file deleted from disk)
**When** the refresh process encounters that book
**Then** the error is logged and appended to the errors list as `{ "book_id": N, "error": "..." }`
**And** processing continues for remaining books
**And** the final response includes all errors

### AC-001.19: List Books with Default Pagination

**Given** the library contains books
**When** the user sends `GET /api/books` (no query params)
**Then** the system returns page 1 with up to 20 books ordered by `added_date` descending
**And** the response body matches `BookListResponse`: `{ "books": [...], "total": N, "page": 1, "page_size": 20, "counts": {...} }`
**And** the `counts` object contains sidebar totals: `{ "all": N, "recent": N, "favorites": N, "reading": N, "deleted": N }`

### AC-001.20: List Books with Custom Pagination

**Given** the library contains more than `page_size` books
**When** the user sends `GET /api/books?page=2&page_size=5`
**Then** the system returns books 6 through 10 (zero-indexed offset 5)
**And** the response `page` is `2` and `page_size` is `5`
**And** `total` reflects the total number of books (not just this page)

### AC-001.21: List Books Filter by Favorites

**Given** the library contains books, some with `is_favorite=true`
**When** the user sends `GET /api/books?favorite_only=true`
**Then** the response `books` array contains only books where `is_favorite` is `true`
**And** `total` reflects the total number of books in the library (unfiltered count)

### AC-001.22: List Books Filter by Recent

**Given** the library contains books, some with `is_recent=true`
**When** the user sends `GET /api/books?recent_only=true`
**Then** the response `books` array contains only books where `is_recent` is `true`

### AC-001.23: List Books Search by Title or Author

**Given** the library contains a book titled "Dune" by "Frank Herbert"
**When** the user sends `GET /api/books?search=dune`
**Then** the response `books` array includes that book (case-insensitive ILIKE match)
**And** when the user sends `GET /api/books?search=herbert`
**Then** the response also includes that book (searches both title and author)

### AC-001.24: List Books Filter by Format

**Given** the library contains books in multiple formats
**When** the user sends `GET /api/books?format_filter=PDF`
**Then** the response `books` array contains only books where `format` is `"PDF"`

### AC-001.25: List Books Combined Filters

**Given** the library contains favorited EPUB books
**When** the user sends `GET /api/books?favorite_only=true&format_filter=EPUB`
**Then** the response contains only books matching both conditions

### AC-001.26: List Empty Library

**Given** no books exist in the database
**When** the user sends `GET /api/books`
**Then** the response is `{ "books": [], "total": 0, "page": 1, "page_size": 20, "counts": {...} }`
**And** all count values are `0`

### AC-001.27: Get Book Details

**Given** a book with ID `1` exists in the database
**When** the user sends `GET /api/books/1`
**Then** the system returns HTTP `200` with a `BookResponse` JSON body containing all book fields
**And** the book's `last_read_date` is updated to the current UTC timestamp

### AC-001.28: Get Book Not Found

**Given** no book with the requested ID exists
**When** the user sends `GET /api/books/999`
**Then** the system returns HTTP `404`

### AC-001.29: Update Book Metadata

**Given** a book with ID `1` exists
**When** the user sends `PATCH /api/books/1` with body `{ "title": "New Title", "author": "New Author" }`
**Then** the system updates only the provided fields (partial update semantics)
**And** returns HTTP `200` with the updated `BookResponse`
**And** unmentioned fields remain unchanged

### AC-001.30: Update Book Favorite Flag

**Given** a book with `is_favorite=false`
**When** the user sends `PATCH /api/books/{id}` with body `{ "is_favorite": true }`
**Then** the book's `is_favorite` is set to `true`
**And** the response reflects the change

### AC-001.31: Update Book Validation (Title Length)

**Given** a `BookUpdate` with `title` exceeding 500 characters
**When** the request is validated by Pydantic
**Then** the system returns HTTP `422` with validation error details

### AC-001.32: Update Book Validation (Progress Range)

**Given** a `BookUpdate` with `progress` set to `150`
**When** the request is validated by Pydantic
**Then** the system returns HTTP `422` because `progress` must be in `[0, 100]`

### AC-001.33: Update Book Validation (current_chapter Negative)

**Given** a `BookUpdate` with `current_chapter` set to `-1`
**When** the request is validated by Pydantic
**Then** the system returns HTTP `422` because `current_chapter` must be `>= 0`

### AC-001.34: Update Nonexistent Book

**Given** no book with the requested ID exists
**When** the user sends `PATCH /api/books/999`
**Then** the system returns HTTP `404`

### AC-001.35: Delete Book

**Given** a book with ID `1` exists
**When** the user sends `DELETE /api/books/1`
**Then** the book row is removed from the database
**And** all associated `ChapterSummary` rows are cascade-deleted
**And** the response is HTTP `200` with `{ "message": "Book deleted successfully" }`

### AC-001.36: Delete Book Not Found

**Given** no book with the requested ID exists
**When** the user sends `DELETE /api/books/999`
**Then** the system returns HTTP `404`

### AC-001.37: Toggle Favorite (True to False)

**Given** a book with ID `1` and `is_favorite=true`
**When** the user sends `POST /api/books/1/favorite`
**Then** the book's `is_favorite` is set to `false`
**And** the change is committed to the database
**And** the response is HTTP `200` with the updated `BookResponse`

### AC-001.38: Toggle Favorite (False to True)

**Given** a book with ID `1` and `is_favorite=false`
**When** the user sends `POST /api/books/1/favorite`
**Then** the book's `is_favorite` is set to `true`
**And** the response reflects the toggled state

### AC-001.39: Toggle Favorite Book Not Found

**Given** no book with the requested ID exists
**When** the user sends `POST /api/books/999/favorite`
**Then** the system returns HTTP `404`

### AC-001.40: Update Reading Progress

**Given** a book with ID `1` exists
**When** the user sends `POST /api/books/1/progress` with body `{ "chapter_index": 3, "progress": 45.5 }`
**Then** the book's `current_chapter` is set to `3`
**And** the book's `progress` is set to `45.5`
**And** the book's `is_recent` is set to `true` (since progress > 0)
**And** the response is HTTP `200` with the updated `BookResponse`

### AC-001.41: Update Progress Validation (chapter_index Negative)

**Given** a `ProgressUpdate` with `chapter_index` set to `-1`
**When** the request is validated by Pydantic
**Then** the system returns HTTP `422` because `chapter_index` must be `>= 0`

### AC-001.42: Update Progress Validation (progress Out of Range)

**Given** a `ProgressUpdate` with `progress` set to `101`
**When** the request is validated by Pydantic
**Then** the system returns HTTP `422` because `progress` must be in `[0, 100]`

### AC-001.43: Update Progress Book Not Found

**Given** no book with the requested ID exists
**When** the user sends `POST /api/books/999/progress`
**Then** the system returns HTTP `404`

### AC-001.44: Get Library Statistics

**Given** the library contains books
**When** the user sends `GET /api/stats`
**Then** the response is HTTP `200` with `{ "total_books": N, "favorite_books": N, "recent_books": N, "total_size_bytes": N }`
**And** `total_books` matches the count of all Book rows
**And** `favorite_books` is the count of books where `is_favorite=true`
**And** `recent_books` is the count of books where `is_recent=true`
**And** `total_size_bytes` is the sum of all `file_size` values

### AC-001.45: Get Library Statistics Empty Library

**Given** no books exist in the database
**When** the user sends `GET /api/stats`
**Then** the response is `{ "total_books": 0, "favorite_books": 0, "recent_books": 0, "total_size_bytes": 0 }`

### AC-001.46: Duplicate Path Prevention During Scan

**Given** the database already contains a book at path `/books/novel.epub`
**When** a library scan encounters that same file
**Then** the service detects the existing record by path lookup
**And** increments the `skipped` counter
**And** does not create a duplicate record

### AC-001.47: Cover Extraction During Import

**Given** a new book is being imported (via scan, single-file, or upload)
**When** the scanner successfully extracts a cover image
**Then** the `cover_path` field on the Book record is set to the path of the extracted cover image
**And** cover images are saved to the configured `covers_path` directory

### AC-001.48: Cover Extraction Failure Does Not Block Import

**Given** a new book is being imported
**When** cover extraction fails for that book
**Then** the book is still imported successfully with `cover_path` set to `null`
**And** no error is raised for the import itself

---

## API Contract

### Endpoints

| Method | Path | Request Body | Success Response | Error Responses |
|--------|------|-------------|-----------------|-----------------|
| POST | `/api/library/scan` | None | `200` `{ "imported", "skipped", "errors", "total" }` | `500` scanner error |
| POST | `/api/library/import-dir` | `{ "path": string }` (DirectoryImportRequest) | `200` `{ "imported", "skipped", "errors", "total" }` | `400` directory not found |
| POST | `/api/library/import-file` | `{ "file_path": string }` (raw dict) | `200` BookResponse | `400` missing file_path or unsupported format; `404` file not found; `500` import failure |
| POST | `/api/library/upload` | multipart `file` | `200` BookResponse | `400` unsupported format; `500` upload failure |
| POST | `/api/library/refresh-covers` | None (query: `force` bool) | `200` `{ "updated", "skipped", "errors", "total" }` | - |
| GET | `/api/books` | None (query: page, page_size, favorite_only, recent_only, search, format_filter) | `200` BookListResponse | - |
| GET | `/api/books/{book_id}` | None | `200` BookResponse | `404` not found |
| PATCH | `/api/books/{book_id}` | BookUpdate (partial) | `200` BookResponse | `404` not found; `422` validation |
| DELETE | `/api/books/{book_id}` | None | `200` `{ "message": "Book deleted successfully" }` | `404` not found |
| POST | `/api/books/{book_id}/favorite` | None | `200` BookResponse | `404` not found |
| POST | `/api/books/{book_id}/progress` | ProgressUpdate | `200` BookResponse | `404` not found; `422` validation |
| GET | `/api/stats` | None | `200` LibraryStats (as dict) | - |

### Data Models

```python
class BookBase(BaseModel):
    title: str           # min_length=1, max_length=500
    author: Optional[str]  # max_length=300
    format: str          # "EPUB" | "PDF" | "MOBI", default="EPUB"

class BookCreate(BookBase):
    path: str            # min_length=1, max_length=1000
    file_size: int       # ge=0
    cover_path: Optional[str]   # max_length=1000
    publisher: Optional[str]    # max_length=300
    publish_date: Optional[str] # max_length=50
    description: Optional[str]
    language: Optional[str]     # max_length=20
    isbn: Optional[str]         # max_length=30
    total_pages: int     # ge=0, default=0

class BookUpdate(BaseModel):
    title: Optional[str]         # min_length=1, max_length=500
    author: Optional[str]        # max_length=300
    is_favorite: Optional[bool]
    progress: Optional[float]    # ge=0, le=100
    current_chapter: Optional[int]  # ge=0

class BookResponse(BookBase):
    id: int
    path: str
    cover_path: Optional[str]
    total_chapters: int
    current_chapter: int
    progress: float
    is_favorite: bool
    is_recent: bool
    file_size: int
    added_date: datetime
    last_read_date: Optional[datetime]
    publisher: Optional[str]
    publish_date: Optional[str]
    description: Optional[str]
    language: Optional[str]
    isbn: Optional[str]
    total_pages: int
    # model_config: from_attributes=True

class BookListResponse(BaseModel):
    books: list[BookResponse]
    total: int
    page: int
    page_size: int
    counts: Optional[dict[str, int]]  # { all, recent, favorites, reading, deleted }

class ProgressUpdate(BaseModel):
    chapter_index: int   # ge=0
    progress: float      # ge=0, le=100

class LibraryStats(BaseModel):
    total_books: int
    favorite_books: int
    recent_books: int
    total_size_bytes: int

class DirectoryImportRequest(BaseModel):
    path: str            # min_length=1
```

### Database Model

```sql
CREATE TABLE books (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           VARCHAR(500) NOT NULL,
    author          VARCHAR(300),
    path            VARCHAR(1000) NOT NULL UNIQUE,
    cover_path      VARCHAR(1000),
    format          VARCHAR(20) NOT NULL DEFAULT 'EPUB',
    total_chapters  INTEGER DEFAULT 0,
    current_chapter INTEGER DEFAULT 0,
    progress        FLOAT DEFAULT 0.0,
    is_favorite     BOOLEAN DEFAULT 0,
    is_recent       BOOLEAN DEFAULT 1,
    file_size       INTEGER DEFAULT 0,
    added_date      DATETIME NOT NULL,
    last_read_date  DATETIME,
    publisher       VARCHAR(300),
    publish_date    VARCHAR(50),
    description     TEXT,
    language        VARCHAR(20),
    isbn            VARCHAR(30),
    total_pages     INTEGER DEFAULT 0
);

CREATE INDEX ix_books_title ON books(title);
CREATE INDEX ix_books_author ON books(author);
CREATE INDEX ix_books_is_favorite ON books(is_favorite);
CREATE INDEX ix_books_is_recent ON books(is_recent);
```

Key constraints:
- `path` is `UNIQUE` -- no two Book rows may reference the same filesystem file.
- `title` is `NOT NULL` and indexed for search performance.
- `author` is indexed for search performance.
- `is_favorite` and `is_recent` are indexed for filtered queries.
- Deleting a Book cascades to all associated `ChapterSummary` rows.

---

## Implementation Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Routes | `app/routes/library.py` | `scan_library`, `import_directory`, `import_book_file`, `upload_book`, `refresh_covers`, `list_books`, `get_book`, `update_book`, `delete_book`, `toggle_favorite`, `update_progress`, `get_library_stats` |
| Service | `app/services/library_service.py` | `LibraryService.scan_and_import`, `LibraryService.import_book`, `LibraryService.get_book`, `LibraryService.list_books`, `LibraryService.update_book`, `LibraryService.delete_book`, `LibraryService.get_library_stats`, `LibraryService.refresh_covers` |
| Reader Service | `app/services/reader_service.py` | `ReaderService.update_progress` (delegated from progress endpoint) |
| Repository | `app/repositories.py` | `BookRepository.create`, `BookRepository.get_by_id`, `BookRepository.get_by_id_or_404`, `BookRepository.get_by_path`, `BookRepository.list_all`, `BookRepository.update`, `BookRepository.update_progress`, `BookRepository.delete`, `BookRepository.count` |
| Scanner | `app/scanner.py` | `LibraryScanner.scan_directory`, `LibraryScanner.extract_metadata`, `LibraryScanner.extract_cover` |
| Models | `app/models.py` | `Book` (SQLAlchemy model) |
| Schemas | `app/schemas.py` | `BookCreate`, `BookUpdate`, `BookResponse`, `BookListResponse`, `ProgressUpdate`, `LibraryStats`, `DirectoryImportRequest` |
| Exceptions | `app/exceptions.py` | `LibraryScannerError`, `EbookParsingError`, `ResourceNotFoundError`, `ValidationError` |
| Config | `app/config.py` | `AppConfig` (library_path, covers_path) |
| Database | `app/database.py` | `get_db` (AsyncSession dependency) |

---

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|------------------|-----------|---------------|--------|
| AC-001.26 List empty library | `tests/test_api.py` | `test_list_empty_library` | Covered |
| AC-001.28 Get nonexistent book | `tests/test_api.py` | `test_get_nonexistent_book` | Covered |
| AC-001.03 Scan empty directory | `tests/test_scanner.py` | `test_scanner_empty_directory` | Covered |
| AC-001.02 Scan nonexistent directory | `tests/test_scanner.py` | `test_scanner_nonexistent_directory` | Covered |
| AC-001.01 Scan library (happy path) | `tests/test_api.py` | `test_library_scan` | Covered |
| AC-001.44 Library statistics | `tests/test_api.py` | `test_library_stats` | Covered |
| Health check (infra) | `tests/test_api.py` | `test_health_check` | Covered |
| Scanner format detection | `tests/test_scanner.py` | `test_scanner_format_detection` | Covered |
| EPUB parser initialization | `tests/test_scanner.py` | `test_epub_parser_metadata_extraction` | Covered |
| PDF parser initialization | `tests/test_scanner.py` | `test_pdf_parser_initialization` | Covered |
| MOBI parser initialization | `tests/test_scanner.py` | `test_mobi_parser_initialization` | Covered |
| Extract metadata from invalid file | `tests/test_scanner.py` | `test_extract_metadata_invalid_file` | Covered |
| AC-001.06 Import from directory | - | - | GAP |
| AC-001.07 Import from invalid directory | - | - | GAP |
| AC-001.08 Import single file | - | - | GAP |
| AC-001.09 Import single file missing path | - | - | GAP |
| AC-001.10 Import single file not found | - | - | GAP |
| AC-001.11 Import unsupported format | - | - | GAP |
| AC-001.13 Upload book file | - | - | GAP |
| AC-001.14 Upload unsupported format | - | - | GAP |
| AC-001.16 Refresh covers (missing) | - | - | GAP |
| AC-001.17 Refresh covers (force) | - | - | GAP |
| AC-001.19 List books default pagination | - | - | GAP |
| AC-001.20 List books custom pagination | - | - | GAP |
| AC-001.21 List books filter favorites | - | - | GAP |
| AC-001.22 List books filter recent | - | - | GAP |
| AC-001.23 List books search | - | - | GAP |
| AC-001.24 List books filter format | - | - | GAP |
| AC-001.25 List books combined filters | - | - | GAP |
| AC-001.27 Get book details | - | - | GAP |
| AC-001.29 Update book metadata | - | - | GAP |
| AC-001.31 Update book validation | - | - | GAP |
| AC-001.34 Update nonexistent book | - | - | GAP |
| AC-001.35 Delete book | - | - | GAP |
| AC-001.36 Delete nonexistent book | - | - | GAP |
| AC-001.37 Toggle favorite on | - | - | GAP |
| AC-001.38 Toggle favorite off | - | - | GAP |
| AC-001.39 Toggle favorite nonexistent | - | - | GAP |
| AC-001.40 Update reading progress | - | - | GAP |
| AC-001.41 Progress validation negative chapter | - | - | GAP |
| AC-001.42 Progress validation out of range | - | - | GAP |
| AC-001.45 Stats empty library | - | - | GAP |
| AC-001.46 Duplicate path prevention | - | - | GAP |
| AC-001.47 Cover extraction during import | - | - | GAP |
| AC-001.48 Cover extraction failure graceful | - | - | GAP |

---

## Dependencies

- **SPEC-008: File Parsers** -- Library scanning and metadata extraction delegate to format-specific parsers (`EPUBParser`, `PDFParser`, `MOBIParser`) defined in `app/parsers.py`. The scanner cannot function without these parsers.
- **External Libraries:**
  - `ebooklib` -- EPUB parsing
  - `PyMuPDF` (fitz) -- PDF parsing and cover extraction
  - `pymobi` -- MOBI parsing (optional; skipped if not installed)
  - `Pillow` -- Cover image processing and resizing
  - `sqlalchemy[asyncio]` + `aiosqlite` -- Async ORM and SQLite driver
  - `fastapi` -- Web framework with Pydantic validation
  - `pydantic-settings` -- Configuration management
- **Internal Services:**
  - `ReaderService` -- Progress update endpoint delegates to `ReaderService.update_progress` which also sets `is_recent` flag.

---

## Open Questions

- None. This feature is fully implemented and matches the specification above.
