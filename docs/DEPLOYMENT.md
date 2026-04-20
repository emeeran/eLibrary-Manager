# Deployment Guide

## Table of Contents

- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Environment Variables](#environment-variables)
- [NAS Storage Setup](#nas-storage-setup)
- [AI Provider Configuration](#ai-provider-configuration)
- [Production Hardening](#production-hardening)
- [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

- **Python 3.12+** — `python3 --version`
- **uv** — Install from [docs.astral.sh/uv](https://docs.astral.sh/uv/)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd eLibrary-Manager

# Install all dependencies (including dev tools)
uv sync

# Set up pre-commit hooks
make install

# Create environment file
cp .env.example .env
```

### Running

```bash
# Development server with auto-reload
make dev

# Or manually:
PYTHONPATH=backend uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit **http://localhost:8000**

### Development Commands

```bash
make dev          # Start dev server
make test         # Run tests with coverage
make lint         # Run ruff + mypy
make format       # Format with black + ruff --fix
make check        # Run lint + test together
make clean        # Remove __pycache__, .pyc, coverage artifacts
```

---

## Docker Deployment

### Dockerfile

The application uses a multi-stage build for minimal image size:

- **Stage 1 (Builder):** `python:3.12-slim` + uv — installs dependencies
- **Stage 2 (Runtime):** `python:3.12-slim` — copies venv and app code only

The runtime image runs as a non-root user (`dawnstar`, UID 1000) with a health check endpoint.

### Quick Start

```bash
# Configure environment
cp .env.example .env
# Edit .env with your API keys and paths

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f dawnstar

# Stop
docker-compose down
```

### Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./library` | `/app/library` | Ebook files |
| `./dawnstar_data` | `/app/dawnstar_data` | SQLite database |
| `./static_covers` | `/app/static_covers` | Extracted cover images |
| `./static_book_images` | `/app/static_book_images` | Extracted book images |

### Port

Default: **8000**. Configure via `APP_PORT` in `.env` or `docker-compose.yml`.

---

## Environment Variables

All configuration is managed through environment variables, loaded from `.env` via `python-dotenv`.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dawnstar_data/dawnstar.db` | SQLite async connection string |
| `DB_POOL_SIZE` | `10` | Connection pool size |
| `DB_MAX_OVERFLOW` | `20` | Max overflow connections |

### Library Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `LIBRARY_PATH` | `./library` | Directory containing ebook files |
| `COVERS_PATH` | `./static_covers` | Directory for extracted cover images |

### AI Providers

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | Google Gemini API key |
| `GOOGLE_MODEL` | `gemini-1.5-flash` | Gemini model name |
| `GOOGLE_RATE_LIMIT_RPM` | `15` | Rate limit (requests/minute) |
| `GROQ_API_KEY` | — | Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `GROQ_RATE_LIMIT_RPM` | `30` | Rate limit (requests/minute) |
| `OLLAMA_CLOUD_URL` | `https://api.ollama.ai` | Ollama Cloud endpoint |
| `OLLAMA_CLOUD_MODEL` | `llama3.3` | Ollama Cloud model |
| `OLLAMA_LOCAL_URL` | `http://localhost:11434` | Local Ollama endpoint |
| `OLLAMA_LOCAL_MODEL` | `llama3.3` | Local Ollama model |
| `AI_DEFAULT_PROVIDER` | `auto` | Provider: `auto`, `google`, `groq`, `ollama_cloud`, `ollama_local` |
| `AI_ENABLE_FALLBACK` | `true` | Enable automatic fallback chain |

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `0.0.0.0` | Server bind address |
| `APP_PORT` | `8000` | Server port |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### Performance

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_COVER_SIZE` | `300000` | Maximum cover image size in bytes |
| `LAZY_LOAD_BATCH_SIZE` | `20` | Number of covers to lazy-load per batch |

---

## NAS Storage Setup

The application can read ebooks from a NAS share via SMB/CIFS or NFS mount.

### SMB/CIFS Mount (Linux)

```bash
# Install cifs-utils
sudo apt install cifs-utils

# Create mount point
sudo mkdir -p /mnt/ebooks

# Mount (add to /etc/fstab for persistence)
sudo mount -t cifs //nas-server/books /mnt/ebooks \
  -o username=user,password=pass,uid=1000,gid=1000,iocharset=utf8
```

### Configure Application

Set `LIBRARY_PATH` to the mount point:

```bash
LIBRARY_PATH=/mnt/ebooks
```

### NAS Health Monitoring

When NAS storage is configured, the application runs a background health monitor that:
- Checks mount availability on a configurable interval
- Updates NAS health status accessible via `GET /api/settings/nas-health`
- Triggers alerts when the NAS becomes unavailable

### Offline Caching

The NAS file cache (`nas_cache.py`) provides offline reading capability:
- Accessed files are cached locally on disk
- LRU eviction when cache exceeds size limit
- Automatic cache refresh on NAS reconnection

---

## AI Provider Configuration

### Google Gemini (Recommended)

1. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Set in `.env`:

```bash
GOOGLE_API_KEY=AIzaSy...
GOOGLE_MODEL=gemini-1.5-flash
```

### Groq

1. Get an API key from [console.groq.com](https://console.groq.com)
2. Set in `.env`:

```bash
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

### Ollama Local (Offline)

1. Install Ollama from [ollama.com](https://ollama.com)
2. Pull a model:

```bash
ollama pull llama3.3
```

3. Set in `.env`:

```bash
OLLAMA_LOCAL_URL=http://localhost:11434
OLLAMA_LOCAL_MODEL=llama3.3
```

### Fallback Chain

When `AI_DEFAULT_PROVIDER=auto` and `AI_ENABLE_FALLBACK=true`:

```
Google Gemini ──► Groq ──► Ollama Cloud ──► Ollama Local
    (fail)          (fail)      (fail)         (last resort)
```

Each provider is tried in priority order. Rate limits are enforced independently per provider.

---

## Production Hardening

### Security Checklist

- [ ] Set `DEBUG=false` in production
- [ ] Use `LOG_LEVEL=WARNING` or `LOG_LEVEL=INFO`
- [ ] Set a strong hidden-library password via the Settings UI
- [ ] Restrict `APP_HOST` if behind a reverse proxy
- [ ] Enable HTTPS via reverse proxy (Nginx, Caddy, Traefik)
- [ ] Back up `dawnstar_data/` directory regularly
- [ ] Do not expose `.env` file — ensure it's in `.gitignore`

### Reverse Proxy Example (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name ebooks.example.com;

    ssl_certificate /etc/ssl/certs/ebooks.crt;
    ssl_certificate_key /etc/ssl/private/ebooks.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE support for scan progress
    location /api/library/scan-progress/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
    }
}
```

### Database Backup

```bash
# SQLite backup (safe while app is running thanks to WAL mode)
sqlite3 dawnstar_data/dawnstar.db ".backup 'dawnstar_data/backup.db'"
```

---

## Troubleshooting

### Application won't start

```bash
# Check if port is in use
lsof -i :8000

# Check Python version
python3 --version  # Must be 3.12+

# Verify dependencies
uv sync
```

### No books appear after scan

1. Verify `LIBRARY_PATH` points to a directory with ebook files
2. Check file permissions (read access for the application user)
3. Check logs: `make docker-logs` or check console output

### AI summaries not working

1. Verify at least one API key is set in `.env`
2. Test connection via Settings UI or `POST /api/settings/test-ai`
3. Check rate limits if using free tiers
4. For Ollama Local: ensure Ollama is running (`ollama serve`)

### NAS connection issues

1. Verify mount: `mount | grep /mnt/ebooks`
2. Check NAS health: `GET /api/settings/nas-health`
3. Test connection: `POST /api/settings/test-nas`
4. Check SMB credentials in mount configuration

### Performance issues

1. Check memory usage — target is < 150 MB idle
2. Reduce `LAZY_LOAD_BATCH_SIZE` if cover loading is slow
3. Ensure SQLite WAL mode is active (check `dawnstar_data/` for WAL files)
4. Clear chapter cache by restarting the application (in-memory only)
