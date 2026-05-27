"""Base model with common columns: id, created_at, updated_at, deleted_at."""

import time

from sqlalchemy import BigInteger, Column, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Mixin that adds id, created_at, updated_at, deleted_at.

    Per 00-global.md:
    - id: BIGSERIAL (BigInteger autoincrement)
    - created_at, updated_at: UTC integer timestamp
    - deleted_at: nullable UTC integer timestamp (soft delete)
    """

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    created_at: Mapped[int] = mapped_column(
        Integer, default=lambda: int(time.time()), nullable=False
    )

    updated_at: Mapped[int] = mapped_column(
        Integer,
        default=lambda: int(time.time()),
        onupdate=lambda: int(time.time()),
        nullable=False,
    )

    deleted_at: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
