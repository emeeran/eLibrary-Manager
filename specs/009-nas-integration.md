# Spec 009: NAS Integration

**Status:** Active
**Version:** 1.0.0
**Last Updated:** 2026-04-16

## Overview

Enable eLibrary Manager to index and read ebooks stored on a Synology NAS (or any SMB/NFS share) while keeping the database and extracted metadata local. Support offline reading via a persistent local cache.

## Requirements

### Functional Requirements

1. **NAS Configuration**: Users can configure NAS connection parameters (host, share, mount path, protocol, credentials) via the Settings UI.
2. **Unified Library Scan**: A single scan action indexes both local and NAS books. NAS books are tagged with `storage_type="nas"`.
3. **Transparent File Access**: NAS-sourced books are accessed via the local mount point. No parser changes are required.
4. **Connection Health Monitoring**: A background task monitors NAS mount availability every 60 seconds. Health status is exposed via API.
5. **Offline Cache**: NAS books are automatically cached locally when first opened. Users can pre-cache books for offline access via a "Make Available Offline" action.
6. **Graceful Degradation**: When NAS is offline, cached books remain readable. Uncached NAS books display a clear error message.
7. **Credential Security**: NAS passwords are encrypted at rest using Fernet symmetric encryption. Passwords are never returned in API responses.

### Non-Functional Requirements

- NAS health checks must complete within 5 seconds
- Cache eviction uses LRU strategy with a 2GB default limit
- SMB mount setup is the user's responsibility (documented in setup script)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings/nas-health` | Current NAS mount health status |
| POST | `/api/settings/test-nas` | On-demand NAS connectivity test |
| POST | `/api/books/{id}/cache` | Pre-cache a book for offline access |
| DELETE | `/api/books/{id}/cache` | Remove a book from offline cache |
| GET | `/api/library/cache-status` | Cache statistics and cached book list |

## Acceptance Criteria

- [ ] NAS configuration persists across app restarts
- [ ] Unified scan returns combined local + NAS statistics
- [ ] NAS books are tagged with `storage_type="nas"` in the database
- [ ] Cached NAS books are readable when NAS is offline
- [ ] Uncached NAS books show structured error when NAS is offline
- [ ] Health endpoint reflects current mount status
- [ ] Password encryption uses Fernet with a key derived from the DB path

## Test Coverage

- Unit: `NASStorageBackend.health_check()`, `NASFileCache.put/get/remove/cleanup`
- Unit: `encrypt_value/decrypt_value` round-trip
- Integration: Scan with both local and NAS sources
- Integration: Reader fallback to cache when NAS offline
