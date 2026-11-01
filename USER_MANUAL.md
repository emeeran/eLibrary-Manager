# eLibrary Manager — User Manual

A self-hosted web application for managing and reading large ebook collections, with AI-powered chapter summarization, text-to-speech, Calibre/OPDS integration, and an Icecream eBook Reader–style interface.

---

## 1. Installation

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager
- For Docker deployment: Docker + Docker Compose

### Local install

```bash
git clone https://github.com/emeeran/eLibrary-Manager.git
cd eLibrary-Manager

# Install all dependencies into a managed virtualenv
uv sync

# Create your configuration
cp .env.example .env
```

Edit `.env`. The two settings that matter most:

```bash
# AI summaries: either of these (GEMINI_API_KEY wins if both are set)
GEMINI_API_KEY=your-google-ai-studio-key
# GOOGLE_API_KEY=your-google-ai-studio-key

# Login account
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-password
```

### Docker install

```bash
cp .env.example .env      # edit as above
docker-compose up -d
docker-compose logs -f elibrary
```

The app listens on **http://localhost:8000**. Ebooks are read from `./library`, the database lives in `./dawnstar_data`, and covers are extracted to `./static_covers`.

### First login

Open http://localhost:8000 and sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`. Sessions are HMAC-signed cookies; logging out or changing the password invalidates all previous sessions.

### Supported formats

EPUB, PDF, MOBI, CBZ, FB2, and Markdown (`.md`).

---

## 2. Running the app

| Command | What it does |
|---------|--------------|
| `make dev` | Development server with auto-reload, binds `0.0.0.0:8000` |
| `make run` | Alias for `make dev` |
| `./run-dev.sh` | Binds `127.0.0.1` and picks the first free port (or set `ELIBRARY_DEV_PORT`) |
| `./start.sh` | Loads `.env`, picks a free port from `APP_PORT`, opens the browser |
| `make test` | Test suite with HTML coverage report |
| `make lint` / `make format` | Ruff + MyPy / Black + Ruff |
| `make docker-up` / `make docker-down` / `make docker-logs` | Compose lifecycle |
| `make deb` / `make deb-install` | Build and install the Debian package (includes a systemd unit) |

---

## 3. Adding books

1. **Drop files into the library folder.** Copy ebooks into the directory configured by `LIBRARY_PATH` (default `./library`). The scanner indexes them and extracts covers into `COVERS_PATH`.
2. **Upload via the web UI.** Uploads are size-limited by `MAX_UPLOAD_SIZE_MB` (default 100 MB).
3. **Import a Calibre library.** From the app, start a Calibre import — it runs in the background and reports progress via live events; a sync monitor keeps the import up to date afterwards (see specs 011/013).
4. **Download from an OPDS catalog** (see §7).

---

## 4. Reading

Open any book card to enter the reader.

- **Themes:** Day (`#ffffff` background), Sepia (`#f4ecd8`), Night (`#1e1e1e`).
- **Progress:** Your position is saved automatically and restored on the next session.
- **Bookmarks, notes, highlights:** Create them while reading. Annotations can also be embedded back into the EPUB file itself.
- **Full-text search:** Search across book content (SQLite full-text search).
- **Auto-scroll:** Hands-free scrolling in the reader.
- **Open externally:** The `/open` route hands the file to your system's default viewer (spec 014), and Calibre-Web deep links jump from Calibre-Web straight into the eLibrary reader (spec 013).

### AI features (per chapter)

- **Summaries:** Generated on demand and cached in the database — regenerating is instant.
- **Transform:** Translate or define selected text.
- **Ask:** Grounded Q&A about the current book.

Providers are tried in priority order when `AI_DEFAULT_PROVIDER=auto`:

```
1. Google Gemini      (GOOGLE_API_KEY / GEMINI_API_KEY)
2. Ollama Cloud       (OLLAMA_CLOUD_URL, default https://api.ollama.ai)
3. Ollama Local       (OLLAMA_LOCAL_URL, default http://localhost:11434)
```

