# API Reference

Base URL: `http://localhost:8000`

The API follows RESTful conventions. All request/response bodies are JSON. Page routes return rendered HTML.

---

## Table of Contents

- [Pages](#pages)
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
- [Health](#health)

---

## Pages

### `GET /`

Render the library home page with book grid/table view.

### `GET /reader/{book_id}`

Render the book reader page.

### `GET /settings`

Render the settings management page.

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

Delete a book from the library (removes database record; optionally deletes file).

**Response:** `200 OK`

```json
{
  "message": "Book deleted"
}
```

### `POST /api/books/{book_id}/favorite`

Toggle the favorite status of a book.

**Response:** `200 OK`

```json
{
  "is_favorite": true
}
```

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

### `DELETE /api/books/{book_id}/bookmarks/{bookmark_id}`

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

### `PATCH /api/books/{book_id}/notes/{note_id}`

Update a note.

### `DELETE /api/books/{book_id}/notes/{note_id}`

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

### `DELETE /api/books/{book_id}/annotations/{annotation_id}`

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
      "model": "gemini-1.5-flash"
    },
    {
      "name": "groq",
      "display_name": "Groq",
      "priority": 2,
      "available": true,
      "model": "llama-3.3-70b-versatile"
    },
    {
      "name": "ollama_cloud",
      "display_name": "Ollama Cloud",
      "priority": 3,
      "available": false,
      "model": "llama3.3"
    },
    {
      "name": "ollama_local",
      "display_name": "Ollama Local",
      "priority": 4,
      "available": true,
      "model": "llama3.3"
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
  "provider": "groq"
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

---

## Hidden Books

### `POST /api/library/hide/{book_id}`

Hide a book (requires password).

### `POST /api/library/unhide/{book_id}`

Unhide a book (requires password).

### `POST /api/library/hidden`

List all hidden books (requires password).

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
| 404 | `BookNotFound` | Book ID does not exist |
| 400 | `EbookParsingError` | Failed to parse ebook file |
| 500 | `LibraryScannerError` | Scanner encountered an error |
| 503 | `AIProviderError` | All AI providers failed |
| 429 | — | Rate limit exceeded |
| 500 | `DatabaseError` | Database operation failed |

Custom exception hierarchy (defined in `backend/app/exceptions.py`):

```
DawnstarError (base)
├── DatabaseError
├── LibraryScannerError
├── EbookParsingError
├── AIProviderError
├── BookNotFoundError
├── ConfigurationError
└── StorageError
```
