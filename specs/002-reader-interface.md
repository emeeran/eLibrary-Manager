# SPEC-002: Reader Interface

- **Status:** Active
- **Version:** 1.0.0
- **Last Updated:** 2026-04-15

## Purpose

The Reader Interface provides the core book-reading experience in eLibrary Manager. It is responsible for rendering ebook chapter content (EPUB, PDF, MOBI), maintaining a performant server-side chapter cache, tracking reading progress, and exposing the API endpoints consumed by the Icecream-style reader UI. This spec covers chapter retrieval, table-of-contents navigation, bookmark management, note management, annotation (highlight) management, AI-powered chapter and book summarization, and the frontend rendering layer.

## Behavior

### AC-002.01: Get Chapter Content

**Given** a book exists with id `{book_id}` and has one or more chapters
**When** the client sends `GET /api/books/{book_id}/chapter/{chapter_index}`
**Then** the system returns HTTP 200 with JSON body `{ content, title, total_chapters, current_chapter }`
**And** `content` is the raw HTML of the requested chapter
**And** `title` is the chapter title string
**And** `total_chapters` is the total number of chapters in the book
**And** `current_chapter` equals the requested `chapter_index`
**And** the `Book.last_read_date` field is updated to the current UTC timestamp
**And** the response includes `Cache-Control: public, max-age=3600, immutable`
**And** the response includes an `ETag` header of the form `"book-{book_id}-ch-{chapter_index}"`

### AC-002.02: Get Chapter Content — Cached

**Given** a chapter was previously fetched and is present in the LRU chapter cache
**When** the same chapter is requested again and the source file has not been modified
**Then** the system returns the cached content without re-parsing the ebook file
**And** the cache entry is moved to the most-recently-used position

### AC-002.03: Get Chapter Content — Cache Invalidation

**Given** a chapter is present in the LRU cache
**When** the source ebook file's modification time (`file_mtime`) differs from the cached value
**Then** the cache entry is evicted
**And** the chapter is re-parsed from the source file
**And** the fresh content is stored in the cache

### AC-002.04: Get Chapter Content — Book Not Found

**Given** no book exists with the given `{book_id}`
**When** the client sends `GET /api/books/{book_id}/chapter/{chapter_index}`
**Then** the system returns HTTP 404 with an `ErrorResponse` body

### AC-002.05: Get Chapter Content — Chapter Out of Range

**Given** a book exists with `{total_chapters}` chapters
**When** the client requests `chapter_index >= total_chapters`
**Then** the system returns HTTP 404 with a `ResourceNotFoundError`

### AC-002.06: Get Table of Contents

**Given** a book exists with id `{book_id}`
**When** the client sends `GET /api/books/{book_id}/toc`
**Then** the system returns HTTP 200 with a `TOCResponse` body
**And** `items` is a list of `TOCItem` objects each with `index`, `title`, `level` (>= 1), and optional `children`
**And** `total_chapters` equals `Book.total_chapters`

### AC-002.07: Get Table of Contents — Book Not Found

**Given** no book exists with the given `{book_id}`
**When** the client sends `GET /api/books/{book_id}/toc`
**Then** the system returns HTTP 404

### AC-002.08: Get Chapter Summary

**Given** a book exists with id `{book_id}` and chapter at `{chapter_index}`
**When** the client sends `GET /api/books/{book_id}/summary/{chapter_index}`
**Then** the system returns HTTP 200 with `{ summary, provider, created_at }`
**And** if a cached summary exists and `refresh` is `false` (default), the cached summary is returned
**And** if `refresh=true` or no cached summary exists, the system generates a new AI summary
**And** the AI summary context includes the book title and author
**And** a `ChapterSummary` record is persisted in the database with `provider` set to the active AI provider name

### AC-002.09: Get Chapter Summary — Cached

**Given** a `ChapterSummary` record exists for `{book_id}` and `{chapter_index}`
**When** the client requests the summary without `refresh=true`
**Then** the system returns the existing summary without invoking the AI engine

### AC-002.10: Get Chapter Summary — Force Refresh

