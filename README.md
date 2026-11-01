# eLibrary Manager

A lightweight, self-hosted ebook management and reading application with AI-powered chapter summarization. Designed as a pixel-perfect digital twin of Icecream eBook Reader Pro 6.53.

## Features

- **Multi-Format Library** — Index and read EPUB, PDF, MOBI, CBZ, FB2, and Markdown files
- **Icecream UI Clone** — Dark-themed sidebar, rounded book cards, progress bars, grid/table views
- **Reader Themes** — Day (`#ffffff`), Sepia (`#f4ecd8`), and Night (`#1e1e1e`) with pixel-perfect hex codes
- **AI Chapter Summaries** — Multi-provider fallback chain: Google Gemini → Ollama Cloud → Ollama Local
- **AI Transform & Q&A** — Translate/define selected text and ask grounded questions about the current book
- **Text-to-Speech** — EdgeTTS (neural voices) and gTTS engines with voice selection
- **Bookmarks, Notes & Annotations** — While reading; annotations can be embedded back into EPUB files
- **Calibre Integration** — Background Calibre library import with progress streaming, sync monitoring, and Calibre-Web deep links
- **OPDS Network Catalogs** — Register and browse OPDS catalogs; credentials stay server-side; download into the library
- **Full-Text Content Search** — SQLite FTS-backed search across book contents
- **Hidden Library** — Per-book password protection (bcrypt) with rate-limited unlock and admin bulk reset
- **Auto-Categorization** — Hybrid rule-based and AI-driven book categorization
- **NAS Integration** — Serves from a pre-mounted SMB/NFS path with health monitoring and offline file caching
- **Reading Goals & Stats** — Daily reading goal, session tracking, dashboard statistics
- **Authentication** — Stateless HMAC-signed session cookies, session-epoch revocation, CSRF + hardening headers
- **Maintenance & Backups** — Backup/restore, book QA checks, soft delete
- **Reading Progress** — Automatic position synchronization across sessions
- **Search & Filter** — By title, author, format, favorites, recency, series, reading status, and category

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Local Development

```bash
# Clone repository
git clone https://github.com/emeeran/eLibrary-Manager.git
cd eLibrary-Manager

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env — at minimum set GEMINI_API_KEY (or GOOGLE_API_KEY) for AI summaries
# and ADMIN_PASSWORD for login

# Place ebooks in the library directory
cp /path/to/ebooks/*.epub library/

# Run the application
make dev
```

Visit **http://localhost:8000** and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` (defaults: `admin` / value of `ADMIN_PASSWORD`).

Alternatives to `make dev`:

- `./run-dev.sh` — binds `127.0.0.1` and picks the first free port (or `ELIBRARY_DEV_PORT`)
- `./start.sh` — loads `.env`, picks a free port from `APP_PORT`, opens the browser

### Docker Deployment

```bash
# Configure environment
cp .env.example .env

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f elibrary
```

The app is available at **http://localhost:8000** with ebooks mapped from `./library`, database in `./dawnstar_data`, and covers in `./static_covers`. An optional profile-gated `ollama` service is available via `docker-compose --profile ollama up -d`.

## Configuration

