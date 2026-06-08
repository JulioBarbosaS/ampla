"""The online backup produces a standalone, consistent copy of the data."""

import sqlite3

import pytest

from app.db_backup import online_backup, sqlite_path


def test_sqlite_path_extracts_the_file():
    assert sqlite_path("sqlite+aiosqlite:////data/amp.db") == "/data/amp.db"


def test_memory_database_cannot_be_backed_up():
    with pytest.raises(ValueError, match="memória"):
        sqlite_path("sqlite+aiosqlite:///:memory:")


def test_non_sqlite_is_rejected():
    with pytest.raises(ValueError, match="SQLite"):
        sqlite_path("postgresql://localhost/amp")


def test_backup_preserves_data_and_creates_dest_dir(tmp_path):
    src = tmp_path / "amp.db"
    conn = sqlite3.connect(src)
    conn.execute("CREATE TABLE users (id INTEGER, email TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'julio@example.com')")
    conn.commit()
    conn.close()

    dest = tmp_path / "backups" / "snap.db"  # nested dir is created
    out = online_backup(f"sqlite:///{src}", dest)

    assert out == dest and dest.exists()
    backup = sqlite3.connect(dest)
    try:
        assert backup.execute("SELECT email FROM users").fetchall() == [("julio@example.com",)]
    finally:
        backup.close()
