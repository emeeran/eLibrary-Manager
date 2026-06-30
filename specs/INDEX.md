# eLibrary Manager — Spec Index

**Spec-Driven Development Registry**

| ID | Spec | Status | Version | Last Updated | Key Files |
|----|------|--------|---------|-------------|-----------|
| 001 | [Library Management](001-library-management.md) | Active | 1.0.0 | 2026-04-15 | `app/routes/library.py`, `app/services/library_service.py` |
| 002 | [Reader Interface](002-reader-interface.md) | Active | 1.0.0 | 2026-04-15 | `app/routes/reader.py`, `app/services/reader_service.py` |
| 003 | [AI Summarization](003-ai-summarization.md) | Active | 1.0.0 | 2026-04-15 | `app/ai_engine.py`, `app/ai_providers/` |
| 004 | [Bookmarks](004-bookmarks.md) | Active | 1.0.0 | 2026-04-15 | `app/models.py` (Bookmark), `app/routes/reader.py` |
| 005 | [Notes & Annotations](005-notes-annotations.md) | Active | 1.0.0 | 2026-04-15 | `app/models.py` (Note, Annotation), `app/routes/reader.py` |
| 006 | [Text-to-Speech](006-text-to-speech.md) | Active | 1.0.0 | 2026-04-15 | `app/routes/ai_tts.py`, `app/static/js/tts.js` |
| 007 | [Settings](007-settings.md) | Active | 1.0.0 | 2026-04-15 | `app/routes/settings.py` |
| 008 | [File Parsers](008-file-parsers.md) | Active | 1.0.0 | 2026-04-15 | `app/parsers/`, `app/scanner.py` |
| 009 | [NAS Integration](009-nas-integration.md) | Active | 1.0.0 | 2026-04-16 | `app/storage/`, `app/nas_health.py`, `app/nas_cache.py` |
| 010 | [Hidden Books](010-hidden-books.md) | Active | 1.0.0 | 2026-06-29 | `app/routes/hidden.py`, `app/models.py` (Book.hidden_password) |
| 011 | [Calibre Integration](011-calibre-integration.md) | Active | 1.1.0 | 2026-06-30 | `app/services/calibre_importer.py`, `app/routes/calibre.py` |
| 012 | [Full-Text Content Search](012-full-text-search.md) | Active | 1.0.0 | 2026-06-30 | `app/services/content_extractor.py`, `app/services/content_backfill_service.py`, `app/repositories.py` |
| 013 | [Calibre-Web → eLM Reader Deep Link](013-calibre-reader-deeplink.md) | Active | 1.0.0 | 2026-06-30 | `app/routes/calibre.py` (`GET /calibre/launch`) |

## Dependency Graph

```
008-file-parsers ──► 001-library-management ──► 002-reader-interface
                                                    │
                                                    ├──► 003-ai-summarization
                                                    ├──► 004-bookmarks
                                                    ├──► 005-notes-annotations
                                                    └──► 006-text-to-speech

007-settings (standalone — affects all above via configuration)
```

## Spec Lifecycle

- **Draft:** Under review, not yet implemented
- **Active:** Implemented and traceable to code
- **Deprecated:** Superseded or removed — do not implement against

## Updating Specs

1. Any behavior change requires a spec update *first*
2. New features get a new spec or a new acceptance criterion in an existing spec
3. Spec version bumps: patch for clarifications, minor for new criteria, major for breaking changes