All configuration is managed through environment variables (or `.env`). Copy `.env.example` to `.env` and customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dawnstar_data/dawnstar.db` | SQLite connection string |
| `LIBRARY_PATH` | `./library` | Path to ebook collection |
| `COVERS_PATH` | `./static_covers` | Extracted cover images |
| `BOOK_IMAGES_PATH` | `./static_book_images` | Extracted book images |
| `SECRET_KEY` | `""` | Signs session cookies and encrypts settings secrets. **Required when `APP_ENV=production`** |
| `ADMIN_USERNAME` | `admin` | Login username |
| `ADMIN_PASSWORD` | `""` | Login password (plaintext, auto-hashed at startup) |
| `ADMIN_PASSWORD_HASH` | `""` | Login password as bcrypt hash (preferred over plaintext) |
| `GOOGLE_API_KEY` | `""` | Google Gemini API key (`GEMINI_API_KEY` env var takes priority) |
| `GOOGLE_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `GOOGLE_RATE_LIMIT_RPM` | `15` | Gemini requests-per-minute cap |
| `OLLAMA_CLOUD_URL` | `https://api.ollama.ai` | Ollama Cloud endpoint |
| `OLLAMA_CLOUD_MODEL` | `llama3.3` | Ollama Cloud model |
| `OLLAMA_LOCAL_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `OLLAMA_LOCAL_MODEL` | `llama3.2:3b` | Local Ollama model |
| `AI_DEFAULT_PROVIDER` | `auto` | Preferred AI provider (`auto` = priority fallback order) |
| `AI_ENABLE_FALLBACK` | `true` | Enable provider fallback chain |
| `AI_REQUEST_TIMEOUT` | `30.0` | Per-request AI timeout (seconds) |
| `AI_MAX_RETRIES` | `2` | Retries per provider |
| `NAS_ENABLED` | `false` | Enable the NAS storage backend |
| `NAS_HOST` | `""` | NAS hostname (reporting only) |
| `NAS_MOUNT_PATH` | `""` | Pre-mounted SMB/NFS path to serve |
| `NAS_CACHE_DIR` | `./nas_cache` | Offline file cache directory |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |
| `DEBUG` | `false` | Debug mode |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |
| `MAX_COVER_SIZE` | `300000` | Max cover image size (bytes) |
| `MAX_UPLOAD_SIZE_MB` | `100` | Max upload size (MB) |
| `LAZY_LOAD_BATCH_SIZE` | `20` | Covers fetched per lazy-load batch |
| `DB_POOL_SIZE` | `5` | SQLAlchemy pool size |
| `DB_MAX_OVERFLOW` | `0` | SQLAlchemy pool overflow |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment documentation.

## Project Structure

```
eLibrary-Manager/
├── backend/
│   └── app/                      # Python package (imported as `app`)
│       ├── main.py               # FastAPI entry point + middleware wiring
│       ├── config.py             # Pydantic settings management
│       ├── database.py           # SQLite/SQLAlchemy async setup
│       ├── models.py             # ORM models (Book, Bookmark, Note, etc.)
│       ├── schemas.py            # Pydantic API schemas
│       ├── repositories.py       # Data access layer
│       ├── auth.py               # Stateless signed-cookie sessions
│       ├── security.py           # Fernet/bcrypt credential helpers
│       ├── security_middleware.py # CSP headers + CSRF origin check
│       ├── middleware.py         # Logging / caching / rate limiting
│       ├── scanner.py            # Library scanning orchestration
│       ├── scan_progress.py      # Scan/import progress (SSE)
│       ├── reader_engine.py      # Unified content extraction
│       ├── ai_engine.py          # Multi-provider AI orchestrator
│       ├── chapter_cache.py      # LRU chapter content cache
│       ├── edgetts_service.py    # EdgeTTS engine
│       ├── gtts_service.py       # gTTS engine
│       ├── nas_cache.py          # NAS offline caching
│       ├── nas_health.py         # NAS health probes
│       ├── logging_config.py     # Logging setup
│       ├── exceptions.py         # Domain exceptions
│       ├── routes/               # API route modules
│       │   ├── library.py        #   Library management API
│       │   ├── reader.py         #   Reader / chapters / bookmarks API
│       │   ├── settings.py       #   Settings API
│       │   ├── ai_tts.py         #   AI provider and TTS API
│       │   ├── stats.py          #   Reading stats & goals API
│       │   ├── maintenance.py    #   Maintenance / backup API
│       │   ├── categories.py     #   Category management API
│       │   ├── hidden.py         #   Hidden-books API
│       │   ├── auth.py           #   Login/logout API
│       │   ├── calibre.py        #   Calibre import / sync / deep links
│       │   └── opds.py           #   OPDS network catalogs API
│       ├── services/             # Service layer (library, reader, categorization,
│       │                         #   maintenance, calibre importer/sync, OPDS,
│       │                         #   annotation embedder, content search, backup, …)
│       ├── parsers/              # Format parsers
│       │   ├── epub_parser.py    #   EPUB (ebooklib)
│       │   ├── pdf_parser.py     #   PDF (PyMuPDF)
│       │   ├── mobi_parser.py    #   MOBI (pymobi)
│       │   ├── cbz_parser.py     #   CBZ comic archives
│       │   ├── fb2_parser.py     #   FB2 fiction books
│       │   ├── md_parser.py      #   Markdown
│       │   └── image_service.py  #   Cover/image extraction
│       ├── ai_providers/
│       │   ├── base.py           # Abstract provider interface
│       │   ├── google_provider.py    # Google Gemini (google-genai SDK)
│       │   └── ollama_provider.py    # Ollama Cloud + Local (OpenAI SDK)
│       └── storage/
│           ├── local.py          # Local filesystem backend
│           ├── nas.py            # NAS backend (pre-mounted path)
│           └── factory.py        # Storage backend factory
├── frontend/
│   ├── templates/                # Jinja2 HTML templates
│   │   ├── library.html          # Library grid/table view
│   │   ├── reader.html           # Book reader with themes
│   │   ├── settings.html         # Settings management page
│   │   ├── maintenance.html      # Maintenance page
│   │   └── login.html            # Authentication page
│   └── static/
│       ├── css/                  # main.css, reader.css
│       └── js/
│           ├── library.js        # Library page interactions
│           ├── settings.js       # Settings page logic
│           ├── opds.js           # OPDS catalog browser
│           ├── tts.js            # Text-to-speech controls
│           ├── theme.js          # Theme switching
│           ├── lib/              # Shared helpers (api, dom, notify, storage)
│           └── reader/           # Reader split by concern:
│                                 #   state, chapters, panels, settings, search,
│                                 #   annotations, summary, tts-bridge, autoscroll,
│                                 #   ui, init, globals
├── specs/                        # Feature specifications (SDD) — see specs/INDEX.md
├── alembic/                      # Database migrations
├── tests/                        # Pytest suite (35 files)
├── library/                      # Ebook storage directory
├── dawnstar_data/                # SQLite database + WAL
├── static_covers/                # Extracted cover images
├── static_book_images/           # Extracted book images
├── packaging/deb/                # .deb packaging + systemd unit
├── docs/                         # Documentation
├── Dockerfile                    # Multi-stage Docker build
├── docker-compose.yml            # App + optional Ollama service
├── Makefile                      # Development commands
├── run-dev.sh / start.sh         # Launcher scripts
└── pyproject.toml                # uv project configuration
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, Uvicorn |
| **Database** | SQLite with WAL mode, SQLAlchemy (async via aiosqlite), Alembic migrations |
| **Frontend** | Jinja2 templates, Tailwind-inspired utility CSS, vanilla JavaScript |
| **AI Providers** | google-genai (Gemini), OpenAI SDK (Ollama Cloud + Local) |
| **Ebook Parsing** | ebooklib (EPUB), PyMuPDF (PDF), pymobi (MOBI), stdlib/BeautifulSoup (CBZ, FB2, MD) |
| **HTML Sanitization** | nh3 |
| **TTS** | EdgeTTS (neural voices), gTTS (Google Translate) |
| **Package Manager** | uv |
| **Testing** | pytest, pytest-asyncio, pytest-cov |
| **Code Quality** | Black, Ruff, MyPy |
| **Security** | cryptography (Fernet), bcrypt |