**Given** a cached summary exists for the chapter
**When** the client sends `GET /api/books/{book_id}/summary/{chapter_index}?refresh=true`
**Then** the system generates a new AI summary regardless of the cache
**And** the new summary is persisted as a new `ChapterSummary` record

### AC-002.11: Get Chapter Summary — Chapter Not Found

**Given** `{chapter_index}` is out of range for the book
**When** the client requests a summary
**Then** the system returns HTTP 404 with a `ResourceNotFoundError`

### AC-002.12: Get Full Book Summary

**Given** a book exists with id `{book_id}`
**When** the client sends `GET /api/books/{book_id}/summary`
**Then** the system returns HTTP 200 with `{ summary, provider, created_at }`
**And** if a cached book summary exists and `refresh` is `false`, the cached summary is returned
**And** if `refresh=true` or no cached summary exists, the system:
  - Retrieves all chapters
  - Generates or retrieves cached summaries for each individual chapter
  - Combines all chapter summaries into a single text
  - Sends the combined text to the AI for a comprehensive book-level summary
  - Persists the result via `BookSummaryRepository.create_or_update`

### AC-002.13: Get Full Book Summary — Cached

**Given** a `BookSummary` record exists for `{book_id}`
**When** the client requests the book summary without `refresh=true`
**Then** the system returns the existing book summary without regenerating

### AC-002.14: Create Bookmark

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/bookmarks` with a valid `BookmarkCreate` body
**Then** the system creates a `Bookmark` record in the database
**And** returns HTTP 200 with a `BookmarkResponse` including the generated `id` and `created_at`
**And** `chapter_index` must be >= 0
**And** `position_in_chapter` defaults to 0 and must be >= 0
**And** `title` and `notes` are optional string fields

### AC-002.15: List Bookmarks

**Given** a book exists with id `{book_id}`
**When** the client sends `GET /api/books/{book_id}/bookmarks`
**Then** the system returns HTTP 200 with a `BookmarksResponse` body
**And** `bookmarks` is a list of `BookmarkResponse` objects
**And** bookmarks are ordered by `created_at` descending (most recent first)

### AC-002.16: Delete Bookmark

**Given** a bookmark exists with id `{bookmark_id}`
**When** the client sends `DELETE /api/bookmarks/{bookmark_id}`
**Then** the system deletes the bookmark from the database
**And** returns HTTP 200 with `{ "message": "Bookmark deleted successfully" }`

### AC-002.17: Jump to Bookmark

**Given** a bookmark exists with id `{bookmark_id}`
**When** the client sends `GET /api/bookmarks/{bookmark_id}/jump`
**Then** the system returns HTTP 200 with `{ chapter_index, position_in_chapter }`
**And** the client uses this data to navigate the reader to the bookmarked position

### AC-002.18: Jump to Bookmark — Not Found

**Given** no bookmark exists with `{bookmark_id}`
**When** the client sends `GET /api/bookmarks/{bookmark_id}/jump`
**Then** the system returns HTTP 404 with a `ResourceNotFoundError`

### AC-002.19: Create Note

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/notes` with a valid `NoteCreate` body
**Then** the system creates a `Note` record in the database
**And** returns HTTP 200 with a `NoteResponse` including generated `id`, `created_at`, and `updated_at`
**And** `content` is required and must be non-empty
**And** `color` defaults to `"yellow"` and must be one of: `yellow`, `green`, `blue`, `pink`, `orange`
**And** `chapter_index` must be >= 0
**And** `position_in_chapter` defaults to 0 and must be >= 0
**And** `quoted_text` is an optional string

### AC-002.20: List Notes

**Given** a book exists with id `{book_id}`
**When** the client sends `GET /api/books/{book_id}/notes`
**Then** the system returns HTTP 200 with a `NotesResponse` body
**And** `notes` is a list of `NoteResponse` objects
**And** notes are ordered by `created_at` descending

### AC-002.21: Delete Note

**Given** a note exists with id `{note_id}`
**When** the client sends `DELETE /api/notes/{note_id}`
**Then** the system deletes the note from the database
**And** returns HTTP 200 with `{ "message": "Note deleted successfully" }`

