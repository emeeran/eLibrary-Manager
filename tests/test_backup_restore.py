"""Tests for library backup / restore (item 2.3).

The service functions run against real temp files (a small SQLite DB with the
books schema, plus fake covers); route-level tests stub the engine disposal so
the shared in-memory test engine survives.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services.backup_service import apply_restore, create_backup, db_path_from_url

BOOKS_SCHEMA = (
    "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, progress REAL)"
)


@pytest.fixture
def db_file(tmp_path):
    """A small SQLite file with one book row."""
    path = tmp_path / "dawnstar.db"
    con = sqlite3.connect(path)
    with con:
        con.executescript(BOOKS_SCHEMA)
        con.execute("INSERT INTO books (title, progress) VALUES ('Dune', 42.0)")
    con.close()
    return path


@pytest.fixture
def covers_dir(tmp_path):
    covers = tmp_path / "covers"
    covers.mkdir()
    (covers / "a.jpg").write_bytes(b"fake-jpg")
    return covers


def test_db_path_from_url_rejects_memory():
    with pytest.raises(ValueError, match="file-backed"):
        db_path_from_url("sqlite+aiosqlite:///:memory:")


def test_backup_restore_round_trip(tmp_path, db_file, covers_dir):
    """Backup → mutate → restore yields the original row back (AC 2.3.1)."""
    backups = tmp_path / "backups"
    zip_path = create_backup(db_file, covers_dir, {"theme": "day"}, backups)
    assert zip_path.is_file()
    assert "settings.json" in zipfile_names(zip_path)

    # Mutate after backup: add a second book and a cover, delete the settings key.
    con = sqlite3.connect(db_file)
    with con:
        con.execute("INSERT INTO books (title, progress) VALUES ('Extra', 0)")
    con.close()
    (covers_dir / "b.jpg").write_bytes(b"new")

    settings = apply_restore(zip_path, db_file, covers_dir)
    assert settings == {"theme": "day"}

    con = sqlite3.connect(db_file)
    titles = [r[0] for r in con.execute("SELECT title FROM books").fetchall()]
    con.close()
    assert titles == ["Dune"]
    assert sorted(p.name for p in covers_dir.iterdir()) == ["a.jpg"]


def test_restore_refuses_garbage_archive(tmp_path, db_file, covers_dir):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    from zipfile import BadZipFile

    with pytest.raises((ValueError, BadZipFile)):
        apply_restore(bad, db_file, covers_dir)


def test_restore_refuses_archive_without_db(tmp_path, db_file, covers_dir):
    import zipfile

    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("settings.json", "{}")
    with pytest.raises(ValueError, match="no database file"):
        apply_restore(empty, db_file, covers_dir)


def zipfile_names(path: Path) -> list[str]:
    import zipfile

    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


@pytest.mark.asyncio
async def test_restore_route_gate_and_swap(client, monkeypatch, tmp_path):
    """Route takes a pre-restore backup and swaps the DB; gate fails closed."""
    import app.routes.maintenance as maint

    db_file = tmp_path / "dawnstar.db"
    con = sqlite3.connect(db_file)
    with con:
        con.executescript(BOOKS_SCHEMA)
        con.execute("INSERT INTO books (title, progress) VALUES ('Dune', 42.0)")
    con.close()
    backups = tmp_path / "backups"
    backups.mkdir()

    covers = tmp_path / "covers"
    covers.mkdir()
    monkeypatch.setattr(maint, "_db_file_path", lambda: db_file)
    monkeypatch.setattr(maint, "_backups_dir", lambda d=None: backups)
    monkeypatch.setattr(maint, "get_config", lambda: SimpleNamespace(covers_path=str(covers)))

    class _StubEngine:
        async def dispose(self):
            self.disposed = True

    stub = _StubEngine()

    class _StubManager:
        _engine = stub

        @property
        def engine(self):
            return self._engine

        @staticmethod
        async def get_session():
            class _S:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def merge(self, obj):
                    pass

                async def commit(self):
                    pass

            return _S()

    monkeypatch.setattr(maint, "db_manager", _StubManager())

    # First, create a backup through the route itself.
    resp = await client.post("/api/maintenance/backup")
    assert resp.status_code == 200
    backup_name = Path(resp.json()["file"]).name

    # Mutate after the backup.
    con = sqlite3.connect(db_file)
    with con:
        con.execute("INSERT INTO books (title, progress) VALUES ('Extra', 0)")
    con.close()

    resp = await client.post(
        "/api/maintenance/restore", data={"backup_name": backup_name}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["restored"] is True
    assert data["pre_restore_backup"].startswith("pre-restore-")
    assert stub.disposed is True

    con = sqlite3.connect(db_file)
    titles = [r[0] for r in con.execute("SELECT title FROM books").fetchall()]
    con.close()
    assert titles == ["Dune"]


@pytest.mark.asyncio
async def test_restore_route_refuses_when_pre_backup_fails(client, monkeypatch, tmp_path):
    """If the pre-restore backup cannot be written, restore is refused (AC 2.3.2)."""
    import app.routes.maintenance as maint

    monkeypatch.setattr(maint, "_db_file_path", lambda: tmp_path / "nope.db")
    monkeypatch.setattr(
        maint, "_backups_dir", lambda d=None: tmp_path / "backups"
    )
    monkeypatch.setattr(
        maint, "get_config", lambda: SimpleNamespace(covers_path=str(tmp_path / "covers"))
    )
    # db file does not exist -> force backup creation to raise; patch the
    # route module's own binding of create_backup.
    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(maint, "create_backup", _boom)

    # The named backup must exist so the route reaches the pre-restore gate.
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "whatever.zip").write_bytes(b"placeholder")

    resp = await client.post(
        "/api/maintenance/restore",
        files={"backup_name": (None, "whatever.zip")},
    )
    assert resp.status_code == 500, resp.text
    assert "pre-restore backup failed" in resp.json()["detail"]