## Development

```bash
make help           # List all targets
make dev            # Run development server with auto-reload (binds 0.0.0.0:8000)
make run            # Alias for dev
make test           # Run tests with coverage report
make lint           # Run ruff + mypy
make format         # Format with black + ruff
make check          # Run lint + test
make clean          # Remove generated files
make install        # Install deps + pre-commit hooks
make docker-build   # Build the Docker image
make docker-up      # docker-compose up -d
make docker-down    # docker-compose down
make docker-logs    # Tail container logs
make deb            # Build the .deb package
make deb-install    # Install the built .deb (sudo)
```

## AI Provider Architecture

The application uses a priority-based fallback chain for AI summarization:

```
1. Google Gemini (Primary)     ──► Highest quality, fastest
2. Ollama Cloud (Secondary)    ──► Cloud-hosted Llama models
3. Ollama Local (Fallback)     ──► Works offline, self-hosted
```

When `AI_DEFAULT_PROVIDER=auto`, the orchestrator tries providers in priority order and falls back automatically on failure. Each provider has independent rate limiting (configurable RPM). Gemini is used via the `google-genai` SDK; both Ollama endpoints use the OpenAI-compatible SDK.

## Documentation

| Document | Description |
|----------|-------------|
| [User Manual](USER_MANUAL.md) | Installation, workflows, configuration, troubleshooting |
| [API Reference](docs/API.md) | REST API endpoints, schemas, and examples |
| [Architecture](docs/ARCHITECTURE.md) | System design, data flow, and component diagrams |
| [Deployment](docs/DEPLOYMENT.md) | Docker, local dev, NAS setup, and environment config |

## Spec-Driven Development

All features are governed by formal specifications in `specs/`. See [specs/INDEX.md](specs/INDEX.md) for the full registry:

| ID | Feature | Status |
|----|---------|--------|
| 001 | Library Management | Active |
| 002 | Reader Interface | Active |
| 003 | AI Summarization | Active |
| 004 | Bookmarks | Active |
| 005 | Notes & Annotations | Active |
| 006 | Text-to-Speech | Active |
| 007 | Settings | Active |
| 008 | File Parsers | Active |
| 009 | NAS Integration | Active |
| 010 | Hidden Books | Active |
| 011 | Calibre Integration | Active |
| 012 | Full-Text Content Search | Active |
| 013 | Calibre-Web → eLM Reader Deep Link | Active |
| 014 | Default File Viewer Integration | Active |
| 015 | OPDS Network Catalogs | Active |

## Performance Targets

- Memory footprint: **< 150 MB** idle
- SQLite WAL mode for concurrent read/write operations
- LRU chapter cache with file modification tracking
- Lazy-loaded book covers with batch fetching
- On-demand AI summarization with database caching

## License

MIT License