### AC-002.22: Create Annotation

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/annotations` with a valid `AnnotationCreate` body
**Then** the system creates an `Annotation` record in the database
**And** returns HTTP 200 with an `AnnotationResponse` including generated `id` and `created_at`
**And** `chapter_index` must be >= 0
**And** `start_position` must be >= 0
**And** `end_position` must be >= 0
**And** `text` is required and must be non-empty
**And** `color` defaults to `"yellow"` and must be one of: `yellow`, `green`, `blue`, `pink`, `orange`
**And** `note` is an optional string

### AC-002.23: List Annotations

**Given** a book exists with id `{book_id}`
**When** the client sends `GET /api/books/{book_id}/annotations`
**Then** the system returns HTTP 200 with an `AnnotationsResponse` body
**And** `annotations` is a list of `AnnotationResponse` objects ordered by `start_position` ascending
**When** the optional query parameter `chapter_index` is provided
**Then** only annotations for that chapter are returned
**When** `chapter_index` is omitted
**Then** all annotations for the book are returned

### AC-002.24: Delete Annotation

**Given** an annotation exists with id `{annotation_id}`
**When** the client sends `DELETE /api/annotations/{annotation_id}`
**Then** the system deletes the annotation from the database
**And** returns HTTP 200 with `{ "message": "Annotation deleted successfully" }`

### AC-002.25: Chapter Cache — LRU Eviction

**Given** the chapter cache contains `max_size` (default 200) entries
**When** a new chapter is cached via `put()`
**Then** the least-recently-used entry is evicted before the new entry is added
**And** the cache size never exceeds `max_size`

### AC-002.26: Chapter Cache — Book Invalidation

**Given** the cache contains multiple chapters for a single book path
**When** `invalidate_book(book_path)` is called
**Then** all cache entries with keys starting with `{book_path}:` are removed
**And** the method returns the count of entries removed

### AC-002.27: Chapter Cache — Full Clear

**When** `clear()` is called on the `ChapterCache` instance
**Then** all cached entries are removed regardless of book path

### AC-002.28: Chapter Cache — Statistics

**When** the `stats` property is accessed
**Then** it returns a dictionary with keys: `size`, `max_size`, `hits`, `misses`, `hit_rate`
**And** `hit_rate` is a percentage string formatted to one decimal place

### AC-002.29: Chapter Cache — Thread Safety

**Given** the `ChapterCache` uses an `asyncio.Lock`
**When** concurrent `get()`, `put()`, `invalidate_book()`, or `clear()` calls are made
**Then** all operations are serialized through the lock to prevent data corruption

### AC-002.30: Update Reading Progress

**Given** a book exists with id `{book_id}`
**When** the client sends `POST /api/books/{book_id}/progress` with a `ProgressUpdate` body
**Then** the system updates `Book.current_chapter` and `Book.progress` on the book record
**And** if `progress > 0`, the system sets `Book.is_recent = True`
**And** returns the updated `BookResponse`
**And** `chapter_index` must be >= 0
**And** `progress` must be between 0.0 and 100.0 inclusive

### AC-002.31: Reader Engine — Get Text for Summary

**Given** a book exists at `ebook_path` with chapter at `{chapter_index}`
**When** `get_text_for_summary(ebook_path, chapter_index, max_chars=15000)` is called
**Then** the system returns the chapter text content
**And** if the content exceeds `max_chars` characters, it is truncated to `max_chars`
**And** truncation is logged at DEBUG level

### AC-002.32: Reader Themes — Day

**When** the `data-theme` attribute on the `<html>` element is set to `"day"`
**Then** the reading area background is `#ffffff` and text color is `#1a1a1a`

### AC-002.33: Reader Themes — Sepia

**When** the `data-theme` attribute is set to `"sepia"` or `"sepia-light"`
**Then** the reading area background is `#f4ecd8` and text color is `#5b4636`

### AC-002.34: Reader Themes — Sepia Dark

**When** the `data-theme` attribute is set to `"sepia-dark"`
**Then** the reading area background is `#2a2418` and text color is `#d4c5a5`

