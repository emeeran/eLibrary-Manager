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

## ⚑ Missed by pipeline, caught by blind review (Phase 5)

A context-blind review (`/.pipeline/blind-review.md`) caught two **P0 bugs in
untested paths** that Phases 1–4 missed entirely. Both confirmed against the code:

- [x] **P0 — FIXED (`b671d20`) — `backend/app/auth.py:181-185` `_bump_epoch` never commits.** It opens the session via the raw `db_manager.session_factory()` inside `async with`; `AsyncSession.__aexit__` only `close()`s (no commit — only `get_session()` commits). So the epoch bump is rolled back and **logout / password-change revocation does not persist** — an old session cookie resurfaces as valid once the in-memory epoch cache refreshes from the un-updated DB (within the `_EPOCH_CACHE_TTL`), and stays valid until its 24h absolute expiry. The tests miss it because `test_security_session.py` stubs `_bump_epoch`. *Fix:* `await db.commit()` (or use `get_session()`).
- [x] **P0 — FIXED (`cb33981`) — `backend/app/routes/settings.py:219` missing `await`.** `orchestrator = get_ai_orchestrator()` calls an `async def` without awaiting, so `POST /api/settings/test-ai` raises `AttributeError` every call — the "Test AI connection" button is dead. *Fix:* `await get_ai_orchestrator()`.

Other real items the blind review surfaced that Phases 1–4 under-weighted:

