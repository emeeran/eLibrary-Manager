# Architecture

## System Overview

eLibrary Manager is a monolithic web application built on a layered architecture pattern:

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Client)                      │
│  Jinja2 Templates + Tailwind CSS + Vanilla JavaScript   │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────┐
│                   FastAPI (Routes)                       │
│  library.py  reader.py  settings.py  ai_tts.py          │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  Service Layer                           │
│  library_service  reader_service  categorization_service │
└──────────────────────────┬──────────────────────────────┘
                           │
┌─────────┬────────────────┼────────────────┬─────────────┐
│         │                │                │             │
│    ┌────▼────┐    ┌──────▼──────┐   ┌────▼────┐  ┌────▼────┐
│    │ Parsers │    │ AI Engine   │   │ Repos   │  │ Storage │
│    │ EPUB    │    │ Providers   │   │ (DAO)   │  │ Local   │
│    │ PDF     │    │ Google      │   │         │  │ NAS     │
│    │ MOBI    │    │ Groq        │   │         │  │         │
│    └─────────┘    │ Ollama x2   │   │         │  │         │
│                   └─────────────┘   │         │  │         │
│                                     └────┬────┘  └─────────┘
└──────────────────────────────────────────┼─────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │   SQLite    │
                                    │  (WAL mode) │
                                    └─────────────┘
