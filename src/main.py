from __future__ import annotations

"""FastAPI application entry point.

Lifespan:
- startup: создаёт asyncpg Pool, Redis-клиент, LLMConnector — сохраняет в app.state
- shutdown: закрывает Pool и Redis-соединение
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.api.router import api_router
from src.config import settings
from src.llm.config import LLMConfig
from src.llm.connector import LLMConnector
from src.memory.db import create_pool
from src.memory.redis_client import create_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Управляет ресурсами приложения: startup + shutdown."""
    logger.info("TravelAgent: инициализация ресурсов...")

    # PostgreSQL connection pool
    app.state.pool = await create_pool(settings.DATABASE_URL)
    logger.info("TravelAgent: PostgreSQL pool создан")

    # Redis client
    app.state.redis = create_client(settings.REDIS_URL)
    logger.info("TravelAgent: Redis client создан")

    # LLM Connector
    llm_config = LLMConfig()
    app.state.llm_connector = LLMConnector(llm_config)
    logger.info(
        "TravelAgent: LLMConnector инициализирован (provider=%r, model=%r)",
        llm_config.provider,
        llm_config.model,
    )

    logger.info("TravelAgent: готов к работе")
    yield

    # Shutdown
    logger.info("TravelAgent: завершение работы...")
    await app.state.pool.close()
    await app.state.redis.aclose()
    logger.info("TravelAgent: ресурсы освобождены")


app = FastAPI(
    title="TravelAgent API",
    description="AI-консьерж для high-end туроператоров (Telegram + Web)",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)
