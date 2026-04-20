# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

**Phase: Active Development (Spec-Driven Development)**

The application is fully implemented. All features are governed by formal specifications in `specs/`. See `specs/INDEX.md` for the spec registry.

## Project Overview

eLibrary Manager is a lightweight web application for managing and reading large ebook collections with AI-powered chapter summarization. The design goal is a pixel-perfect digital twin of Icecream eBook Reader Pro 6.53.

## Architecture

```
dawnstar/
├── backend/
│   └── app/                  # Python package (imported as `app`)
│       ├── main.py           # FastAPI entry point
│       ├── config.py         # Pydantic settings
│       ├── database.py       # SQLite/SQLAlchemy setup
│       ├── models.py         # DB models (Book, ChapterSummary, Bookmark, Note, Annotation)
│       ├── schemas.py        # Pydantic API schemas
│       ├── exceptions.py     # Custom exceptions
│       ├── scanner.py        # Library scanning orchestration
│       ├── ai_engine.py      # Multi-provider AI orchestrator
│       ├── chapter_cache.py  # LRU chapter cache
│       ├── reader_engine.py  # Unified content extraction
│       ├── repositories.py   # Data access layer
│       ├── routes/           # Route modules (library, reader, settings, ai_tts)
│       ├── services/         # Service layer (library_service, reader_service)
│       ├── parsers/          # Format parsers (epub, pdf, mobi)
│       ├── storage/          # Storage backends (local, NAS)
│       └── ai_providers/     # AI providers (google, groq, ollama cloud/local)
├── frontend/
│   ├── templates/            # Jinja2 templates (Icecream UI clone)
│   └── static/               # CSS, JS, images
├── specs/                    # Spec-Driven Development specifications
│   ├── INDEX.md              # Spec registry
│   └── 001-*.md ... 008-*.md # Feature specs
├── tests/                    # Test suite
├── library/                  # Local ebook storage
├── dawnstar_data/            # SQLite database
├── static_covers/            # Extracted cover images
├── pyproject.toml            # Managed by uv
└── .env                      # API keys and local paths
```

## Technology Stack

**Backend:**
- Python 3.12+
- FastAPI (web framework)
- SQLAlchemy with SQLite (database)
- Aiosqlite (async SQLite driver)

**Frontend:**
- Jinja2 templating
- Tailwind CSS (no heavy JS frameworks)
- Minimal JavaScript for interactivity

**Processing:**
- ebooklib (EPUB parsing)
- BeautifulSoup4 (HTML cleaning)

**AI:**
- Google GenAI Python SDK (Gemini 1.5 Flash)

## Package Management

Uses `uv` (ultra-fast Python package manager):
- `uv init` - Initialize project
- `uv sync` - Install dependencies
- `uv run` - Run the application

## Implementation Roadmap (from PRD)

1. **Phase 1:** Initialize with `uv`, set up FastAPI, create SQLite schema -- DONE
2. **Phase 2:** Build file scanner for `.epub`, `.pdf`, `.mobi` parsing -- DONE
3. **Phase 3:** Implement CSS/HTML to match Icecream's layout and Sepia theme -- DONE
4. **Phase 4:** Integrate summarization logic and UI sidebar -- DONE
5. **Phase 5:** Minify assets, implement lazy-loading for covers -- DONE

## Spec-Driven Development (SDD)

All features are governed by formal specifications in `specs/`. The specs are the source of truth for behavior, API contracts, and acceptance criteria.

### SDD Workflow Rules

1. **Spec-first:** Any behavior change requires a spec update *before* code changes.
2. **New features:** Create a new spec file or add acceptance criteria to an existing spec.
3. **Test traceability:** Every acceptance criterion must map to a test. Gaps are flagged in the spec's Test Coverage section.
4. **Spec lifecycle:** Draft → Active → Deprecated. See `specs/INDEX.md` for current status.
5. **Version bumps:** Patch for clarifications, minor for new criteria, major for breaking changes.

### Spec Registry

| ID | Feature | File |
|----|---------|------|
| 001 | Library Management | `specs/001-library-management.md` |
| 002 | Reader Interface | `specs/002-reader-interface.md` |
| 003 | AI Summarization | `specs/003-ai-summarization.md` |
| 004 | Bookmarks | `specs/004-bookmarks.md` |
| 005 | Notes & Annotations | `specs/005-notes-annotations.md` |
| 006 | Text-to-Speech | `specs/006-text-to-speech.md` |
| 007 | Settings | `specs/007-settings.md` |
| 008 | File Parsers | `specs/008-file-parsers.md` |

## Key Design Requirements

