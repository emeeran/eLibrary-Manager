# Production Readiness Audit — 2026-08-05

Single-admin ebook manager (FastAPI + async SQLAlchemy/SQLite, ~11k books on a
CIFS/NAS mount, deployed as a `.deb` systemd service under `MemoryMax=1G`).
Findings are synthesized from six parallel dimension scans and **reconciled
against the actual code** — inflated subagent severities corrected, false
positives moved to "Verified not issues."

## Summary

**Verdict: production-ready with mandatory hardening.** The app is already
running at scale and the core paths (auth, reader, search, Calibre sync) are
solid and tested. It is *not* a greenfield deployment gate — it's an assessment
of what to fix for robust operation. The real risks cluster in four places:
**(1) unbounded PDF rendering under the 1G cap, (2) upload validation,
(3) a too-shallow health check, (4) test coverage on NAS/parsers.** None of the
subagent-flagged "BLOCKERs" survived verification (see the last section).

## High priority

- [ ] **`backend/app/parsers/pdf_parser.py` (~146-158 cover extraction, ~773-814 page render)** — pixmap rendering at 2×/150 DPI with **no size cap**. Under `MemoryMax=1G` a large/complex PDF can OOM-kill the service. Content extraction was already memory-bounded (`content_extractor.py` 2M-char cap); cover/page rendering was not. *Fix:* cap pixmap dimensions / DPI before `get_pixmap`, skip oversize.
- [ ] **`backend/app/routes/library.py` upload (`upload_book`, ~537-591)** — **no max upload size** and **extension-only validation** (no magic-byte check). A crafted file or a huge upload can fill disk or smuggle a non-book payload. Single-admin lowers but doesn't remove the risk. *Fix:* enforce a max size (e.g. 100 MB) and verify EPUB-zip / `%PDF` magic bytes.
- [ ] **`backend/app/main.py:270-273` `/api/health`** — returns a static `{"status":"ok"}` with **no DB/NAS/AI check**. The systemd unit uses `Restart=on-failure` (not a watchdog), so a running-but-degraded process (e.g. DB file gone) is never detected or recovered. *Fix:* probe DB (`SELECT 1`), and when configured, NAS + AI provider health; return 503 on failure.
- [ ] **Test coverage on critical untested paths** — `nas_cache.py` (0%), `nas_health.py` (0%), `services/calibre_sync_monitor.py` (0%), parsers (`pdf_parser` ~15%, `epub_parser` ~19%, `mobi_parser` ~18%). These are exactly the modules most likely to break on real-world input. CI gate is 45% (actual 46%). *Fix:* targeted tests for NAS cache eviction/health, parser metadata + corrupt-input (parser tests were added this pass; NAS remains the gap).

## Medium / Low