### AC-002.35: Reader Themes — Night

**When** the `data-theme` attribute is set to `"night"`
**Then** the reading area background is `#1e1e1e` and text color is `#d1d1d1`

### AC-002.36: Page Layout — Single

**When** the page layout is set to `"single"`
**Then** the chapter content is rendered in a single column with `max-width: 850px`, centered

### AC-002.37: Page Layout — Double

**When** the page layout is set to `"double"`
**Then** the chapter content is rendered in two CSS columns with `max-width: 1400px`, `column-gap: 60px`, and a `column-rule` divider
**And** headings and paragraphs use `break-inside: avoid` to prevent splits across columns

### AC-002.38: Page Layout — Continuous

**When** the page layout is set to `"continuous"`
**Then** the chapter content is rendered in a single column with `max-width: 850px`, centered, with continuous vertical scrolling

### AC-002.39: Reader Page Rendering

**Given** a book exists with id `{book_id}`
**When** the browser requests `GET /reader/{book_id}`
**Then** the server renders the `reader.html` template with `{ request, book_id }`
**And** the template includes the Icecream-style reader UI

### AC-002.40: Annotation Highlight Colors

**Given** annotations exist with various color values
**When** highlights are rendered in the chapter content
**Then** the CSS classes map as follows:
  - `yellow` maps to `.hl-yellow` (background `#fff59d`)
  - `green` maps to `.hl-green` (background `#c8e6c9`)
  - `blue` maps to `.hl-blue` (background `#bbdefb`)
  - `pink` maps to `.hl-pink` (background `#f8bbd0`)

### AC-002.41: Selection Context Menu

**When** the user selects text within the reading area
**Then** a floating context menu (`.ic-selection-menu`) appears near the selection
**And** the menu includes highlight color swatches (yellow, green, blue, pink) and a note-creation tool
**And** the menu animates in with a `ic-pop-in` CSS animation (scale 0.8 to 1.0, fade in)

### AC-002.42: Sidebar Navigation Panels

**Given** the reader UI is rendered
**When** the user toggles the Table of Contents panel
**Then** the left sidebar (`.ic-toc-sidebar`, 280px wide) slides open or collapses
**When** the user toggles the Notes panel
**Then** the left sidebar (`.ic-notes-sidebar`, 280px wide) slides open or collapses
**When** the user toggles the Bookmarks panel
**Then** the left sidebar (`.ic-bookmarks-sidebar`, 280px wide) slides open or collapses
**When** the user toggles the Search panel
**Then** the left sidebar (`.ic-search-sidebar`, 280px wide) slides open or collapses
**When** the user toggles the Book Info panel
**Then** the right sidebar (`.ic-bookinfo-sidebar`, 280px wide) slides open or collapses
**When** the user toggles the Summary panel
**Then** the right sidebar (`.ic-summary-sidebar`, 320px wide) slides open or collapses
**When** the user toggles the Settings panel
**Then** the right sidebar (`.ic-settings-sidebar`, 280px wide) slides open or collapses

### AC-002.43: Chapter Typography

**Given** chapter content is rendered in the reading area
**Then** the text uses Georgia / Times New Roman / serif font stack at 18px
**And** line-height is 1.7 with justified text alignment
**And** orphans and widows are set to 3 for pagination quality
**And** the first paragraph supports drop-cap styling via `.first-paragraph::first-letter`

### AC-002.44: Performance — Content Visibility

**Given** the chapter text is rendered in the reading area
**Then** CSS `content-visibility: auto` is applied to `.ic-chapter-text` and child paragraph elements
**And** `contain-intrinsic-size` hints are set for off-screen content rendering optimization
**And** the reading area uses `will-change: scroll-position` and `transform: translateZ(0)` for GPU-accelerated scrolling

### AC-002.45: Performance — Cached Chapter Rendering

**When** chapter content is served from the server-side cache
**Then** the `.ic-cached` class is applied to the chapter text element
**And** a faster fade-in animation (0.1s) is used instead of the default loading animation

### AC-002.46: Responsive Layout — Tablet (<=1024px)