Fallback is automatic on failure when `AI_ENABLE_FALLBACK=true`; per-provider rate limits, timeouts (`AI_REQUEST_TIMEOUT`), and retries (`AI_MAX_RETRIES`) are configurable.

### Text-to-Speech

Two engines are available: **EdgeTTS** (neural voices) and **gTTS**. Select engine and voice from the reader's TTS controls.

---

## 5. Organizing the library

- **Grid and table views**, sorting, and filtering by title, author, format, favorites, recency, series, reading status, and category.
- **Categories:** Managed via the categories API/page; books can also be auto-categorized (hybrid rule-based + AI).
- **Series, reading status, word count:** Tracked per book.
- **Reading goals:** Set a daily goal (default 30 minutes) in settings; the dashboard shows goal progress and session stats.
- **Hidden books:** Hide any book behind its own password (stored as a bcrypt hash). Unlock is rate-limited and locks out after 5 failed attempts; an admin can bulk-reveal all hidden books.
- **Maintenance:** Backup/restore, book QA checks, and soft delete from the maintenance page.

---

## 6. OPDS network catalogs

Register an OPDS catalog (URL + optional credentials) and browse it from the app. Credentials are stored server-side and never exposed to the browser. Download entries directly into your library.

---

## 7. NAS storage

To keep the collection on a network share, **mount the share yourself** (SMB/NFS), then point the app at it:

```bash
NAS_ENABLED=true
NAS_MOUNT_PATH=/mnt/nas/books   # an existing mount point
NAS_CACHE_DIR=./nas_cache       # offline read cache
```

The app validates the mount, probes its health (5s timeout by default), and caches files for offline access. It does not mount the share for you.

---

## 8. Configuration reference

All settings are environment variables (or `.env` entries). See the table in [README.md](README.md#configuration) for the complete, current list. Security-critical notes:

- **`SECRET_KEY` is required in production** (`APP_ENV=production`); it signs session cookies and encrypts settings secrets.
- Prefer `ADMIN_PASSWORD_HASH` (bcrypt) over plaintext `ADMIN_PASSWORD`.
- `GEMINI_API_KEY` takes priority over `GOOGLE_API_KEY`.

---

## 9. Troubleshooting / FAQ

**The page asks for a login I never set.**
Authentication is always on. Set `ADMIN_USERNAME` / `ADMIN_PASSWORD` in `.env` and restart.

**AI summaries fail or are slow.**
Check that `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is set, or configure a local Ollama at `OLLAMA_LOCAL_URL`. Watch the log level (`LOG_LEVEL=DEBUG`) for provider fallback messages. Without any working provider, only Ollama-local-dependent features stop; reading itself is unaffected.

**A book is missing from the library.**
Make sure the file is inside `LIBRARY_PATH` and in a supported format (EPUB/PDF/MOBI/CBZ/FB2/MD), then rescan. Check that the NAS mount is healthy if `NAS_ENABLED=true`.

**`docker-compose logs -f dawnstar` fails.**
The compose service is named `elibrary` — use `docker-compose logs -f elibrary`.

**App won't start / port already in use.**
Use `./run-dev.sh` (auto port pick) or change `APP_PORT`.

**I locked myself out of a hidden book.**
Unlock attempts lock out after 5 failures; an admin can reveal all hidden books via the admin bulk action.

**Database schema errors after upgrading.**
Run the migrations: `uv run alembic upgrade head`.

---

## 10. Where things live

| Path | Purpose |
|------|---------|
| `library/` | Your ebooks (`LIBRARY_PATH`) |
| `dawnstar_data/` | SQLite database + WAL |
| `static_covers/` | Extracted cover images |
| `static_book_images/` | Extracted book images |
| `specs/` | Formal feature specifications (source of truth for behavior) |
| `docs/` | API reference, architecture, deployment docs |
