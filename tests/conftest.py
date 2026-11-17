"""Pytest configuration and test database isolation."""
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.config import settings
from app.models import Base
import app.database as app_db

test_engine = create_async_engine(
    settings.TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

TestAsyncSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Point app database engine to dedicated test database using NullPool."""
    app_db.engine = test_engine
    app_db.AsyncSessionLocal = TestAsyncSessionLocal

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()