```

## Layer Responsibilities

### Routes (API Layer)

Route modules handle HTTP concerns: request parsing, response formatting, and status codes. They delegate all business logic to services.

| Route Module | Endpoints | Responsibility |
|-------------|-----------|----------------|
| `routes/library.py` | `/api/library/*`, `/api/books/*`, `/api/stats`, `/api/categories/*` | Library scanning, book CRUD, filtering, stats |
| `routes/reader.py` | `/api/books/{id}/chapter/*`, `/api/books/{id}/summary/*`, bookmarks, notes, annotations | Content delivery, progress, AI summaries |
| `routes/settings.py` | `/api/settings/*` | Configuration persistence, AI/NAS testing |
| `routes/ai_tts.py` | `/api/ai/*`, `/api/tts/*` | Provider management, TTS synthesis |

### Services (Business Logic)

Services encapsulate domain logic and coordinate between repositories, parsers, and AI engine.

| Service | Key Operations |
|---------|---------------|
| `library_service.py` | `scan_and_import()`, `fast_index()`, `import_book()`, `get_library_stats()`, `refresh_covers()` |
| `reader_service.py` | `get_chapter_content()`, `update_progress()`, `get_chapter_summary()`, `get_book_summary()`, bookmark/note/annotation CRUD |
| `categorization_service.py` | `auto_categorize()` (rule-based + AI hybrid), `auto_categorize_all()` |

### Repository (Data Access)

`repositories.py` implements the repository pattern with type-safe database operations:

- **BookRepository** — CRUD with filtering (search, format, category, favorite, hidden)
- **ChapterSummaryRepository** — AI summary caching
- **BookSummaryRepository** — Full book summary caching
- **SettingsRepository** — Key-value settings storage

All repositories use async SQLAlchemy sessions via the `get_db()` dependency.

### Parsers (Content Extraction)

Each format has a dedicated parser implementing common operations:

```
BaseParser (implicit interface)
├── epub_parser.py  — ebooklib + BeautifulSoup4
├── pdf_parser.py   — PyPDF + PyMuPDF (Fitz)
└── mobi_parser.py  — pymobi
```

Each parser provides:
- `extract_metadata(file_path)` → title, author, ISBN, publisher, etc.
- `extract_cover(file_path, book_id)` → saves cover image to `static_covers/`
- `get_chapters(file_path)` → list of chapter content
- `get_table_of_contents(file_path)` → hierarchical TOC

The PDF parser additionally supports:
- `get_smart_chapters()` — groups pages into logical chapters
- `render_page_as_image()` — renders pages as PNG images

`image_service.py` handles cover and inline image extraction/storage, with per-book image directories under `static_book_images/`.

### AI Engine (Multi-Provider Orchestration)

```
AIProviderOrchestrator
├── GoogleProvider (priority 1)  ─── Google Gemini API
├── GroqProvider (priority 2)    ─── Groq Cloud API
├── OllamaCloudProvider (3)      ─── Ollama Cloud API
└── OllamaLocalProvider (4)      ─── Local Ollama server
```

**Fallback chain:**

1. Request arrives for summary
2. Orchestrator tries the highest-priority available provider
3. On failure (rate limit, timeout, error), falls back to next provider
4. All providers implement `BaseAIProvider` with `generate_summary(request) -> str`
5. Each provider has independent rate limiting (configurable RPM)

**Caching:** Generated summaries are persisted in the database (`ChapterSummary`, `BookSummary` models) so subsequent requests are instant.

### Storage (Filesystem Abstraction)

```
StorageBackend (interface)
├── LocalStorage  — direct filesystem access
└── NASStorage    — SMB/NFS mount with health monitoring
```

`storage/factory.py` creates the appropriate backend based on configuration. The NAS backend includes:
- `NASHealthMonitor` — periodic background health checks
- `NASFileCache` — LRU disk cache for offline access with size-based eviction

## Data Models

```
┌──────────┐     ┌───────────────────┐
│   Book   │────<│   ChapterSummary  │
│          │     └───────────────────┘
│  id      │     ┌───────────────────┐
│  title   │────<│    BookSummary    │
│  author  │     └───────────────────┘
│  format  │     ┌───────────────────┐
│  path    │────<│    Bookmark       │
│  cover   │     └───────────────────┘
│  progress│     ┌───────────────────┐
│          │────<│      Note         │
│          │     └───────────────────┘
│          │     ┌───────────────────┐
│          │────<│   Annotation      │
└────┬─────┘     └───────────────────┘
     │
     │ M:N via BookCategory
     │
┌────▼─────┐
│ Category │
└──────────┘
```

| Model | Purpose |
|-------|---------|
| **Book** | Core entity — metadata, file path, reading progress, cover URL |
| **ChapterSummary** | Cached AI summary per chapter |
| **BookSummary** | Cached AI summary for entire book |
| **Bookmark** | User-defined reading marker with optional note |
| **Note** | User note attached to a chapter |
| **Annotation** | Text highlight with offset range, color, and optional note |
| **Setting** | Key-value application settings store |
| **Category** | User-defined book categories with colors |
| **BookCategory** | Many-to-many join table |

## Caching Strategy

### Chapter Cache (`chapter_cache.py`)

In-memory LRU cache for chapter content:

- Tracks file modification time — cache invalidates when source file changes
- Evicts least-recently-used entries when capacity is reached
- Provides cache statistics (hits, misses, size)

### Summary Cache

AI-generated summaries are persisted in SQLite:

- First request triggers AI generation
- Subsequent requests return cached result instantly
- Cache keyed by `(book_id, chapter_index, provider)`

### NAS File Cache (`nas_cache.py`)

Disk-based LRU cache for NAS-stored ebooks:

- Caches accessed files locally for offline reading
- Size-based eviction with configurable maximum
- Metadata tracking for cache management

## Middleware Stack

| Middleware | Purpose |
|-----------|---------|
| `GZipMiddleware` | Compress responses > 1KB |
| `LoggingMiddleware` | Request/response logging with timing |
| `CacheControlMiddleware` | Cache headers for static assets |
| `RateLimitMiddleware` | Per-IP rate limiting on expensive endpoints |

## Security

- **Encryption:** `cryptography.fernet` for encrypting sensitive settings values
- **Password Protection:** Hidden library feature uses hashed passwords via `security.py`
- **Rate Limiting:** Configurable per-IP rate limits on scan, AI, and TTS endpoints
- **Input Validation:** Pydantic schemas validate all API inputs

## Background Tasks

| Task | Trigger | Purpose |
|------|---------|---------|
| NAS Health Monitor | Application startup | Periodic NAS availability checks |
| Scan Progress | `POST /api/library/scan` | SSE progress streaming |
| Cover Extraction | During scan | Async cover image extraction |

## Spec Dependency Graph

```
008-file-parsers ──► 001-library-management ──► 002-reader-interface
                                                    │
                                                    ├──► 003-ai-summarization
                                                    ├──► 004-bookmarks
                                                    ├──► 005-notes-annotations
                                                    └──► 006-text-to-speech

007-settings (standalone — affects all via configuration)
009-nas-integration (standalone — storage layer)
```