**When** the viewport width is 1024px or less
**Then** the summary sidebar becomes absolutely positioned with a drop shadow instead of inline
**And** when collapsed it translates off-screen to the right

### AC-002.47: Responsive Layout — Mobile (<=768px)

**When** the viewport width is 768px or less
**Then** all left sidebars become absolutely positioned with drop shadows
**And** the book title in the header is hidden
**And** chapter content padding is reduced to 30px 20px
**And** tab labels are hidden, showing only icons

### AC-002.48: Accessibility — Focus Indicators

**When** keyboard focus lands on `.ic-tab`, `.ic-window-btn`, or `.ic-chapter-item`
**Then** a 2px solid blue outline with 2px offset is displayed
**And** mouse-triggered focus does not show the outline (via `:focus:not(:focus-visible)`)

### AC-002.49: Accessibility — Reduced Motion

**When** the user's system preference is `prefers-reduced-motion: reduce`
**Then** all CSS animations and transitions are reduced to 0.01ms
**And** scroll behavior is set to `auto` (no smooth scrolling)

### AC-002.50: AI Provider Status

**Given** the ReaderService is initialized
**When** `get_ai_providers_status()` is called
**Then** the system returns a dictionary with status of all configured AI providers

**When** `get_active_ai_provider()` is called
**Then** the system returns the name of the currently active AI provider

**When** `switch_ai_provider(provider_name)` is called with a valid provider name
**Then** the system performs a health check on the target provider
**And** if healthy, moves it to position 0 (highest priority) in the provider list
**And** returns `{ active_provider, provider_order }`
**When** the provider name is not found, the system raises `ValueError`
**When** the provider fails the health check, the system raises `ValueError`

## API Contract

### Endpoints

| Method | Path | Request Body | Query Params | Response Type | Purpose |
|--------|------|-------------|-------------|---------------|---------|
| GET | `/api/books/{book_id}/chapter/{chapter_index}` | — | — | `{ content, title, total_chapters, current_chapter }` | Get chapter HTML content |
| GET | `/api/books/{book_id}/toc` | — | — | `TOCResponse` | Get table of contents |
| GET | `/api/books/{book_id}/summary/{chapter_index}` | — | `refresh: bool = false` | `{ summary, provider, created_at }` | Get chapter AI summary |
| GET | `/api/books/{book_id}/summary` | — | `refresh: bool = false` | `{ summary, provider, created_at }` | Get full book AI summary |
| GET | `/api/books/{book_id}/bookmarks` | — | — | `BookmarksResponse` | List all bookmarks |
| POST | `/api/books/{book_id}/bookmarks` | `BookmarkCreate` | — | `BookmarkResponse` | Create a bookmark |
| DELETE | `/api/bookmarks/{bookmark_id}` | — | — | `{ message }` | Delete a bookmark |
| GET | `/api/bookmarks/{bookmark_id}/jump` | — | — | `{ chapter_index, position_in_chapter }` | Get bookmark jump data |
| GET | `/api/books/{book_id}/notes` | — | — | `NotesResponse` | List all notes |
| POST | `/api/books/{book_id}/notes` | `NoteCreate` | — | `NoteResponse` | Create a note |
| DELETE | `/api/notes/{note_id}` | — | — | `{ message }` | Delete a note |
| GET | `/api/books/{book_id}/annotations` | — | `chapter_index: int = null` | `AnnotationsResponse` | List annotations |
| POST | `/api/books/{book_id}/annotations` | `AnnotationCreate` | — | `AnnotationResponse` | Create an annotation |
| DELETE | `/api/annotations/{annotation_id}` | — | — | `{ message }` | Delete an annotation |
| POST | `/api/books/{book_id}/progress` | `ProgressUpdate` | — | `BookResponse` | Update reading progress |

Note: The `POST /api/books/{book_id}/progress` endpoint is defined in `app/routes/library.py` but is listed here because it is semantically part of the reader workflow.

### Data Models

#### TOCItem

```python
class TOCItem(BaseModel):
    index: int           # Chapter index
    title: str           # Chapter title
    level: int = 1       # Nesting level (ge=1)
    children: list["TOCItem"] = []  # Child chapters (recursive)
```

