"""Test fixtures — async client, test DB, mocked Redis."""

import time
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

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
    """Create a mock that fakes a Redis key-value store with sorted set support."""
    store: dict[str, str] = {}
    zsets: dict[str, dict[str, float]] = {}

    async def _setex(key, ttl, value):
        store[key] = value
    async def _get(key):
        return store.get(key)
    async def _exists(key):
        return 1 if key in store else 0
    async def _set(key, value):
        store[key] = value
    async def _incrby(key, amount):
        current = int(store.get(key, 0))
        store[key] = str(current + amount)
        return current + amount
    async def _delete(key):
        store.pop(key, None)
    async def _expire(key, ttl):
        pass  # no-op in mock
    async def _zadd(key, mapping):
        if key not in zsets:
            zsets[key] = {}
        zsets[key].update(mapping)
    async def _zremrangebyscore(key, min_score, max_score):
        if key not in zsets:
            return 0
        removed = 0
        to_remove = [
            member for member, score in zsets[key].items()
            if min_score <= score <= max_score
        ]
        for member in to_remove:
            del zsets[key][member]
            removed += 1
        return removed
    async def _zcard(key):
        return len(zsets.get(key, {}))
    async def _aclose():
        pass

    mock = AsyncMock()
    mock.setex = AsyncMock(side_effect=_setex)
    mock.get = AsyncMock(side_effect=_get)
    mock.exists = AsyncMock(side_effect=_exists)
    mock.set = AsyncMock(side_effect=_set)
    mock.incrby = AsyncMock(side_effect=_incrby)
    mock.delete = AsyncMock(side_effect=_delete)
    mock.expire = AsyncMock(side_effect=_expire)
    mock.zadd = AsyncMock(side_effect=_zadd)
    mock.zremrangebyscore = AsyncMock(side_effect=_zremrangebyscore)
    mock.zcard = AsyncMock(side_effect=_zcard)
    mock.aclose = AsyncMock(side_effect=_aclose)
    return mock


@pytest.fixture
async def app():
    """Create a fresh FastAPI app with test DB and mocked Redis.

    Monkey-patches get_redis at every import site BEFORE creating the app,
    so all module-level imports of get_redis resolve to the mock.
    """
    # Create fresh Redis mock for each test
    fresh_mock = _mock_redis()

    async def _mock_get_redis():
        return fresh_mock
    # Must import and patch BEFORE any other app imports that reference get_redis
    import app.core.redis as core_redis

    core_redis.get_redis = _mock_get_redis

    # Now the rest of the app can be created — all imports resolve to mock
    from app.models.base import Base

    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Also patch already-imported modules that cached get_redis as a local name
    import app.core.security as security_mod
    import app.services.room_service as room_svc
    import app.services.interaction_service as interaction_svc

    security_mod.get_redis = _mock_get_redis
    room_svc.get_redis = _mock_get_redis
    interaction_svc.get_redis = _mock_get_redis

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    yield app

    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for test requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def now_ts() -> int:
    """Sanitized current UTC timestamp (seconds)."""
    return int(time.time())
