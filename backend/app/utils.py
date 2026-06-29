"""Small shared utility helpers used across modules."""

from __future__ import annotations

import hashlib


def hash_path(path: str) -> str:
    """Return a stable 32-char hex key for a filesystem path.

    Maps a book/NAS path to a deterministic key used for cache directories and
    generated asset filenames. Equivalent to ``sha256(path.encode())[:32]``.

    Args:
        path: Filesystem path to hash.

    Returns:
        A 32-character lowercase hex string.
    """
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]
