"""Database session and engine setup."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _normalize_db_url(url: str) -> str:
    """Convert postgres:// or postgresql:// to postgresql+asyncpg:// if needed."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_database_url = _normalize_db_url(settings.DATABASE_URL)

# Determine if we're using SQLite (tests)
_is_sqlite = "sqlite" in _database_url

connect_args = {}
if _is_sqlite:
    connect_args["check_same_thread"] = False

engine = create_async_engine(
    _database_url,
    echo=settings.DEBUG,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:  # type: ignore[valid-type]
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
