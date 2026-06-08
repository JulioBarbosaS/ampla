"""Migrations apply cleanly AND stay in sync with the models. `alembic check`
fails if someone changes a model without adding a matching migration — that
is the drift guard that keeps the upgrade path safe."""

import os
import subprocess
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[2]


def _alembic(args, db) -> subprocess.CompletedProcess:
    env = {**os.environ, "AMP_DATABASE_URL": f"sqlite+aiosqlite:///{db}"}
    return subprocess.run(  # noqa: S603 — fixed args, trusted input (the test runner)
        [sys.executable, "-m", "alembic", *args],
        cwd=HUB,
        env=env,
        capture_output=True,
        text=True,
    )


def test_migrations_apply_and_match_models(tmp_path):
    db = tmp_path / "m.db"
    up = _alembic(["upgrade", "head"], db)
    assert up.returncode == 0, up.stderr
    check = _alembic(["check"], db)
    assert check.returncode == 0, check.stdout + check.stderr  # no model/migration drift
