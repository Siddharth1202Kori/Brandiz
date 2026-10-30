"""Response envelope + paging primitives shared by API and providers.

Envelope shape (doc 03 §5):
    {"data": ..., "meta": {"limited", "cached", "source", "fetched_at", "page"}}
"""

from datetime import datetime

from pydantic import BaseModel, Field


class PageOpts(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    sort: str | None = None


class PageInfo(BaseModel):
    offset: int
    limit: int
    total: int | None = None


class Page[T](BaseModel):
    items: list[T]
    page: PageInfo


class Meta(BaseModel):
    limited: bool = False
    cached: bool = False
    stale: bool = False
    source: str | None = None
    fetched_at: datetime | None = None
    page: PageInfo | None = None


class Envelope[T](BaseModel):
    data: T
    meta: Meta = Field(default_factory=Meta)


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
