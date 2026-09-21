"""Library backup / restore (item 2.3).

A backup is one ZIP: the SQLite database via the stdlib online-backup API
(WAL-safe, runs while the app is live), the covers directory, and a
``settings.json`` export. Restore swaps the database file and re-extracts
covers; the engine disposal and settings upsert stay with the caller so this
module stays pure file work.
"""

import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def db_path_from_url(database_url: str) -> Path:
    """Extract the file path from a sqlite database URL.

    Raises:
        ValueError: If the URL is not a file-backed SQLite database.
    """
    if "sqlite" not in database_url or ":memory:" in database_url:
        raise ValueError("Backup requires a file-backed SQLite database")
    return Path(database_url.split("///", 1)[-1])


def _safe_zip_member(name: str) -> bool:
    """Reject absolute paths and traversal in archive members (zip-slip)."""
    if name.startswith("/") or ".." in Path(name).parts:
        return False
    return True


def list_backups(backups_dir: Path) -> list[str]:
    """Sorted (newest first) backup ZIP names in the directory."""
    if not backups_dir.is_dir():
        return []
    return sorted(
        (p.name for p in backups_dir.glob("*.zip")), reverse=True
    )


def create_backup(
    db_path: Path,
    covers_dir: Path,
    settings_map: dict[str, str],
    dest_dir: Path,
    label: str = "elibrary",
) -> Path:
    """Write one backup ZIP and return its path.

    Args:
        db_path: SQLite database file (read via the online-backup API).
        covers_dir: Cover images directory (skipped if missing).
        settings_map: Settings key/value export.
        dest_dir: Directory receiving the ZIP (created if needed).
        label: Filename prefix, e.g. ``elibrary`` or ``pre-restore``.

    Returns:
        Path of the written ZIP.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = dest_dir / f"{label}-{stamp}.zip"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        if db_path.is_file():
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                tmp = dest_dir / f".backup-{stamp}.db"
                dst = sqlite3.connect(tmp)
                try:
                    with dst:
                        src.backup(dst)
                finally:
                    dst.close()
                zf.write(tmp, arcname="db/dawnstar.db")
            finally:
                src.close()
                tmp.unlink(missing_ok=True)
        if covers_dir.is_dir():
            for image in covers_dir.rglob("*"):
                if image.is_file():
                    zf.write(image, arcname=f"covers/{image.relative_to(covers_dir)}")
        zf.writestr("settings.json", json.dumps(settings_map, ensure_ascii=False))
    return out


def apply_restore(zip_path: Path, db_path: Path, covers_dir: Path) -> dict[str, str]:
    """Swap in the database and covers from a backup ZIP.

    The caller must have disposed the SQLAlchemy engine before calling — open
    connections would keep writing to the replaced file.

    Returns:
        The settings map from the archive.
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if _safe_zip_member(n)]
        db_members = [n for n in names if n.startswith("db/") and n.endswith(".db")]
        if not db_members:
            raise ValueError("Backup archive contains no database file")

        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove sidecar WAL/SHM files of the replaced database.
        for suffix in ("-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)
        zf.extract(db_members[0], path=db_path.parent)
        extracted = db_path.parent / db_members[0]
        extracted.replace(db_path)

        if covers_dir.is_dir():
            cover_members = [n for n in names if n.startswith("covers/")]
            archive_files = {
                Path(n).relative_to("covers") for n in cover_members
            }
            # Faithful snapshot: drop covers that aren't in the archive.
            for existing in covers_dir.rglob("*"):
                if existing.is_file() and existing.relative_to(covers_dir) not in archive_files:
                    existing.unlink(missing_ok=True)
            for name in cover_members:
                target = covers_dir / Path(name).relative_to("covers")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())

        if "settings.json" in names:
            return json.loads(zf.read("settings.json") or "{}")
    return {}
