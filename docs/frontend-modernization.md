# Frontend Modernization Roadmap

## Current state

The frontend is **vanilla ES2015+ JavaScript** served as classic `<script>`
tags by FastAPI. There is no framework, no bundler, and no build step today.
Three files hold the vast majority of the logic and are the largest
maintainability debt in the project:

| File | Lines | Concern |
|------|-------|---------|
| `frontend/static/js/reader-icecream.js` | ~3,400 | Reader UI, TOC, chapters, caching, prefetch, bookmarks, notes, annotations, summary, TTS bridge |
| `frontend/static/js/library.js`        | ~2,600 | Library grid/table, filtering, sorting, search, upload, import, categories |
| `frontend/static/js/tts.js`            | ~1,200 | Text-to-speech engine + UI |

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

1. ✅ Tooling scaffolded (this change).
2. ⏳ Extract `lib/` helpers (done: `api`, `storage`, `dom`). Wire
   `reader-icecream.js`'s fetch calls through `lib/api.js` (mechanical).
3. ⏳ Split `reader-icecream.js` by concern into modules under
   `static/js/reader/`: `toc.js`, `chapter-cache.js`, `bookmarks.js`,
   `annotations.js`, `summary.js`, `tts-bridge.js`.
4. ⏳ Bundle the reader entry via `build.mjs` and switch the template to the
   built asset.
5. ⏳ Repeat for `library.js` and `tts.js`.

## Why not adopt a framework now?

The Icecream Reader UI is a near-complete pixel-perfect clone working today in
~7k lines of vanilla JS. A framework migration would be a multi-week rewrite
with high regression risk and no user-facing benefit. Incremental modularisation
captures ~80% of the maintainability win (testability, smaller files, clear
boundaries) at a fraction of the risk.