#### TOCResponse

```python
class TOCResponse(BaseModel):
    items: list[TOCItem]
    total_chapters: int
```

#### BookmarkCreate

```python
class BookmarkCreate(BaseModel):
    chapter_index: int           # ge=0
    position_in_chapter: int = 0 # ge=0
    title: Optional[str] = None  # max_length=500
    notes: Optional[str] = None
```

#### BookmarkResponse

```python
class BookmarkResponse(BaseModel):
    id: int
    book_id: int
    chapter_index: int
    position_in_chapter: int
    title: Optional[str]
    notes: Optional[str]
    created_at: datetime
```

#### BookmarksResponse

```python
class BookmarksResponse(BaseModel):
    bookmarks: list[BookmarkResponse]
```

#### NoteCreate

```python
class NoteCreate(BaseModel):
    chapter_index: int           # ge=0
    position_in_chapter: int = 0 # ge=0
    content: str                 # min_length=1
    color: str = "yellow"        # pattern: yellow|green|blue|pink|orange
    quoted_text: Optional[str] = None
```

#### NoteResponse

```python
class NoteResponse(BaseModel):
    id: int
    book_id: int
    chapter_index: int
    position_in_chapter: int
    content: str
    color: str
    quoted_text: Optional[str]
    created_at: datetime
    updated_at: datetime
```

#### NotesResponse

```python
class NotesResponse(BaseModel):
    notes: list[NoteResponse]
```

#### AnnotationCreate

```python
class AnnotationCreate(BaseModel):
    chapter_index: int    # ge=0
    start_position: int   # ge=0
    end_position: int     # ge=0
    text: str             # min_length=1
    color: str = "yellow" # pattern: yellow|green|blue|pink|orange
    note: Optional[str] = None
```

#### AnnotationResponse

```python
class AnnotationResponse(BaseModel):
    id: int
    book_id: int
    chapter_index: int
    start_position: int
    end_position: int
    text: str
    color: str
    note: Optional[str]
    created_at: datetime
```

#### AnnotationsResponse

```python
class AnnotationsResponse(BaseModel):
    annotations: list[AnnotationResponse]
```

#### ProgressUpdate

```python
class ProgressUpdate(BaseModel):
    chapter_index: int      # ge=0
    progress: float         # ge=0, le=100
```

#### CachedChapter (Internal)

```python
@dataclass
class CachedChapter:
    content: str
    title: str
    total_chapters: int
    cached_at: datetime
    file_mtime: float  # File modification time for invalidation
```

## Implementation Map

| Component | File | Key Functions |
|-----------|------|---------------|
| Routes | `app/routes/reader.py` | `get_chapter`, `get_summary`, `get_book_summary`, `get_table_of_contents`, `list_bookmarks`, `create_bookmark`, `delete_bookmark`, `jump_to_bookmark`, `list_notes`, `create_note`, `delete_note`, `list_annotations`, `create_annotation`, `delete_annotation` |
| Service | `app/services/reader_service.py` | `ReaderService.get_chapter_content`, `ReaderService.update_progress`, `ReaderService.get_chapter_summary`, `ReaderService.get_book_summary`, `ReaderService.get_table_of_contents`, `ReaderService.create_bookmark`, `ReaderService.list_bookmarks`, `ReaderService.get_bookmark`, `ReaderService.delete_bookmark`, `ReaderService.create_note`, `ReaderService.list_notes`, `ReaderService.delete_note`, `ReaderService.create_annotation`, `ReaderService.list_annotations`, `ReaderService.delete_annotation`, `ReaderService.get_ai_providers_status`, `ReaderService.get_active_ai_provider`, `ReaderService.switch_ai_provider` |
| Engine | `app/reader_engine.py` | `ReaderEngine.get_chapter_content`, `ReaderEngine.get_total_chapters`, `ReaderEngine.get_all_chapters`, `ReaderEngine.get_text_for_summary`, `ReaderEngine.get_table_of_contents` |
| Cache | `app/chapter_cache.py` | `ChapterCache.get`, `ChapterCache.put`, `ChapterCache.invalidate_book`, `ChapterCache.clear`, `ChapterCache.stats`, `get_chapter_cache` |
| Schemas | `app/schemas.py` | `TOCItem`, `TOCResponse`, `BookmarkCreate`, `BookmarkResponse`, `BookmarksResponse`, `NoteCreate`, `NoteResponse`, `NotesResponse`, `AnnotationCreate`, `AnnotationResponse`, `AnnotationsResponse`, `ProgressUpdate`, `CachedChapter` |
| Models | `app/models.py` | `Bookmark`, `Note`, `Annotation`, `ChapterSummary`, `BookSummary` |
| Repositories | `app/repositories.py` | `BookRepository`, `ChapterSummaryRepository`, `BookSummaryRepository` |
| Page Route | `app/main.py` | `reader_page` (GET /reader/{book_id}) |
| Templates | `app/templates/reader.html` | Reader HTML (Icecream UI) |
| CSS | `app/static/css/reader.css` | Reader styles (themes, layout, sidebars, typography, annotations) |
| JS | `app/static/js/reader.js` | Core reader logic |
| JS | `app/static/js/reader-icecream.js` | Icecream-specific UI interactions |

