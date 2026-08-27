"""Database session and connection pool management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

# Primary Application Async Engine (Read-Write for app & ingestion)
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL == "debug"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Async Session Factory
async_session_factory = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Dedicated Read-Only Engine for LangGraph Agent
agent_engine: AsyncEngine = create_async_engine(
    settings.AGENT_DATABASE_URL,
    echo=(settings.LOG_LEVEL == "debug"),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

agent_session_factory = async_sessionmaker(
    bind=agent_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider yielding an active async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_agent_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider yielding a read-only agent DB session."""
    async with agent_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
