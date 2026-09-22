# Phase 3 — Style & Authorship Consistency (applied)

Per the request, Phases 2–5 ran straight through (no dry-run pause). This file
records what Phase 3 changed and what it deliberately left alone.

## Applied (behavior-preserving)

| change | scope | why |
|--------|-------|-----|
| `ruff format` on `backend/` + `tests/` | 21 files reformatted (49 already clean) | Project configures `[tool.ruff] line-length = 100`; `ruff check` is the enforced standard in CI. `black` is configured too but not installed; ruff format is black-compatible. `alembic/` deliberately excluded — its `Union[...]` migration style is intentional (per project notes). |
| `prettier --write` on `frontend/static/js/**/*.js` | 19 files reformatted | `package.json` defines `format: prettier --write`. Whitespace/quotes/semicolons only — no behavior or DOM/contract change (inline `onclick`/`window.*` untouched). |
| `stats.py` `Book.is_hidden == False` → `.is_(False)` (10×) | removed 10 `# noqa: E712` | Idiomatic SQLAlchemy; semantically identical for boolean filtering (`IS 0` vs `= 0`, same result set). Drops lint-suppression noise. |
| `settings.py` AI voice | `"Connection successful!"` → `"Connection successful"` | Only exclamation/emoji hit in user-facing text; matches the codebase's otherwise flat tone. |

Verification: `ruff check` clean, `npx eslint lib/` clean, 130 Python tests pass.

## Deliberately NOT done (conservative — would be churn or behavior-risk)

- **Class renames** (`DatabaseManager`, `NASHealthMonitor`, `LibraryScanner`, …): stripping `Manager`/`Monitor` suffixes is high-churn (ripples through every caller/import) for cosmetic gain on names that are already established and descriptive. Decision-fork rule → leave.
- **Global error-handling philosophy rewrite**: the broad `except Exception` sites (`nas_health`, `auth` epoch read, `security` verify, ~14 `noqa: BLE001`) are behavior-risky to narrow blind. → deferred to `AUDIT.md` (Phase 4), not a style change.
- **Comment-noise stripping (~20 spots)**: the codebase's convention *is* explanatory comments; bulk-deleting them is churn against the house style.
- **Test trimming**: the suite (130 tests, 46% coverage) has no obvious padding; removing tests risks lowering the gate. Left intact.
- **`tts.js`/`library.js` legacy lint debt** (~180 pre-existing `no-var`/`prefer-const` errors): pre-dates this pipeline; fixing blind in untested monoliths is out of Phase-3 scope. Noted for `AUDIT.md`; the files are slated for the frontend modernization (Phase 4/5 of that roadmap).

## Net

One formatting standard now applied across all Python and JS; the only
behavior-adjacent edits (SQLAlchemy bools, one string) are semantically
identical. Everything riskier is catalogued for the audit, not silently changed.