## Test Coverage

| Spec Requirement | Test File | Test Function | Status |
|-----------------|-----------|---------------|--------|
| AC-002.01 Get Chapter Content | — | — | GAP |
| AC-002.02 Cached Chapter | — | — | GAP |
| AC-002.03 Cache Invalidation | — | — | GAP |
| AC-002.04 Book Not Found | `tests/test_api.py` | `test_get_nonexistent_book` | PARTIAL — tests library endpoint, not reader |
| AC-002.05 Chapter Out of Range | — | — | GAP |
| AC-002.06 Get TOC | — | — | GAP |
| AC-002.07 TOC Book Not Found | — | — | GAP |
| AC-002.08 Get Chapter Summary | — | — | GAP |
| AC-002.09 Cached Summary | — | — | GAP |
| AC-002.10 Force Refresh Summary | — | — | GAP |
| AC-002.11 Summary Chapter Not Found | — | — | GAP |
| AC-002.12 Get Full Book Summary | — | — | GAP |
| AC-002.13 Cached Book Summary | — | — | GAP |
| AC-002.14 Create Bookmark | — | — | GAP |
| AC-002.15 List Bookmarks | — | — | GAP |
| AC-002.16 Delete Bookmark | — | — | GAP |
| AC-002.17 Jump to Bookmark | — | — | GAP |
| AC-002.18 Bookmark Not Found | — | — | GAP |
| AC-002.19 Create Note | — | — | GAP |
| AC-002.20 List Notes | — | — | GAP |
| AC-002.21 Delete Note | — | — | GAP |
| AC-002.22 Create Annotation | — | — | GAP |
| AC-002.23 List Annotations | — | — | GAP |
| AC-002.24 Delete Annotation | — | — | GAP |
| AC-002.25 Cache LRU Eviction | — | — | GAP |
| AC-002.26 Cache Book Invalidation | — | — | GAP |
| AC-002.27 Cache Full Clear | — | — | GAP |
| AC-002.28 Cache Statistics | — | — | GAP |
| AC-002.29 Cache Thread Safety | — | — | GAP |
| AC-002.30 Update Progress | — | — | GAP |
| AC-002.31 Get Text for Summary | — | — | GAP |
| AC-002.32–002.49 Frontend Themes/Layout/Accessibility | — | — | GAP (requires Playwright/E2E) |
| AC-002.50 AI Provider Status | — | — | GAP |

## Dependencies

- **SPEC-001: Library Management** — Book records must exist before reading; progress update endpoint lives in library routes
- **SPEC-003: AI Summarization** — Chapter and book summaries depend on the AI engine (`app/ai_engine.py`)
- **SPEC-008: File Parsers** — Chapter content extraction depends on `LibraryScanner.get_chapters()` and `LibraryScanner.get_table_of_contents()` for EPUB/PDF/MOBI parsing

## Open Questions

- None