- [x] **P1 — FIXED (2026-09-20, branch `fix/hardening-batches-abc`) — all 8 `fitz.open()` sites now context-managed.** On a mid-render exception (corrupt PDF) the doc handle leaks until GC — a slow FD leak on a long-running reader. (Phase 4's ops scan incorrectly marked handle cleanup PASS.) *Fix:* `with fitz.open(...) as doc:`.
- [x] **P1 — FIXED (2026-09-20) — each directory's `os.scandir` walk now runs in `asyncio.to_thread`** (only `asyncio.sleep` between batches, not `to_thread`). On a large/slow mount this freezes every concurrent request. *Fix:* move `scandir` into `asyncio.to_thread` (the NAS backend already shows the pattern).
- [x] **P2 — FIXED — `repositories.py` filters `is_deleted` in the search predicate + UPDATE trigger (`books_fts_au`) added.** The `books_fts` triggers handle INSERT/DELETE only; soft-delete (`is_deleted=True`) is an UPDATE, so soft-deleted books still surface in title/author search even though the list query filters them. (The content-FTS hard-delete cleanup from `f4265b7` didn't cover this metadata-FTS/soft-delete path.) *Fix:* filter `is_deleted` in the FTS predicate or add an UPDATE trigger.

Smaller blind-review catches (style/dead-code, low severity):
`repositories.py:182,195` uses `__import__("sqlalchemy").text(...)` (obfuscation — `text` is already imported); `ai_engine.py:22` docstring still names a "Groq" provider that isn't instantiated; `google_provider.py:24` class-default `model="gemini-1.5-flash"` conflicts with the config default `gemini-2.5-flash` (overwritten in `__init__`, cosmetic); four near-duplicate background-task runners in `library.py`/`calibre.py`/`maintenance.py` (~150 lines that could be one helper — a Phase-2 debloat miss).

**Agreements (higher confidence):** the blind review independently corroborated
the upload-size-limit and NAS/parser-coverage findings, and validated that
Phases 2–3 did *not* regress the praised controls (nh3 sanitization, keyset
pagination, single-flight summary, AI retry/backoff, SQLite pragmas, NAS
threadpool I/O). See `.pipeline/blind-review.md` for the full verbatim review.

## High priority

- [x] **FIXED (2026-09-20) — `_clamped_matrix()` caps renders at `MAX_RENDER_PX=2048`** (`pdf_parser.py` cover + page render). Under `MemoryMax=1G` a large/complex PDF can OOM-kill the service. Content extraction was already memory-bounded (`content_extractor.py` 2M-char cap); cover/page rendering was not. *Fix:* cap pixmap dimensions / DPI before `get_pixmap`, skip oversize.
- [x] **FIXED (2026-09-20) — bounded write with `max_upload_size_mb` (default 100MB, HTTP 413) + magic-byte sniff (`_upload_signature_matches`, HTTP 415).** A crafted file or a huge upload can fill disk or smuggle a non-book payload. Single-admin lowers but doesn't remove the risk. *Fix:* enforce a max size (e.g. 100 MB) and verify EPUB-zip / `%PDF` magic bytes.
- [x] **FIXED (2026-09-20) — `/api/health` probes DB (`SELECT 1`) + NAS backend when configured; 503 `degraded` on failure. AI deliberately not probed (would flap on transient API issues).** The systemd unit uses `Restart=on-failure` (not a watchdog), so a running-but-degraded process (e.g. DB file gone) is never detected or recovered. *Fix:* probe DB (`SELECT 1`), and when configured, NAS + AI provider health; return 503 on failure.
- [x] **FIXED (2026-09-20) — `tests/test_nas.py` (cache 89%), `tests/test_nas_health.py` (97%), `tests/test_calibre_sync_monitor.py` (95%); parser tests added earlier. Suite 50% vs 45% gate.** parsers (`pdf_parser` ~15%, `epub_parser` ~19%, `mobi_parser` ~18%). These are exactly the modules most likely to break on real-world input. CI gate is 45% (actual 46%). *Fix:* targeted tests for NAS cache eviction/health, parser metadata + corrupt-input (parser tests were added this pass; NAS remains the gap).

## Medium / Low

- [ ] **`.env.example` drift** — documents `GROQ_*` vars (provider never implemented; orchestrator is Google→Ollama), `OLLAMA_LOCAL_MODEL=llama3.3` vs the code default `llama3.2:3b`, and omits `NAS_*`, `ai_request_timeout`/`ai_max_retries`, `DB_MMAP_SIZE`, `ELIBRARY_PORT`. *Fix:* regenerate from `AppConfig` fields.
- [ ] **Dependency pinning (`pyproject.toml`)** — all deps use `>=`. `uv.lock` gives reproducible syncs, but majors can drift on a fresh `uv sync`. *Fix:* consider `~=` on the fragile ones (fastapi, sqlalchemy, pydantic, pymupdf, google-genai).
- [ ] **`backend/app/security.py:87-98`** — `verify_password` returns `False` on **any** exception (masks unexpected errors as "wrong password"); a Fernet-migration path is swallowed with `pass`. *Fix:* catch `bcrypt`/`ValueError`/`UnicodeEncodeError` specifically; log the rest.
- [ ] **`backend/app/routes/hidden.py` lockout** — `_failed_attempts` is **in-memory**, reset on restart. *Fix:* persist attempt counts (settings table) for the hidden-book brute-force lockout to survive restarts.
- [ ] **`backend/app/auth.py` epoch read (~147-164)** — on DB read failure it logs and **serves the cached epoch** (fail-open). Intentional, but a stale cache could honor/invalidated tokens incorrectly; worth a short staleness TTL comment or bounded fallback.
- [ ] **No DB backup mechanism** — no backup endpoint/script for the 11k-book SQLite DB. *Fix:* add a maintenance route using `VACUUM INTO` or the SQLite backup API (the user currently backs up externally).
- [ ] **`backend/app/security.py:16,48`** — `_signing_secret` falls back to `database_url` when `SECRET_KEY` is unset. Production enforces `SECRET_KEY` (config raises), so this is **dev-only**, but a dev box then derives keys from a predictable value. *Fix:* generate and persist a random key on first run instead.
- [x] **FIXED (2026-09-20) — mypy added to the lint job as a non-gating (`continue-on-error`) step** — baseline is ~156 pre-existing errors; flip to gating once paid down. *Fix:* add `uv run mypy backend/` to the lint job.
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
