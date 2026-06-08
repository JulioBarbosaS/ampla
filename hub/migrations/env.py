"""Alembic environment. Migrations run over a SYNC sqlite engine (the app uses
async aiosqlite on the same file); render_as_batch makes SQLite ALTERs work."""

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401 — register every model in the metadata
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def _sync_url() -> str:
    # App URL is sqlite+aiosqlite://… ; Alembic uses the plain sync driver.
    return get_settings().database_url.replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_sync_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
