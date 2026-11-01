# 013 — Calibre-Web → eLM Reader Deep Link (reverse direction)

**Status:** Active  
**Version:** 1.0.0  
**Last Updated:** 2026-06-30  
**Depends on:** `011-calibre-integration.md` (uses `Book.calibre_id` / `Book.calibre_uuid`)  
**Key Files:** `app/routes/calibre.py` (`web_router` → `GET /calibre/launch`), `app/main.py` (router registration)

## Overview

Spec 011 deep-links the **eLM → Calibre-Web** direction ("Open in Calibre-Web"
on a book). This spec covers the **reverse** direction the user requires: when
they click **"Read in web browser"** inside a Calibre-Web instance, the book
opens directly in **eLM's reader** (`/reader/{book_id}`) instead of Calibre-Web's
own reader tab.

Calibre-Web has **no native setting** to redirect its reader to an external app.
The chosen integration is a **reverse-proxy URL rewrite** (no Calibre-Web fork):

```
Calibre-Web "Read"  →  GET /books/<calibre_id>/read
        │ reverse proxy rewrites this path to:
        ▼
eLM  GET /calibre/launch?calibre_id=<calibre_id>  →  302 /reader/<elm_book_id>
```

Both apps live behind **one reverse proxy on one domain** (eLM at root,
Calibre-Web under `/books/*`). Because eLM's session cookie is host-only and
`SameSite=Lax`, the browser sends it on this same-site top-level GET redirect,
so the user is already authenticated. A GET redirect is exempt from CSRF
(`CSRFMiddleware` only guards mutating methods).

## Acceptance Criteria

### Launch endpoint

- **AC-1:** `GET /calibre/launch?calibre_id=<int>` resolves the eLM `Book` whose
  `calibre_id` matches (indexed lookup) and responds **302** to
  `/reader/{book.id}`.
- **AC-2:** `GET /calibre/launch?calibre_uuid=<str>` is accepted as an alternate
  key (used when only the Calibre UUID is known).
- **AC-3:** When neither `calibre_id` nor `calibre_uuid` is supplied, the
  endpoint responds **302** to `/library` (never 400/500 — this is a browser
  navigation from a user click).
- **AC-4:** When the supplied Calibre id/uuid is **not yet imported** into eLM,
  the endpoint responds **302** to `/library?calibre_pending=<id>` (a dead-end
  404 is unacceptable on a user click). The library page surfaces a "run a
  Calibre import" prompt when that query param is present.
- **AC-5:** When the resolved book `is_hidden`, the endpoint responds **302** to
  `/library?calibre_hidden=1` — a deep link must **not** bypass the hidden-book
  password gate (spec 010).
- **AC-6:** The endpoint is **not** under the `/api/` prefix (so an
  unauthenticated request is redirected to `/login` by `AuthMiddleware`, not
  returned as a 401 JSON — the correct UX for a browser navigation). It is
  therefore not a public path; it is protected by the normal session check.

### Reverse-proxy contract

- **AC-7:** The supported Calibre-Web reader entrypoints are rewritten by the
  proxy to the launch endpoint. Both `/books/<id>/read` and
  `/books/<id>/read/<format>` map to `/calibre/launch?calibre_id=<id>`.
- **AC-8:** All other Calibre-Web paths (catalog, metadata editor, OPDS, book
  downloads) pass through to Calibre-Web **unchanged**.
- **AC-9:** Reference proxy configurations (Caddy **and** nginx) are documented
  in `docs/calibre-reader-deeplink.md`.

### Frontend

- **AC-10:** The library page reads `?calibre_pending=<id>` and surfaces a
  dismissible notice that the Calibre book has not been imported yet, with a link
  to Settings → Calibre to run an import.
- **AC-11:** The library page reads `?calibre_hidden=1` and surfaces a notice
  that the requested book is hidden in eLM.

## Data Model

No schema change. Reuses `Book.calibre_id` (indexed) and `Book.calibre_uuid`
added by migration `d1e2f3a4b5c6_add_calibre_columns` (spec 011).

## Security

- The endpoint resolves a book by Calibre id; it must not leak existence of
  hidden books (AC-5 redirects away without revealing the title).
- Authentication is enforced by `AuthMiddleware` (page route → `/login` when
  unauthenticated). Behind the shared-domain proxy the session cookie travels
  with the redirect; in a separate-domain deployment, see the deferred
  "separate-domain HMAC token" option below.
- No CSRF concern: the launch is a `GET` redirect (CSRF only guards
  POST/PUT/PATCH/DELETE).

## Test Coverage

`tests/test_calibre.py` — additions:

| Test | AC |
|------|----|
| `test_launch_resolves_to_reader` | AC-1 |
| `test_launch_by_uuid` | AC-2 |
| `test_launch_no_params_redirects_to_library` | AC-3 |
| `test_launch_unknown_id_redirects_to_pending` | AC-4 |
| `test_launch_hidden_book_redirects_to_library` | AC-5 |

(Auth-gating — AC-6 — is provided by `AuthMiddleware` and is bypassed under
`APP_ENV=testing`; it is asserted by confirming the route is outside `/api/` and
not in `PUBLIC_PATHS`.)

## Open Items / Future Work

- **Separate-domain HMAC token** — only needed if Calibre-Web and eLM cannot
  share one domain. eLM would issue a signed `?t=<sig>&exp=<ts>` over the
  Calibre id (using the existing `SECRET_KEY`) that `/calibre/launch` honors.
- **Hidden-book deep-link UX** — currently redirects to the library with a
  notice; a future iteration could surface the spec-010 unhide prompt directly.
- **Per-format routing** — the proxy currently rewrites both `/read/<id>` and
  `/read/<id>/<fmt>` the same way (eLM auto-detects format). If a format not
  supported by eLM's reader is requested, a future handler could fall back.
