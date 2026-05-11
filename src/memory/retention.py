from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from asyncpg import Pool

logger = logging.getLogger(__name__)

_BATCH_SIZE = 1000  # удаляем батчами, чтобы не блокировать таблицу длинной транзакцией


async def _batch_delete(pool: Pool, sql: str, *args: object) -> int:
    """
    Выполняет батч-удаление, возвращая количество удалённых строк за один проход.
    Caller повторяет вызов до тех пор, пока результат != 0.
    """
    async with pool.acquire() as conn:
        status = await conn.execute(sql, *args)
    # execute() возвращает строку вида "DELETE N"
    return int(status.split()[-1])


async def delete_old_sessions(pool: Pool, days: int = 90) -> int:
    """
    Удаляет сессии (и каскадно messages, interactions), которые не обновлялись
    более N дней. Использует батч-удаление по BATCH_SIZE строк.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = 0

    while True:
        deleted = await _batch_delete(
            pool,
            """
            DELETE FROM sessions
            WHERE id IN (
                SELECT id FROM sessions
                WHERE last_active_at < $1
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            """,
            cutoff,
            _BATCH_SIZE,
        )
        total += deleted
        if deleted == 0:
            break

    if total:
        logger.info("Retention: удалено %d сессий старше %d дней", total, days)
    return total


async def delete_old_interactions(pool: Pool, days: int = 14) -> int:
    """
    Удаляет записи interactions старше N дней.
    Interactions не удаляются каскадно при удалении сессии в некоторых конфигурациях.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total = 0

    while True:
        deleted = await _batch_delete(
            pool,
            """
            DELETE FROM interactions
            WHERE id IN (
                SELECT id FROM interactions
                WHERE created_at < $1
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            """,
            cutoff,
            _BATCH_SIZE,
        )
        total += deleted
        if deleted == 0:
            break

    if total:
        logger.info("Retention: удалено %d interactions старше %d дней", total, days)
    return total


async def run_retention(pool: Pool) -> None:
    """Запускает все retention-задачи. Предназначен для вызова из cron-планировщика."""
    logger.info("Запуск retention-очистки данных")
    sessions_deleted = await delete_old_sessions(pool, days=90)
    interactions_deleted = await delete_old_interactions(pool, days=14)
    logger.info(
        "Retention завершён: сессии=%d, interactions=%d",
        sessions_deleted,
        interactions_deleted,
    )
