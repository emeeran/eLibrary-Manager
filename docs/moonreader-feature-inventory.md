# Moon+ Reader Pro 10.7 — Feature Inventory (REA static analysis)

**Purpose:** feature-parity source for eLibrary Manager SDD. Behavioral study
only — no Moon+ code, resources, or assets are copied into eLibrary.

## Target identity

| Fact | Value | Evidence |
|---|---|---|
| Package | `com.flyersoft.moonreaderp` v10.7 (1007000) | `ev_d57f84a4…` |
| APK SHA-256 | `0bb1214a209b8e4f133dacd1daa1b55b49242c3885d1359d453006de362eefb5` | — |
| Size | 12,958 classes, 2,153 resources, 2,419 decoded files | `ev_d57f84a4…` |
| SDK | minSdk 21 → targetSdk 36 | `ev_d57f84a4…` |
| Resources | 946 default strings, 87 locales | `ev_d7fa0635…` |

> ⚠️ Build is a "(Patched)" cracked copy — DRM-stripped by a third party.
> Features may deviate from official Play Store Pro. Analysis is static and
> behavioral; eLibrary implements features independently.

## Format engines (classes + native libs)

| Format | Implementation | Signal |
|---|---|---|
| PDF | **Radaee** engine — `com.radaee.{view,reader,util}` (34 classes) + `librdpdf.so` | Pen/hl annots, outlines, thumbnails, text reflow, render quality, max zoom, unify page sizes, print/share |
| DJVU | native `libmydjvu.so` | — |
| EPUB | `com.flyersoft.books.Epub` | embedded fonts, epub3 print page numbers, JS toggle |
| FB2 | `com.flyersoft.books.Fb2` + `assets/fb2.css` | custom user CSS |
| MOBI/AZW | `com.flyersoft.books.Mobi` + `libmloader.so` | — |
| CHM | `com.flyersoft.books.chmlib` (35 classes) | — |
| Others | `Docx`, `Md`, `Mhtml`, `Rtf`, `Umd`, `ComicInfo` (CBZ), Html/Txt | — |
| Rendering | `com.flyersoft.staticlayout.*` (~90 classes): custom text layout, TeX hyphenation (21-language pattern dicts in assets), span types incl. squiggly/table/shadow/sub-super-script | — |
| Images | Fresco (`libimagepipeline.so`, `libnative-imagetranscoder.so`) | slideshow interval, pic gallery |

## Feature clusters

1. **Reader modes** — dual-page (auto for foldables, landscape-only, book-style
   bg), auto-scroll w/ speed control, scroll modes, page-turn animations
   (3D curl `NewCurl3D`, cover `GoogleBook3D`, slide h/v), e-ink mode (no
   animations), AMOLED dark, auto day/night by time *or* brightness sensor,
   bluelight filter, immersive mode, vertical text, RTL, justification,
   hyphenation, CSS override toggles (indent/justify/margin/others), footnotes
   inline (`FootnoteTextView`), magnifier, `PrefSpeedRead` (RSVP mode).
2. **Input/gestures** — tap zones, swipe, tilt-to-turn (sensitivity),
   shake-phone actions (`MyShakeSensorListener`), volume-key page turns,
   headset play key, dpad, custom keycode.
3. **Annotations** — highlight styles incl. **squiggly**, underline,
   strikethrough/strikeout, color templates above toolbar, long-tap-drag
   direct highlight, PDF pen width, popup notes, bookmark editor,
   `last_highlight_as_text_selection`.
4. **TTS** — `BookTtsService` (foreground media playback), pitch/speed/volume,
   sentence interval, content division, char filters, stop-after-N-minutes
   timer, notification-bar controls, pre-speak confirmation.
5. **Cloud sync/backup** — Dropbox SDK (46 classes) + Google Drive; shelf sync
   + reading-position sync, Wi-Fi-only, auto-backup w/ scope
   (all shelf + first 20 recent), local backup/restore, free→Pro migration.
6. **OPDS / Net Library** — `com.flyersoft.opds.*` (`OpdsSite`, `OpdsEntries`),
   add/edit/delete catalogs by URL, download service, auto-detect OPDS from
   opened URLs.
7. **Dictionary** — `DictPackage`, history, custom online-dict URL template
   (`%s` for keyword), single-tap vs long-tap open, system app dictionary
   handoff.
8. **Integrations** — **Readwise export** (`components.Readwise`), share text,
   `PROCESS_TEXT` (define/translate), print, home-screen **widget**
   (`WidgetProvider/Service`), book reading calendar (`BookCalendar`, 15
   classes).
9. **Statistics** — by day/week/month/year, clear-all, heatmap calendar views.
10. **Security** — fingerprint/biometric book protection (`biometricprompt_*`
    strings, `USE_BIOMETRIC`).
11. **Library/shelf** — auto-import watched folders, group books, filters,
    sort by import time, cover download, shelf views (`BookShelfView`,
    `CoverFlow`).

## eLibrary gap matrix (Phase 3)

| Moon+ feature | eLibrary status | Proposed spec action |
|---|---|---|
| OPDS catalogs | none | **New 015** — pair with 009 NAS |
| Dual-page, auto-scroll, page animations, scroll modes | partial (002) | **Extend 002 or new 016** |
| TTS pitch/interval/filters/timer/notification | partial (006) | **Extend 006** |
| Highlight styles (squiggly, strikeout, color templates) | partial (005) | **Extend 005** |
| Formats: fb2, djvu, cbz, rtf, docx, md, chm | epub/pdf/mobi only (008) | **Extend 008** (djvu via `djvulibre`/`mupdf`) |
| Auto-scroll / speed-read (RSVP) | none | **New spec** |
| Dictionary lookup | none | **New spec** (optional) |
| Readwise highlight export | none | **New spec** (optional, small) |
| Statistics heatmap/by-year | partial (stats routes) | **Extend** stats spec |
| Cloud sync (Dropbox/GDrive) | N/A (self-hosted, single server) | **Skip** |
| Home-screen widget | N/A web app | **Skip** (could add desktop launcher icon later) |
| Biometric book protection | per-book password (010) | **Skip** — no biometric API server-side |
| Footnotes inline, hyphenation, vertical/RTL text | partial (002) | Consider in 002 extension |

Raw data: `~/rea-work/` (resources.json, strings-inventory.md, classes-*.json).
