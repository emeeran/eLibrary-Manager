# Frontend Modernization Roadmap

## Current state

The frontend is **vanilla ES2015+ JavaScript** served as classic `<script>`
tags by FastAPI. There is no framework and no runtime build step. The reader
was a single ~3,400-line monolith (`reader-icecream.js`) and has now been
**decomposed into focused modules** under `frontend/static/js/reader/`. The
library and TTS files remain monolithic and are the next candidates.

| File | Lines | Concern | Status |
|------|-------|---------|--------|
| `frontend/static/js/reader/*.js` | ~3,400 (11 files) | Reader UI, TOC, chapters, caching, prefetch, bookmarks, notes, annotations, summary, TTS bridge | ✅ modularized |
| `frontend/static/js/library.js`        | ~2,600 | Library grid/table, filtering, sorting, search, upload, import, categories | ⏳ pending |
| `frontend/static/js/tts.js`            | ~1,200 | Text-to-speech engine + UI | ⏳ pending |

`CLAUDE.md` previously claimed "React / Next.js (App Router)" — that was
aspirational, not reality. The JS rules in `CLAUDE.md` have been corrected.

## Tooling now in place

- `frontend/package.json` — dev tooling (esbuild, ESLint flat config, Prettier).
- `frontend/eslint.config.js` — ESLint flat config enforcing modern, safe
  patterns. Run `npm run lint`.
- `frontend/build.mjs` — esbuild bundler for new module entries. Run
  `npm run build` / `npm run watch`. Currently a no-op until entries are
  registered, so it cannot break existing serving.
- `frontend/static/js/lib/` — new ES-module helpers that establish the
  extraction pattern:
  - `api.js` — typed `fetch` wrapper (`api`, `apiGet/Post/Put/Delete`, `beacon`).
  - `storage.js` — safe JSON `localStorage` helpers.
  - `dom.js` — `qs`, `qsa`, `el`, `debounce`, `setTrustedHTML`.

## Migration principles

1. **No big-bang rewrite.** Each monolith is decomposed incrementally; the app
   stays shippable after every step.
2. **Extract pure logic first.** Helpers with no DOM state (fetch, storage,
   formatting, debounce) move to `lib/` and gain unit tests before anything
   else.
3. **Preserve the `XReader = { ... }` module-object pattern** for stateful
   controllers until a bundler is required at runtime; only then convert to
   ES module exports.
4. **Trust boundary stays server-side.** Book HTML is sanitised with nh3 before
   reaching the client. `setTrustedHTML()` exists to keep that boundary visible
   at every call site; never feed unsanitised strings to `innerHTML`.
5. **Add Vitest unit tests** for each extracted module under
   `frontend/test/` as it lands.

## Phased plan

1. ✅ Tooling scaffolded.
2. ✅ Extract `lib/` helpers (`api`, `storage`, `dom`).
3. ✅ **Split the reader monolith into classic-script modules under
   `static/js/reader/`** (state, ui, settings, chapters, search, annotations,
   panels, summary, tts-bridge, init, globals). Loaded in dependency order via
   `reader.html`; `globals.js` is last so all `window.*` exports resolve.
   Verified in headless Chrome (no JS errors, `initReader` runs end-to-end).
4. ⏳ Route the reader's `fetch` calls through `lib/api.js` (mechanical) and
   route the remaining `localStorage` access through `lib/storage.js`.
5. ⏳ Repeat the split for `library.js` and `tts.js`.
6. ⏳ (Optional, later) Convert the classic modules to ES modules + `addEventListener`,
   removing the inline `onclick` handler contract; bundle via `build.mjs`.

## Why classic-script split (not ES modules) for the reader

The Jinja templates attach behavior via **inline `onclick="fnName()"` handlers**
(~55 in `reader.html`) and call `window.readerApp.init(bookId)`. Inline handlers
resolve names against the global object (`window`) only — they cannot see
top-level `let`/`const`/ES-module bindings. Converting to ES modules would
therefore require rewriting every inline handler to `addEventListener` in the
same pass, which is high-risk for a pixel-precise UI that already works.

Classic `<script>` files share a single global scope: `function` declarations
become `window.*` properties (callable from inline handlers), and top-level
`const`/`let` (e.g. `IcecreamReader`) live in a shared global lexical
environment visible to all subsequent scripts and their function bodies.
Splitting into ordered classic scripts therefore delivers the maintainability
win (small, cohesive, independently-testable files) with **zero** template
handler changes and no behavioral risk. The ES-module conversion is staged as a
later, separate step (phase 6).

## Why not adopt a framework now?

The Icecream Reader UI is a near-complete pixel-perfect clone working today in
~7k lines of vanilla JS. A framework migration would be a multi-week rewrite
with high regression risk and no user-facing benefit. Incremental modularisation
captures ~80% of the maintainability win (testability, smaller files, clear
boundaries) at a fraction of the risk.
