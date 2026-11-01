# Phase 2 — Debloat & Refactor Plan (DRY RUN)

**Not yet applied.** Two parallel subagent scans (backend + frontend) plus
main-thread verification. Everything below was checked against the actual code;
subagent "SAFE" calls that didn't hold up were rejected (logged in "Rejected").

The codebase came into this pipeline already lean (it just exited a feature/cleanup
batch), so Phase 2 is small. Per the spec, anything behavior-risky is deferred to
`AUDIT.md` (Phase 4), not refactored here.

## SAFE to apply now (zero behavior change)

| # | location | change | why safe |
|---|----------|--------|----------|
| 1 | `backend/app/services/library_service.py:443-445` | Delete the 3 commented-out lines (`# cover_path = ...` / `# if cover_path:` / `# book_data.cover_path = cover_path`). Keep the prose comment above them, which fully documents the decision. | Dead old implementation. The 6-line prose comment above ("Covers are deferred… fast_index stays filename-only by intent") already captures the *why*; the commented code adds nothing and reads as leftover scratch. |

That is the only verified-safe removal.

## Rejected (subagent flagged, but verified NOT safe / NOT bloat)

- **`auth.py:255` `del token`** — deliberate unused-argument idiom; docstring already explains "unused but kept for API symmetry." Not bloat.
- **`settings.py:27` & `:40` `import asyncio`** — NOT redundant/dead. Two separate function-local imports in different `if` branches, both reachable (deferred to avoid circular imports). Subagent was wrong.
- **`theme.js:67-73` Ctrl+T handler** — NOT a duplicate. `library.js:2079` handles Ctrl+F/B/N, *not* Ctrl+T; theme.js holds the only theme-cycle shortcut. Removing it deletes a feature.
- **Duplicate `escapeHtml` (library.js / settings.js / reader/state.js)** — the three are **not identical** (reader's is DOM-based and doesn't escape `'`; lib/dom's is regex and does). Also `settings.html` doesn't load `lib/dom.js`. Consolidation is the staged Phase-4/5 migration, not a bloat fix. **RISKY → deferred.**
- **`from typing import Any` and `from __future__ import annotations`** — the "inline to `object`" / "remove no-op" suggestions change typing semantics and can affect Pydantic/FastAPI annotation evaluation. Not safe. Leave.
- **Comment noise (~20 spots)** — judged useful documentation; the codebase's convention *is* explanatory comments. Removing would be churn against the house style.

## Deferred to AUDIT.md (Phase 4) — RISKY, do not refactor in Phase 2

These look like bloat but narrowing/changing them could alter behavior; they get
file:line entries in the production-readiness audit instead:

- **Over-broad exception handlers** — `nas_health.py:68` (`except Exception` in the monitor loop), `auth.py:162` (epoch read swallows errors, serves stale cache), `security.py:87-98` (password-verify returns False on *any* error), and the ~14 `# noqa: BLE001` broad catches. Each needs a per-site decision; bulk-narrowing is exactly what the spec says to flag, not silently do.
- **`Book.is_hidden == False` (10× in `stats.py`)** — works today (with `# noqa: E712`); `.is_(False)` is stylistically preferred but changes generated SQL slightly. -> Phase 3 (style), not here.
- **Single-impl abstractions** (`BaseAIProvider`, `storage/factory.py`) — have ≥2 implementations and real runtime polymorphism (provider fallback, local/NAS). Not bloat; keep.

## Verdict

One 3-line dead-code removal. The rest of the codebase is already at the
senior-engineer floor Phase 2 aims for; the remaining "bloat-looking" code is
either intentional (defensive catches, fallbacks, API-symmetry params) or
behavior-risky to touch blind (→ AUDIT.md).
