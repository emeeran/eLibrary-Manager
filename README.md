# eLibrary Manager

A lightweight, pixel-perfect clone of Icecream eBook Reader Pro 6.53 with AI-powered chapter summarization.

## Features

- **Multi-Format Library Support** - EPUB, PDF, and MOBI file indexing
- **Pixel-Perfect UI** - Icecream Reader clone with Day/Sepia/Night themes
- **Multi-Provider AI Summaries** - Google -> Groq -> Ollama Cloud -> Ollama Local fallback
- **Text-to-Speech** - Browser-based read-aloud functionality
- **Progress Tracking** - Reading position synchronization
- **Search & Filter** - By title, author, format, favorites, recent

## Quick Start

### Local Development

```bash
# Clone repository
git clone <repository-url>
cd dawstar-eBook

# Install dependencies
uv sync

# Place ebook files in library directory
cp /path/to/ebooks/*.epub library/

# Run application
PYTHONPATH=backend uv run uvicorn app.main:app --reload
```

Visit http://localhost:8000

### Docker Deployment

```bash
# Configure environment
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f elibrary
```

## Configuration

See `.env.example` for all configuration options including:

- **Database**: SQLite connection string
- **Library Paths**: Where your ebooks are stored
- **AI Providers**: Configuration for all 4 providers (Google, Groq, Ollama Cloud, Ollama Local)
- **Application**: Host, port, debug mode, logging level

## Development

```bash
# Install dependencies
uv sync

# Run development server
make dev

# Testing
make test

# Code quality
make lint
make format

# Docker
make docker-build
make docker-up
make docker-logs
```

## Project Structure

```
elibrary-manager/
├── backend/
│   └── app/                      # Python package
│       ├── main.py               # FastAPI entry point
│       ├── config.py             # Configuration management
│       ├── database.py           # Database connection
│       ├── models.py             # SQLAlchemy models
│       ├── schemas.py            # Pydantic schemas
│       ├── exceptions.py         # Custom exceptions
│       ├── repositories.py       # Data access layer
│       ├── routes/               # API route modules
│       ├── services/             # Business logic
│       ├── parsers/              # Format parsers (EPUB, PDF, MOBI)
│       ├── ai_providers/         # AI providers (Google, Groq, Ollama)
│       ├── storage/              # Storage backends (local, NAS)
│       ├── scanner.py            # Library scanner
│       ├── reader_engine.py      # Content extraction
│       └── ai_engine.py          # AI orchestrator
├── frontend/
│   ├── templates/                # Jinja2 HTML templates
│   └── static/                   # CSS, JS, images
├── tests/                        # Test suite
├── specs/                        # Feature specifications
├── library/                      # Your ebook files
├── dawnstar_data/                # Database storage (legacy dir name)
├── static_covers/                # Extracted covers
├── static_book_images/           # Extracted book images
└── pyproject.toml                # UV package config
```

## Technology Stack

- **Backend**: Python 3.12+, FastAPI, uvicorn
- **Database**: SQLite + SQLAlchemy (async)
- **Frontend**: Jinja2 + Tailwind CSS
- **AI Providers**: Google Gemini, Groq, Ollama
- **Package Manager**: uv (ultra-fast)
- **Testing**: pytest, pytest-asyncio
- **Code Quality**: black, ruff, mypy

## AI Provider Fallback

The app automatically falls back through providers:

1. **Google Gemini** (Primary) - Fastest, highest quality
2. **Groq** (Secondary) - Very fast inference
3. **Ollama Cloud** (Tertiary) - Good quality
4. **Ollama Local** (Fallback) - Works offline

## License

MIT License

## Acknowledgments

Based on the Icecream eBook Reader Pro 6.53 design. All trademarks are property of their respective owners.
