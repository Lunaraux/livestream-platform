"""Test fixtures — async client, test DB, mocked Redis blacklist."""

import time
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.main import create_app


# ── Test database ──────────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Redis mock ─────────────────────────────────────────────────────

def _mock_redis():
    """Create a mock that fakes a Redis blacklist store."""
    store: dict[str, str] = {}

    mock = AsyncMock()
    mock.setex = AsyncMock(side_effect=lambda key, ttl, value: store.__setitem__(key, value))
    mock.get = AsyncMock(side_effect=lambda key: store.get(key))
    mock.exists = AsyncMock(side_effect=lambda key: 1 if key in store else 0)
    mock.aclose = AsyncMock()
    return mock


# ── App fixture ────────────────────────────────────────────────────

@pytest.fixture
async def app():
    """Create a fresh FastAPI app with test DB and mocked Redis."""
    from app.models.base import Base

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    yield app

    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for test requests."""
    redis_mock = _mock_redis()
    with patch("app.core.security._get_redis", return_value=redis_mock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def now_ts() -> int:
    """Sanitized current UTC timestamp (seconds)."""
    return int(time.time())
