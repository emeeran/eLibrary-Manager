# eLibrary Manager

A lightweight, self-hosted ebook management and reading application with AI-powered chapter summarization. Designed as a pixel-perfect digital twin of Icecream eBook Reader Pro 6.53.

## Features

- **Multi-Format Library** — Index and read EPUB, PDF, and MOBI files
- **Icecream UI Clone** — Dark-themed sidebar, rounded book cards, progress bars, grid/table views
- **Reader Themes** — Day (`#ffffff`), Sepia (`#f4ecd8`), and Night (`#1e1e1e`) with pixel-perfect hex codes
- **AI Chapter Summaries** — Multi-provider fallback chain: Google Gemini → Groq → Ollama Cloud → Ollama Local
- **Text-to-Speech** — EdgeTTS (neural voices) and gTTS engines with voice selection
- **Bookmarks & Notes** — Create bookmarks, notes, and text annotations while reading
- **Auto-Categorization** — Hybrid rule-based and AI-driven book categorization
- **NAS Integration** — SMB/NFS mount support with health monitoring and offline file caching
- **Hidden Library** — Password-protected book hiding for sensitive content
- **Reading Progress** — Automatic position synchronization across sessions
- **Search & Filter** — By title, author, format, favorites, recency, and category

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Local Development

```bash
# Clone repository
git clone <repository-url>
cd eLibrary-Manager

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env — at minimum set GEMINI_API_KEY for AI summaries

# Place ebooks in the library directory
cp /path/to/ebooks/*.epub library/

# Run the application
make dev
```

Visit **http://localhost:8000**

### Docker Deployment

```bash
# Configure environment
cp .env.example .env

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f dawnstar
```

The app is available at **http://localhost:8000** with ebooks mapped from `./library`, database in `./dawnstar_data`, and covers in `./static_covers`.

## Configuration

All configuration is managed through environment variables. Copy `.env.example` to `.env` and customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dawnstar_data/dawnstar.db` | SQLite connection string |
| `LIBRARY_PATH` | `./library` | Path to ebook collection |
| `GOOGLE_API_KEY` | — | Google Gemini API key (primary AI) |
| `GOOGLE_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `GROQ_API_KEY` | — | Groq API key (secondary AI) |
| `OLLAMA_LOCAL_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `AI_DEFAULT_PROVIDER` | `auto` | AI provider: `auto`, `google`, `groq`, `ollama_cloud`, `ollama_local` |
| `AI_ENABLE_FALLBACK` | `true` | Enable provider fallback chain |
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |
| `DEBUG` | `false` | Debug mode |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full deployment documentation.

## Project Structure

```
eLibrary-Manager/
├── backend/
│   └── app/                      # Python package
│       ├── main.py               # FastAPI entry point
│       ├── config.py             # Pydantic settings management
│       ├── database.py           # SQLite/SQLAlchemy async setup
│       ├── models.py             # ORM models (Book, Bookmark, Note, etc.)
│       ├── schemas.py            # Pydantic API schemas
│       ├── repositories.py       # Data access layer
│       ├── scanner.py            # Library scanning orchestration
│       ├── reader_engine.py      # Unified content extraction
│       ├── ai_engine.py          # Multi-provider AI orchestrator
│       ├── chapter_cache.py      # LRU chapter content cache
│       ├── middleware.py         # Custom HTTP middleware
│       ├── security.py           # Encryption and password utilities
│       ├── routes/
│       │   ├── library.py        # Library management API
│       │   ├── reader.py         # Reader functionality API
│       │   ├── settings.py       # Settings management API
│       │   └── ai_tts.py         # AI provider and TTS API
│       ├── services/
│       │   ├── library_service.py    # Library business logic
│       │   ├── reader_service.py     # Reader business logic
│       │   └── categorization_service.py  # Auto-categorization
│       ├── parsers/
│       │   ├── epub_parser.py    # EPUB format parser
│       │   ├── pdf_parser.py     # PDF format parser
│       │   ├── mobi_parser.py    # MOBI format parser
│       │   └── image_service.py  # Cover/image extraction
│       ├── ai_providers/
│       │   ├── base.py           # Abstract provider interface
│       │   ├── google_provider.py    # Google Gemini
│       │   ├── groq_provider.py      # Groq (Llama)
│       │   └── ollama_provider.py    # Ollama Cloud + Local
│       └── storage/
│           ├── local.py          # Local filesystem backend
│           ├── nas.py            # NAS/SMB backend
│           └── factory.py        # Storage backend factory
├── frontend/
│   ├── templates/                # Jinja2 HTML templates
│   │   ├── base.html             # Base layout with sidebar
│   │   ├── library.html          # Library grid/table view
│   │   ├── reader.html           # Book reader with themes
│   │   ├── settings.html         # Settings management page
│   │   └── login.html            # Authentication page
│   └── static/
│       ├── css/
│       │   ├── main.css          # Library and global styles
│       │   └── reader.css        # Reader-specific styles
│       └── js/
│           ├── library.js        # Library page interactions
│           ├── reader.js         # Reader core logic
│           ├── reader-icecream.js # Icecream UI behaviors
│           ├── settings.js       # Settings page logic
│           ├── theme.js          # Theme switching
│           ├── tts.js            # Text-to-speech controls
│           └── resize-sidebar.js # Resizable sidebar
├── specs/                        # Feature specifications (SDD)
├── tests/                        # Test suite
├── library/                      # Ebook storage directory
├── dawnstar_data/                # SQLite database
├── static_covers/                # Extracted cover images
├── static_book_images/           # Extracted book images
├── docs/                         # Documentation
├── Dockerfile                    # Multi-stage Docker build
├── Makefile                      # Development commands
└── pyproject.toml                # uv project configuration
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI, Uvicorn |
| **Database** | SQLite with WAL mode, SQLAlchemy (async via aiosqlite) |
| **Frontend** | Jinja2 templates, Tailwind CSS, vanilla JavaScript |
| **AI Providers** | Google Gemini SDK, Groq SDK, OpenAI SDK (Ollama compat) |
| **Ebook Parsing** | ebooklib (EPUB), PyPDF + PyMuPDF (PDF), pymobi (MOBI) |
| **TTS** | EdgeTTS (neural voices), gTTS (Google Translate) |
| **Package Manager** | uv |
| **Testing** | pytest, pytest-asyncio, pytest-cov |
| **Code Quality** | Black, Ruff, MyPy |
| **Security** | cryptography (Fernet encryption) |

## Development

```bash
make dev             # Run development server with auto-reload
make test            # Run tests with coverage report
make lint            # Run ruff + mypy
make format          # Format with black + ruff
make check           # Run lint + test
make clean           # Remove generated files
make install         # Install deps + pre-commit hooks
```

## AI Provider Architecture

The application uses a priority-based fallback chain for AI summarization:

```
1. Google Gemini (Primary)     ──► Highest quality, fastest
2. Groq (Secondary)            ──► Very fast inference (Llama models)
3. Ollama Cloud (Tertiary)     ──► Good quality, cloud-hosted
4. Ollama Local (Fallback)     ──► Works offline, self-hosted
```

When `AI_DEFAULT_PROVIDER=auto`, the orchestrator tries providers in priority order and falls back automatically on failure. Each provider has independent rate limiting (configurable RPM).

## Documentation

| Document | Description |
|----------|-------------|
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

## Performance Targets

- Memory footprint: **< 150 MB** idle
- SQLite WAL mode for concurrent read/write operations
- LRU chapter cache with file modification tracking
- Lazy-loaded book covers with batch fetching
- On-demand AI summarization with database caching

## License

MIT License
