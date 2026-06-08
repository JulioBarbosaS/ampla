"""Consistent online backup of the SQLite database.

Uses the sqlite3 backup API, which snapshots a live database safely — including
any WAL pages not yet checkpointed — so an operator can back up without stopping
the hub. Restore is a file copy with the hub stopped (see README).

    python -m app.db_backup /data/amp-backup.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings


def sqlite_path(database_url: str) -> str:
    """The on-disk file behind an (async or sync) SQLite URL."""
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("Backup disponível apenas para SQLite.")
    if not url.database or url.database == ":memory:":
        raise ValueError("Banco em memória não pode ser copiado.")
    return url.database


def online_backup(database_url: str, dest: str | Path) -> Path:
    """Snapshot the database to `dest` (hot, consistent). Returns the dest path."""
    source = sqlite3.connect(sqlite_path(database_url))
    try:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)  # atomic snapshot, WAL included
        finally:
            target.close()
    finally:
        source.close()
    return dest


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python -m app.db_backup <arquivo-destino>", file=sys.stderr)
        return 2
    dest = online_backup(get_settings().database_url, argv[0])
    print(f"backup gravado em {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