- [ ] **`.env.example` drift** — documents `GROQ_*` vars (provider never implemented; orchestrator is Google→Ollama), `OLLAMA_LOCAL_MODEL=llama3.3` vs the code default `llama3.2:3b`, and omits `NAS_*`, `ai_request_timeout`/`ai_max_retries`, `DB_MMAP_SIZE`, `ELIBRARY_PORT`. *Fix:* regenerate from `AppConfig` fields.
- [ ] **Dependency pinning (`pyproject.toml`)** — all deps use `>=`. `uv.lock` gives reproducible syncs, but majors can drift on a fresh `uv sync`. *Fix:* consider `~=` on the fragile ones (fastapi, sqlalchemy, pydantic, pymupdf, google-genai).
- [ ] **`backend/app/security.py:87-98`** — `verify_password` returns `False` on **any** exception (masks unexpected errors as "wrong password"); a Fernet-migration path is swallowed with `pass`. *Fix:* catch `bcrypt`/`ValueError`/`UnicodeEncodeError` specifically; log the rest.
- [ ] **`backend/app/routes/hidden.py` lockout** — `_failed_attempts` is **in-memory**, reset on restart. *Fix:* persist attempt counts (settings table) for the hidden-book brute-force lockout to survive restarts.
- [ ] **`backend/app/auth.py` epoch read (~147-164)** — on DB read failure it logs and **serves the cached epoch** (fail-open). Intentional, but a stale cache could honor/invalidated tokens incorrectly; worth a short staleness TTL comment or bounded fallback.
- [ ] **No DB backup mechanism** — no backup endpoint/script for the 11k-book SQLite DB. *Fix:* add a maintenance route using `VACUUM INTO` or the SQLite backup API (the user currently backs up externally).
- [ ] **`backend/app/security.py:16,48`** — `_signing_secret` falls back to `database_url` when `SECRET_KEY` is unset. Production enforces `SECRET_KEY` (config raises), so this is **dev-only**, but a dev box then derives keys from a predictable value. *Fix:* generate and persist a random key on first run instead.
- [ ] **CI (` .github/workflows/ci.yml`)** — runs ruff + tests + docker + secret-scan, but **no `mypy`** despite it being configured (dev deps + pre-commit). *Fix:* add `uv run mypy backend/` to the lint job.
- [ ] **No migration tests** — tests build schema via `Base.metadata.create_all`, never exercising Alembic up/down. Migrations do run on the live deploy, but a regression there is uncaught. *Fix:* one test that upgrades a fresh DB to head and stamps.
- [ ] **No frontend tests** — Vitest is on the modernization roadmap but absent. *Fix:* add unit tests for `lib/` (pure helpers) as the first slice.

## Verified NOT issues (false positives — checked and rejected)

Recorded so the next reviewer doesn't re-chase them:

- **"Single-flight race condition" (`reader_service.py`)** — asyncio is cooperative; the read→`create_task`→store segment has no `await` between, so it is atomic. Covered by `test_chapter_summary_single_flight`.
- **"No SIGTERM / graceful-shutdown handling"** — uvicorn installs SIGTERM/SIGINT handlers and runs the lifespan shutdown (monitors stopped, engine disposed) by default. `run-server.sh` could tune `--timeout-keep-alive`, but there is no missing signal handler.
- **"`get_db` doesn't roll back on exception / background-scan partial writes"** — `DatabaseManager.get_session` (`database.py:104-112`) rolls back on `DawnstarError` and generic `Exception`.
- **"`SECRET_KEY` not validated in production"** — `AppConfig.validate_secret_key` raises in `APP_ENV=production`.
- **Config defaults flagged as blockers** (`ollama_local_url=http://localhost:11434`, `app_host=0.0.0.0`) — sensible, env-overridable defaults; not hardcoded runtime values.
- **"ILIKE SQL injection"** — parameterized; user `%`/`_` only widen match semantics (a UX nuance, not injection).
- **"CSP `unsafe-inline`"** — required by the inline-`onclick` handler contract (documented in `docs/frontend-modernization.md`); removing it is phase 6 of the frontend roadmap, not a standalone vuln.
- **"Sensitive password logging" (`auth.py:95`)** — logs the *event* ("password hashed"), never the password.
- **"WAL grows unbounded"** — SQLite auto-checkpoints (`wal_autocheckpoint=1000` pages) by default.
- **Google/Ollama HTTP client "leaked on shutdown"** — Google uses the SDK-managed client; Ollama's one shared `httpx.AsyncClient` is reclaimed on process exit. A `await orchestrator.close()` in lifespan is nice-to-have, not a leak bug.

## Explicitly out of scope / accepted risk

- **IDOR on bookmark/note/annotation deletion** — single-admin deployment; there is no second user to abuse it. Revisit if multi-user lands.
- **CSRF DNS-rebinding / SameSite=Lax edge cases** — theoretical for a LAN single-admin app behind the Origin check; not worth the friction of `SameSite=Strict`.
- **No Prometheus metrics / request-ID tracing** — deliberate for a single-admin personal app; logging + slow-request warning suffice. Revisit if load/multi-tenant.
- **`tts.js` / `library.js` legacy lint debt (~180 `no-var`/`prefer-const`)** — pre-existing, in monoliths slated for the frontend modernization rewrite; not fixed in this pass.
