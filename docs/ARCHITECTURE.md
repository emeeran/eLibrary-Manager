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
│  library  reader  settings  ai_tts  stats  maintenance  │
│  categories  hidden  auth  calibre  opds                │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  Service Layer                           │
│  library_service  reader_service  categorization_service │
│  maintenance  calibre importer/sync  opds  backup  …     │
└──────────────────────────┬──────────────────────────────┘
                           │
┌─────────┬────────────────┼────────────────┬─────────────┐
│         │                │                │             │
│    ┌────▼────┐    ┌──────▼──────┐   ┌────▼────┐  ┌────▼────┐
│    │ Parsers │    │ AI Engine   │   │ Repos   │  │ Storage │
│    │ EPUB    │    │ Providers   │   │ (DAO)   │  │ Local   │
│    │ PDF     │    │ Google      │   │         │  │ NAS     │
│    │ MOBI    │    │ Ollama x2   │   │         │  │         │
│    │ CBZ/FB2 │    └─────────────┘   │         │  │         │
│    │ /MD     │                      │         │  │         │
│    └─────────┘                      │         │  │         │
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
| `routes/library.py` | `/api/library/*`, `/api/books/*`, `/api/series/*`, `/api/stats` | Library scanning, book CRUD, filtering, bulk ops, stats |
| `routes/reader.py` | `/api/books/{id}/chapter/*`, `/api/books/{id}/summary/*`, bookmarks, notes, annotations, ask/export | Content delivery, progress, AI summaries/Q&A |
| `routes/settings.py` | `/api/settings/*` | Configuration persistence, AI/NAS/PDF-viewer settings |
| `routes/ai_tts.py` | `/api/ai/*`, `/api/tts/*` | Provider management, TTS synthesis/streaming |
| `routes/stats.py` | `/api/stats/sidebar`, `/api/stats/reading` | Sidebar counts, reading sessions & goals |
| `routes/maintenance.py` | `/api/maintenance/*` | DB hygiene, vacuum, backups/restore |
| `routes/categories.py` | `/api/categories/*`, auto-categorization | Category management, auto-categorize |
| `routes/hidden.py` | `/api/books/{id}/hide`, `/unhide`, `/api/hidden/*` | Per-book password protection (spec 010) |
| `routes/auth.py` | `/api/auth/*` | Login/logout/session status |
| `routes/calibre.py` | `/api/library/import-calibre`, calibre-web links | Calibre import/sync, deep links (specs 011/013) |
| `routes/opds.py` | `/api/opds/*` | OPDS network catalogs (spec 015) |

### Services (Business Logic)

Services encapsulate domain logic and coordinate between repositories, parsers, and AI engine.

| Service | Key Operations |
|---------|---------------|
| `library_service.py` | `scan_and_import()`, `fast_index()`, `import_book()`, `get_library_stats()`, `refresh_covers()` |
| `reader_service.py` | `get_chapter_content()`, `update_progress()`, `get_chapter_summary()`, `get_book_summary()`, bookmark/note/annotation CRUD |
| `categorization_service.py` | `auto_categorize()` (rule-based + AI hybrid), `auto_categorize_all()` |
| `maintenance_service.py` / `backup_service.py` | DB hygiene tasks, backup/restore |
| `calibre_importer.py` / `calibre_sync_service.py` / `calibre_sync_monitor.py` | Calibre library import and ongoing sync (spec 011) |
| `opds_service.py` | OPDS catalog browse/download proxy (spec 015) |
| `content_extractor.py` / `content_backfill_service.py` | Full-text content extraction and FTS backfill (spec 012) |
| `annotation_embedder.py` | Write annotations back into EPUB files |
| `book_qa.py` | Grounded book Q&A |
| `metadata_enrichment.py` | AI/metadata enrichment |

### Repository (Data Access)

`repositories.py` implements the repository pattern with type-safe database operations:

- **BookRepository** — CRUD with filtering (search, format, category, favorite, hidden, series, reading status, soft delete)
- **ChapterSummaryRepository** — AI summary caching
- **BookSummaryRepository** — Full book summary caching
- **SettingsRepository** — Key-value settings storage
- Plus bookmark/note/annotation, reading session/goal, OPDS catalog, and FTS full-text-search access layers

All repositories use async SQLAlchemy sessions via the `get_db()` dependency.

### Parsers (Content Extraction)

Each format has a dedicated parser implementing common operations:

```
BaseParser (implicit interface)
├── epub_parser.py  — ebooklib + BeautifulSoup4
├── pdf_parser.py   — PyMuPDF (Fitz)
├── mobi_parser.py  — pymobi
├── cbz_parser.py   — comic book archives (zip + images)
├── fb2_parser.py   — FictionBook 2
└── md_parser.py    — Markdown
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
├── GoogleProvider (priority 1)  ─── Google Gemini API (google-genai SDK)
└── OllamaProvider               ─── OpenAI-compatible SDK
    ├── "ollama_cloud" (2)       ─── Ollama Cloud API
    └── "ollama_local" (3)       ─── Local Ollama server
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
| **Book** | Core entity — metadata, file path, reading progress, cover URL; also soft delete (`is_deleted`), Calibre mapping (`calibre_id`), hidden-book bcrypt hash (`hidden_password`), series, reading status, word count |
| **ChapterSummary** | Cached AI summary per chapter |
| **BookSummary** | Cached AI summary for entire book |
| **Bookmark** | User-defined reading marker with optional note |
| **Note** | User note attached to a chapter |
| **Annotation** | Text highlight with offset range, color, and optional note |
| **Setting** | Key-value application settings store (also holds the session epoch) |
| **Category** / **BookCategory** | Categories and the many-to-many join table |
| **ReadingSession** | Per-session reading tracking |
| **ReadingGoal** | Daily reading goal |
| **OpdsCatalog** | Registered OPDS network catalog (URL, credentials) |

Schema changes ship as Alembic migrations in `alembic/versions/` (run `uv run alembic upgrade head` after upgrading). Full-text search uses SQLite FTS tables (`books_fts` + content-search tables).

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
| `SecurityHeadersMiddleware` (`security_middleware.py`) | CSP + `X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy` headers |
| `CSRFMiddleware` (`security_middleware.py`) | Same-origin enforcement on `POST/PUT/PATCH/DELETE` |
| Auth middleware | Session validation on protected routes (stateless HMAC cookies, `app/auth.py`) |

## Security

- **Sessions:** Stateless HMAC-signed cookies (`app/auth.py`) with session-epoch revocation (logout/password change invalidate all prior tokens)
- **CSRF:** Same-origin enforcement on mutating methods, layered on the `SameSite=Lax` cookie
- **Headers:** CSP and browser-hardening headers via `SecurityHeadersMiddleware`
- **Encryption:** `cryptography.fernet` for encrypting sensitive settings values
- **Password Protection:** Hidden library feature uses per-book bcrypt hashes (spec 010); admin login uses bcrypt (`ADMIN_PASSWORD_HASH` or auto-hashed `ADMIN_PASSWORD`)
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
010-hidden-books (extends 001)
011-calibre-integration (extends 001) ──► 013-calibre-web-deep-link
012-full-text-content-search (extends 001/002)
014-default-file-viewer-integration (standalone)
015-opds-network-catalogs (extends 001)
```

The authoritative registry with versions and statuses is `specs/INDEX.md`.
