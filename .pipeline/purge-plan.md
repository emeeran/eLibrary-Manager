# Phase 1 — Redundant File Purge Plan (DRY RUN)

**Not yet applied.** Review this list; say `--apply` to execute (each item is
`git mv`'d into `.pipeline/purge/<mirrored-path>`, never deleted).

## Candidates to move

| # | path | reason | confidence | inbound refs found |
|---|------|--------|------------|--------------------|
| 1 | `final_report.md` | Stale AI code-review synthesis report dated **2026-05-02** (624 lines). Its headline findings — "no database migration framework", "blocking I/O on the event loop", "in-memory session store", "secrets derived from DB URL" — are all **outdated**: the project now has Alembic migrations, async AI providers, stateless HMAC sessions, and `SECRET_KEY` validation. Not referenced by any code, config, doc, or README. | HIGH | none (only `.pipeline/inventory.csv`, a self-listing) |

**Restore after move:** `git mv .pipeline/purge/final_report.md final_report.md`

## Reviewed and found CLEAN (no action)

- **Tracked build/cache artifacts** — none (`__pycache__`, `*.pyc`, `node_modules`, `dist/`, `*.min.js` are all gitignored; nothing leaked into git).
- **Exact-content duplicates** (md5 across all tracked source) — none.
- **Superseded generations** (`_old`, `_v2`, `_backup`, `_new`, `*~`, `*.bak`, `(copy)`, `old/`, `temp/`) — none.
- **Orphaned Python modules** (`backend/app/**`) — none. Every `routes/*.py` is registered in `main.py`; every `services/`, `parsers/`, `storage/`, `ai_providers/` module is imported somewhere. (Verified by exhaustive import cross-reference.)
- **Orphaned JS modules** (`frontend/static/js/**`) — none. Every `.js` file is loaded by a `<script src>` in `library.html` / `reader.html` / `settings.html`.
- **Near-duplicate / redundant-abstraction pairs** — none. Suspect pairs checked and confirmed distinct (`security.py` vs `security_middleware.py`; `middleware.py` vs `security_middleware.py`; `edgetts_service.py` vs `gtts_service.py`; `content_extractor.py` vs `content_backfill_service.py`; `calibre_sync_service.py` vs `calibre_sync_monitor.py`).

## Noted but NOT moved (out of scope for a purge)

- `.claude/settings.local.json` is tracked but is a *local* Claude-Code settings file (the `.local.` convention implies user-specific). It's not dead code — moving it would disrupt the user's tooling. Flagged for the style/convention phase (belongs in `.gitignore`, not deleted).
- `Gemini-Dawnstar eBook Manager PRD.md` is referenced by `CLAUDE.md` but is **not tracked** (it lives in the gitignored root `trash2review/` reference dump). Dangling doc reference — a docs fix, not a purge.

## Verdict

The tree is already clean at the file level. Only the one stale report qualifies.
