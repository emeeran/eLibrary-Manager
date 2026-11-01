# API Reference

Base URL: `http://localhost:8000`

The API follows RESTful conventions. All request/response bodies are JSON. Page routes return rendered HTML.

---

## Table of Contents

- [Pages](#pages)
- [Authentication](#authentication)
- [Library Management](#library-management)
- [Books](#books)
- [Reader](#reader)
- [Bookmarks](#bookmarks)
- [Notes](#notes)
- [Annotations](#annotations)
- [AI Providers](#ai-providers)
- [Text-to-Speech](#text-to-speech)
- [Settings](#settings)
- [Categories](#categories)
- [Hidden Books](#hidden-books)
- [Stats](#stats)
- [Maintenance](#maintenance)
- [Calibre Integration](#calibre-integration)
- [OPDS Catalogs](#opds-catalogs)
- [Health](#health)

---

## Pages

### `GET /`

Render the library home page with book grid/table view.

### `GET /reader/{book_id}`

Render the book reader page.

### `GET /settings`

Render the settings management page.

### `GET /login`

Render the login page.

### `GET /maintenance`

Render the maintenance page.

### `GET /open?book_id={id}`

Hand the book file to the system default viewer (spec 014).

### `GET /calibre/launch?calibre_id={id}`

Calibre-Web deep link: resolves the book via its indexed `calibre_id` and redirects to `/reader/{book_id}` (spec 013).

---

## Authentication

Session auth is enabled on the API. Login issues an HMAC-signed cookie.

### `POST /api/auth/login`

**Request Body:**

```json
{
  "username": "admin",
  "password": "..."
}
```

### `POST /api/auth/logout`

Invalidate the current session (bumps the session epoch).

### `GET /api/auth/status`

Return whether the current session is authenticated.

---

## Library Management

### `POST /api/library/scan`

Trigger a full library scan. Scans the configured `LIBRARY_PATH` for supported ebook files and imports new books.

**Response:** `200 OK`

```json
{
  "scan_id": "uuid-string",
  "message": "Scan started"
}
```

### `GET /api/library/scan-progress/{scan_id}`

Stream scan progress via Server-Sent Events (SSE).

**Response:** `text/event-stream`

```
data: {"status": "scanning", "current": 15, "total": 42, "current_file": "book.epub"}

data: {"status": "complete", "imported": 38, "skipped": 4, "errors": 0}
```

### `POST /api/library/import-dir`

Import all ebooks from a specific directory.

**Request Body:**

```json
{
  "directory": "/path/to/ebooks"
}
```

### `POST /api/library/import-file`

Import a single ebook file.

**Request Body:**

```json
{
  "file_path": "/path/to/book.epub"
}
```

### `POST /api/library/upload`

Upload a book file via multipart form data.

**Request:** `multipart/form-data` with field `file`

### `POST /api/library/scan-cancel/{scan_id}`

Cancel a running scan.

### `POST /api/library/index-local-dir`

Index a server-local directory into the library.

### `GET /api/library/browse-fs`

Browse the server filesystem (used by the import dialogs).

### `GET /api/library/directories`

List configured library directories.

---

## Books

### `GET /api/books`

List books with optional filters.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Search by title or author |
| `format` | string | Filter by format: `epub`, `pdf`, `mobi` |
| `category` | string | Filter by category name |
| `favorite` | boolean | Filter favorites only |
| `recent` | boolean | Sort by recently opened |
| `hidden` | boolean | Include hidden books (requires password) |
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Items per page (default: 20) |
| `view` | string | View mode: `grid`, `table` |

**Response:** `200 OK`

```json
{
  "books": [
    {
      "id": 1,
      "title": "Book Title",
      "author": "Author Name",
      "format": "epub",
      "file_path": "/library/book.epub",
      "cover_url": "/static_covers/1.jpg",
      "description": "A brief description",
      "publisher": "Publisher",
      "publish_date": "2024-01-01",
      "isbn": "978-0-000-00000-0",
      "language": "en",
      "page_count": 320,
      "file_size": 2048000,
      "progress": 0.45,
      "current_chapter": 5,
      "is_favorite": false,
      "is_hidden": false,
      "last_opened": "2026-04-15T10:30:00",
      "categories": ["Fiction", "Sci-Fi"],
      "added_date": "2026-04-10T08:00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "per_page": 20
}
```

### `GET /api/books/{book_id}`

Get details for a single book.

**Response:** `200 OK` — single book object (see above).

### `PATCH /api/books/{book_id}`

Update book metadata.

**Request Body (partial):**

```json
{
  "title": "Updated Title",
  "author": "Updated Author"
}
```

### `DELETE /api/books/{book_id}`

Soft-delete a book (sets `is_deleted`; the file is kept).

### `POST /api/books/{book_id}/restore`

Restore a soft-deleted book.

### `POST /api/books/{book_id}/favorite`

Toggle the favorite status of a book.

**Response:** `200 OK`

```json
{
  "is_favorite": true
}
```

### Additional book endpoints

| Method & Path | Purpose |
|---|---|
| `PATCH /api/books/bulk` | Bulk metadata update over a set of book IDs |
| `POST /api/books/{book_id}/cover` | Replace/refresh the cover image |
| `POST /api/books/{book_id}/progress` | Save reading progress |
| `POST /api/books/{book_id}/session` | Record a reading session |
| `POST /api/books/{book_id}/enrich` | AI/metadata enrichment of book metadata |
| `POST /api/books/{book_id}/cache` / `DELETE .../cache` | Warm/evict the chapter cache |
| `GET /api/books/series`, `GET /api/series`, `GET /api/series/{name}` | Series listing and detail |

### `GET /api/stats`

Get library statistics.

**Response:** `200 OK`

```json
{
  "total_books": 42,
  "total_authors": 28,
  "formats": {"epub": 30, "pdf": 10, "mobi": 2},
  "favorites": 5,
  "categories": 8,
  "total_size_mb": 512.4
}
```

---

## Reader

### `GET /api/books/{book_id}/chapters`

Get all chapter titles/metadata for a book.

**Response:** `200 OK`

```json
{
  "chapters": [
    {"index": 0, "title": "Chapter 1: Introduction"},
    {"index": 1, "title": "Chapter 2: Getting Started"}
  ],
  "total": 12
}
```

### `GET /api/books/{book_id}/chapter/{chapter_index}`

Get the content of a specific chapter. For EPUB/MOBI returns HTML content; for PDF returns page image data.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `reload` | boolean | Force reload (bypass cache) |

**Response:** `200 OK`

```json
{
  "chapter_index": 0,
  "title": "Chapter 1",
  "content": "<html>...</html>",
  "total_chapters": 12
}
```

### `GET /api/books/{book_id}/page-image/{page_index}`

Render a PDF page as an image (PDF format only).

**Response:** Image file (`image/png`)

### `GET /api/books/{book_id}/toc`

Get the table of contents for a book.

**Response:** `200 OK`

```json
{
  "toc": [
    {"level": 0, "title": "Part I", "href": "part1.xhtml"},
    {"level": 1, "title": "Chapter 1", "href": "ch1.xhtml"}
  ]
}
```

### `GET /api/books/{book_id}/summary/{chapter_index}`

Get an AI-generated summary for a specific chapter. Generates on first request and caches the result.

**Response:** `200 OK`

```json
{
  "chapter_index": 0,
  "summary": "This chapter introduces the main concepts...",
  "provider": "google",
  "cached": true
}
```

### `GET /api/books/{book_id}/summary`

Get an AI-generated summary for the entire book.

**Response:** `200 OK`

```json
{
  "book_id": 1,
  "summary": "This book covers...",
  "provider": "google"
}
```

### Additional reader endpoints

| Method & Path | Purpose |
|---|---|
| `POST /api/books/{book_id}/ask` | Grounded Q&A about the book (AI) |
| `POST /api/books/{book_id}/bookmarks/generate` | AI-generated bookmark suggestions |
| `POST /api/books/{book_id}/annotations/embed` | Write annotations back into the EPUB file |
| `GET /api/books/{book_id}/export` | Export the book with embedded annotations |

---

## Bookmarks

### `POST /api/books/{book_id}/bookmarks`

Create a bookmark.

**Request Body:**

```json
{
  "chapter_index": 3,
  "position": 0.65,
  "note": "Important passage"
}
```

### `GET /api/books/{book_id}/bookmarks`

List all bookmarks for a book.

### `DELETE /api/bookmarks/{bookmark_id}`

Delete a bookmark.

---

## Notes

### `POST /api/books/{book_id}/notes`

Create a note.

**Request Body:**

```json
{
  "chapter_index": 2,
  "content": "My thoughts on this section..."
}
```

### `GET /api/books/{book_id}/notes`

List all notes for a book.

### `DELETE /api/notes/{note_id}`

Delete a note.

---

## Annotations

### `POST /api/books/{book_id}/annotations`

Create a text annotation (highlight).

**Request Body:**

```json
{
  "chapter_index": 1,
  "start_offset": 120,
  "end_offset": 180,
  "text": "Highlighted text",
  "color": "#ffeb3b",
  "note": "Why this matters"
}
```

### `GET /api/books/{book_id}/annotations`

List all annotations for a book.

### `DELETE /api/annotations/{annotation_id}`

Delete an annotation.

---

## AI Providers

### `GET /api/ai/providers`

List all configured AI providers and their status.

**Response:** `200 OK`

```json
{
  "providers": [
    {
      "name": "google",
      "display_name": "Google Gemini",
      "priority": 1,
      "available": true,
      "model": "gemini-2.5-flash"
    },
    {
      "name": "ollama_cloud",
      "display_name": "Ollama Cloud",
      "priority": 2,
      "available": false,
      "model": "llama3.3"
    },
    {
      "name": "ollama_local",
      "display_name": "Ollama Local",
      "priority": 3,
      "available": true,
      "model": "llama3.2:3b"
    }
  ]
}
```

### `GET /api/ai/providers/active`

Get the currently active AI provider.

### `POST /api/ai/providers/switch`

Switch the active AI provider.

**Request Body:**

```json
{
  "provider": "ollama_local"
}
```

---

## Text-to-Speech

### `GET /api/tts/engines`

List available TTS engines.

**Response:** `200 OK`

```json
{
  "engines": [
    {"id": "edge_tts", "name": "EdgeTTS (Neural)", "default": true},
    {"id": "gtts", "name": "Google TTS", "default": false}
  ]
}
```

### `GET /api/tts/voices`

List available voices for a given engine.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `engine` | string | TTS engine ID |
| `language` | string | Language code (e.g., `en`) |

### `POST /api/tts/synthesize`

Generate speech from text.

**Request Body:**

```json
{
  "text": "Text to speak...",
  "engine": "edge_tts",
  "voice": "en-US-AriaNeural",
  "rate": "+0%",
  "pitch": "+0Hz"
}
```

**Response:** Audio file (`audio/mpeg`)

### `POST /api/tts/stream`

Stream synthesized speech as an audio stream (used for long passages).

---

## Settings

### `GET /api/settings`

Get current application settings.

### `POST /api/settings`

Save application settings.

**Request Body:**

```json
{
  "settings": {
    "ai_provider": "google",
    "ai_fallback": true,
    "default_theme": "sepia",
    "auto_categorize": true
  }
}
```

### `POST /api/settings/test-ai`

Test the connection to an AI provider.

**Request Body:**

```json
{
  "provider": "google"
}
```

**Response:**

```json
{
  "success": true,
  "provider": "google",
  "model": "gemini-1.5-flash",
  "latency_ms": 342
}
```

### `GET /api/settings/nas-health`

Check NAS storage health status.

### `POST /api/settings/test-nas`

Test NAS connection.

### `GET /api/settings/pdf-viewer` / `POST /api/settings/pdf-viewer`

Get/set the PDF viewing mode (page-image vs. native viewer).

---

## Categories

### `GET /api/categories`

List all book categories.

### `POST /api/categories`

Create a new category.

**Request Body:**

```json
{
  "name": "Science Fiction",
  "color": "#3b82f6"
}
```

### `DELETE /api/categories/{category_id}`

Delete a category.

### `POST /api/books/{book_id}/categories`

Assign categories to a book.

**Request Body:**

```json
{
  "category_ids": [1, 3, 5]
}
```

### `DELETE /api/books/{book_id}/categories/{category_id}`

Remove a category from a book.

### `POST /api/books/{book_id}/auto-categorize`

Auto-categorize a single book (hybrid rule-based + AI).

### `GET /api/library/auto-categorize-stream`

Stream bulk auto-categorization progress via SSE.

---

## Hidden Books

Per-book password protection (spec 010). Passwords are stored as one-way
bcrypt hashes; unlock attempts are rate-limited and lock out after 5 failures.

### `POST /api/books/{book_id}/hide`

Hide a book behind a password.

**Request Body:**

```json
{
  "password": "choose-a-password"
}
```

### `POST /api/books/{book_id}/unhide`

Verify the password and unhide the book. Rate-limited; locked out after 5 failed attempts.

### `GET /api/hidden/status`

Return the hidden/unlocked status of books.

### `POST /api/hidden/unhide-all`

Admin action: reveal all hidden books (bulk reset).

---

## Stats

### `GET /api/stats`

Library-wide statistics (totals, formats, favorites, categories, size).

### `GET /api/stats/sidebar`

Lightweight counts for the sidebar badges.

### `GET /api/stats/reading`

Reading statistics: sessions, daily goal progress (`daily_goal_minutes`, default 30).

---

## Maintenance

All under `/api/maintenance` (spec-governed DB hygiene and backups):

| Method & Path | Purpose |
|---|---|
| `GET /api/maintenance/summary` | Overview counts (stale/duplicates/orphans/FK status) |
| `GET /api/maintenance/stale-books` / `DELETE ...` | Find/remove stale entries |
| `GET /api/maintenance/duplicates` / `DELETE ...` | Find/remove duplicate books |
| `GET /api/maintenance/orphans` / `DELETE ...` | Find/remove orphan records |
| `GET /api/maintenance/fk-status` | Foreign-key integrity report |
| `POST /api/maintenance/vacuum` | SQLite VACUUM |
| `POST /api/maintenance/reoptimize-covers` | Re-optimize stored cover images |
| `GET /api/maintenance/progress/{task_id}` | Poll a long-running maintenance task |
| `GET /api/maintenance/backups` | List database backups |
| `POST /api/maintenance/backup` | Create a database backup |
| `POST /api/maintenance/restore` | Restore from a backup |

---

## Calibre Integration

Specs 011/013.

| Method & Path | Purpose |
|---|---|
| `POST /api/library/import-calibre` | Start a background Calibre library import (progress via `GET /api/library/scan-progress/{scan_id}` SSE) |
| `GET /api/library/calibre-status` | Import/sync status |
| `GET /api/books/{book_id}/calibre-web-url` | Calibre-Web deep-link URL for a book |
| `GET /api/books/{book_id}/open-calibre-web` | Open the book in Calibre-Web |

---

## OPDS Catalogs

Spec 015. Registered network catalogs; credentials are stored server-side.

| Method & Path | Purpose |
|---|---|
| `GET /api/opds/catalogs` / `POST /api/opds/catalogs` | List/register catalogs |
| `PUT /api/opds/catalogs/{catalog_id}` / `DELETE /api/opds/catalogs/{catalog_id}` | Update/remove a catalog |
| `GET /api/opds/catalogs/{catalog_id}/browse` | Proxied browse of the remote catalog |
| `POST /api/opds/catalogs/{catalog_id}/download` | Download an entry into the library |

---

## Health

### `GET /api/health`

Application health check.

**Response:** `200 OK`

```json
{
  "status": "healthy",
  "database": "connected",
  "library_path": "/app/library"
}
```

---

## Error Responses

All API errors follow a consistent format:

```json
{
  "detail": "Human-readable error message",
  "error_type": "DawnstarError"
}
```

**Common error types:**

| HTTP Status | Error Type | Description |
|-------------|-----------|-------------|
| 404 | `ResourceNotFoundError` | Requested resource does not exist |
| 400 | `ValidationError` | Input validation failed |
| 400 | `EbookParsingError` | Failed to parse ebook file |
| 500 | `DatabaseError` | Database operation failed |
| 500 | `LibraryScannerError` | Scanner encountered an error |
| 429 | `RateLimitError` | Rate limit exceeded |
| 502 | `OpdsCatalogError` | Remote OPDS catalog fetch/parse failed |
| 503 | `AIServiceError` | All AI providers failed |
| 500 | `TTSError` | Text-to-speech synthesis failed |

Custom exception hierarchy (defined in `backend/app/exceptions.py`):

```
DawnstarError (base)
├── DatabaseError
├── LibraryScannerError
├── EbookParsingError
├── AIServiceError
├── ValidationError
├── ResourceNotFoundError
├── RateLimitError
└── OpdsCatalogError

TTSError (standalone — not a DawnstarError subclass)
```
