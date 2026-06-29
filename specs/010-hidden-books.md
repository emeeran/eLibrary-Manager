# 010 — Hidden Books (Per-Book Passwords)

**Status:** Active
**Version:** 1.0.0
**Last Updated:** 2026-06-29
**Key Files:** `app/routes/hidden.py`, `app/models.py` (`Book.hidden_password`), `frontend/static/js/library.js`

## Overview

Each book can be hidden behind its own unique password. There is **no global
hidden-books password** (approach A). Hiding a book removes it from the default
library view; unhiding requires the password chosen when that book was hidden.

## Data Model

- `Book.is_hidden: bool` — whether the book is hidden.
- `Book.hidden_password: str | None` — a **one-way bcrypt hash** of the
  per-book password (`$2b$...`). Never the reversible password. Nullable.

## API Contract

### `POST /api/books/{book_id}/hide`
Set a new per-book password and mark the book hidden.
- Request: `{"password": "<1..72 chars>", "current_password": "<optional>"}`
- 200 `{is_hidden: true, message}` on success.
- 400 if `password` missing or > 72 chars (bcrypt truncates at 72 bytes).
- 401 if the book is already password-protected and `current_password` is wrong
  or absent (prevents silently overwriting a forgotten password).

### `POST /api/books/{book_id}/unhide`
Verify the book's own password and unhide it.
- Request: `{"password": "..."}`.
- 200 on success; clears `is_hidden` and `hidden_password`.
- 401 on wrong password.
- 400 if the book is not actually hidden.
- 429 after **5 failed attempts** for the same `(book_id, client)` — escape
  hatch is the bulk "unhide all" action or a service restart.

### `GET /hidden/status`
Returns `{password_set: <count>0, hidden_count: <int>}`. Drives sidebar nav
visibility (shown iff `hidden_count > 0`).

### `POST /hidden/unhide-all`
Admin-only bulk reset: clears `is_hidden` and `hidden_password` on every book
**and** deletes the legacy global `hidden_password` setting (migration). The
"remove existing password and unhide all" action.

## Security Requirements

1. **Acceptance: passwords are stored as bcrypt hashes, never reversible.**
   `Book.hidden_password` MUST start with `$2`. No Fernet ciphertext, no HMAC
   fallback for newly-hidden books.
2. **Acceptance: API responses never expose `hidden_password`.** `BookResponse`
   must not declare the field (Pydantic ignores it via `model_validate`).
3. **Acceptance: brute force is throttled.** Per-book lockout after 5 failed
   unhide attempts (429). Route-level rate limit on `/hide` and `/unhide`
   (suffix-matched so reads are unaffected).
4. **Acceptance: passwords > 72 chars are rejected** (bcrypt byte limit).
5. **Acceptance: cache invalidation.** Every hide/unhide/unhide-all call
   invokes `invalidate_book_list_cache()` so the grid reflects the change
   immediately.

## UI Behavior

- **Hiding:** the card action button opens the modal in "set new password" mode.
- **Unhiding:** the modal opens in "enter password" mode; the submit button
  label changes to "Unhide book".
- **Viewing the "Hidden" sidebar list needs no password** — only unhiding a
  specific book does.
- **Forgot-password recovery:** the unhide modal's "Remove all & unhide
  everything" link calls `/hidden/unhide-all` (confirmed).

## Test Coverage

- Backend: bcrypt storage, wrong/correct unhide, >72-char rejection, lockout,
  bulk unhide-all, cache invalidation (verified end-to-end against live server).
- Frontend: modal renders in both modes, hide/unhide flows, zero JS errors
  (headless Chrome).

## Gaps / Future

- Lockout state is in-memory (single-process). Adequate for a personal
  single-admin app; would need a shared store for multi-worker.
- No per-book password-strength policy beyond length 1–72.