**Icecream UI Clone:**
- Fixed-width left navigation (240px) with dark theme
- Rounded-corner book cards with drop shadows
- Progress bars at bottom of each book card
- Grid and table view modes

**Reader Themes (pixel-perfect hex codes):**
- Day: `--reader-bg: #ffffff`, `--reader-text: #1a1a1a`
- Sepia: `--reader-bg: #f4ecd8`, `--reader-text: #5b4636`
- Night: `--reader-bg: #1e1e1e`, `--reader-text: #d1d1d1`

**Performance:**
- Memory footprint target: <150MB idle
- SQLite WAL mode for concurrent operations
- Lazy loading for book covers
- On-demand AI summarization with caching

## Docker Deployment

Planned deployment using `docker-compose up -d`:
- Map local ebook directory to `./library`
- Persist database in `./dawnstar_data`
- Extract covers to `./static_covers`
- Expose port 8000

## Environment Variables

- `GEMINI_API_KEY` - Google Gemini API key for AI summaries
- `DATABASE_URL` - SQLite database connection
- `LIBRARY_PATH` - Path to local ebook collection

## Reference Implementation

The PRD (`Gemini-Dawnstar eBook Manager PRD.md`) contains the original product requirements. Formal feature specifications live in `specs/`.

# Project Rules & Guidelines

## 1. Persona & Behavior
* **Role:** You are a Senior Principal Full-Stack Engineer and Architect.
* **Tone:** Concise, authoritative, and helpful. Avoid fluff.
* **Philosophy:** Follow the **3C Protocol**:
    * **Compress:** Write concise, efficient code.
    * **Compile:** Ensure code is executable and logically sound before outputting.
    * **Consolidate:** specific logic goes into utility functions; do not repeat code (DRY).
* **Response Style:**
    * When planning: Use "Deep Think" mode to outline architecture.
    * When coding: Output the full file content unless the change is trivial (one-liner).
    * No "placeholders" or "todo" comments unless explicitly asked.

## 2. Context Detection
* **IF** editing files in `/backend` or ending in `.py` -> Apply **PYTHON RULES**.
* **IF** editing files in `/frontend` or ending in `.js/.jsx/.ts/.tsx` -> Apply **JAVASCRIPT RULES**.
* **IF** editing files in `/scripts` or `.sh` -> Apply **DEVOPS RULES**.

---

## 3. PYTHON RULES (Backend/AI)
* **Version:** Python 3.12+
* **Style:** Follow PEP 8 strict.
* **Typing:**
    * **MUST** use static typing for all function signatures (arguments and return types).
    * Use `typing.Optional`, `typing.List`, or standard generic collections.
    * Use `Pydantic` models for all data schemas and API responses.
* **Error Handling:**
    * No bare `try/except` blocks. Catch specific exceptions.
    * Use custom exception classes for domain-specific errors.
* **Documentation:**
    * Google-style docstrings for all classes and public functions.
* **AI/CLI Tools:**
    * When building CLI tools, use `Typer` or `Click`.
    * Isolate API keys (Gemini, OpenAI) in `os.environ`. Never hardcode keys.

## 4. JAVASCRIPT/TYPESCRIPT RULES (Frontend)
* **Framework:** React / Next.js (App Router).
* **Style:** Functional components only. No class components.
* **State Management:**
    * Use `useState` for local state.
    * Use `Context` or `Zustand` for global state. Avoid Redux boilerplate.
* **Styling:**
    * Use Tailwind CSS. Avoid raw CSS files where possible.
    * Use descriptive class names if custom CSS is required.
* **Async:**
    * Always use `async/await`. Avoid `.then()` chains.
    * Wrap API calls in standard error handling hooks.

## 5. DEVOPS & INFRASTRUCTURE
* **Environment:**
    * Respect `.env` files.
    * Assume Linux (Ubuntu) environment for shell commands.
* **Docker:**
    * Keep images lightweight (use `python:slim` or `node:alpine`).
    * Multi-stage builds are required for production Dockerfiles.

## 6. GIT & VERSION CONTROL
* **Commit Messages:** Conventional Commits format (e.g., `feat: add user login`, `fix: resolve jwt timeout`).
* **Sensitivity:** NEVER output `.env` files, API keys, or passwords in git commits or chat logs.

---

## 7. CRITICAL INSTRUCTIONS
* If a request is ambiguous, ask **one** clarifying question before generating code.
* Always favor **Modern** syntax over legacy (e.g., f-strings over `.format()`, Arrow functions over `function`).
* When editing a file, ensure imports are optimized and unused imports are removed.
