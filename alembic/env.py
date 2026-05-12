from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """
    Читает DATABASE_URL из окружения и нормализует схему для asyncpg.
    Поддерживает postgresql://, postgres://, postgresql+asyncpg://.
    """
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    raise ValueError(f"Неподдерживаемый формат DATABASE_URL: {url!r}")


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=None,
        # Сравнение схем не используется — все изменения через явные миграции
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Режим без подключения к БД — генерирует SQL-скрипт."""
    context.configure(
        url=_get_database_url(),
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(_get_database_url(), echo=False)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
