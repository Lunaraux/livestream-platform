"""Unified response and pagination schemas per 00-global.md."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response envelope.

    Per 00-global.md:
    - code=0: success
    - code!=0: error with corresponding error code
    """

    code: int = Field(default=0, description="Error code, 0 = success")
    message: str = Field(default="success", description="Human-readable message")
    data: T | None = Field(default=None, description="Response payload")


class PaginatedData(BaseModel, Generic[T]):
    """Paginated list response data."""

    items: list[T] = Field(default_factory=list)
    total: int = Field(default=0)
    page: int = Field(default=1)
    page_size: int = Field(default=20)


class PaginationParams(BaseModel):
    """Pagination request parameters.

    Per 00-global.md: page starts at 1, page_size default 20 max 100.
    """

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
