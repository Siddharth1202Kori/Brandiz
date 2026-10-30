"""Keyword Magic filters + sort, applied in memory on the cached full ideas result.

A row whose metric is unknown (None) fails any bound on that metric, and sorts last in
either direction — "no data" never pretends to be 0.
"""

from typing import Literal

from pydantic import BaseModel, Field

from seomaster_core.keywords import word_count
from seomaster_core.seo import KeywordMetrics

SortField = Literal["volume", "kd", "cpc", "competition", "keyword"]
SortDir = Literal["asc", "desc"]


class IdeaFilters(BaseModel):
    volume_min: int | None = Field(default=None, ge=0)
    volume_max: int | None = Field(default=None, ge=0)
    kd_min: int | None = Field(default=None, ge=0, le=100)
    kd_max: int | None = Field(default=None, ge=0, le=100)
    cpc_min: float | None = Field(default=None, ge=0)
    cpc_max: float | None = Field(default=None, ge=0)
    words_min: int | None = Field(default=None, ge=1)
    words_max: int | None = Field(default=None, ge=1)
    intents: list[str] = []  # any of
    include: list[str] = []  # all must appear
    exclude: list[str] = []  # none may appear


def _within(value: float | None, lo: float | None, hi: float | None) -> bool:
    if lo is None and hi is None:
        return True
    if value is None:
        return False
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def matches(m: KeywordMetrics, f: IdeaFilters) -> bool:
    kw = m.keyword
    return (
        _within(m.volume, f.volume_min, f.volume_max)
        and _within(m.kd, f.kd_min, f.kd_max)
        and _within(m.cpc, f.cpc_min, f.cpc_max)
        and _within(word_count(kw), f.words_min, f.words_max)
        and (not f.intents or any(i in m.intents for i in f.intents))
        and all(t.lower() in kw for t in f.include if t.strip())
        and not any(t.lower() in kw for t in f.exclude if t.strip())
    )


def apply(
    rows: list[KeywordMetrics],
    f: IdeaFilters,
    sort: SortField = "volume",
    direction: SortDir = "desc",
) -> list[KeywordMetrics]:
    kept = [m for m in rows if matches(m, f)]
    if sort == "keyword":
        return sorted(kept, key=lambda m: m.keyword, reverse=direction == "desc")
    known = [m for m in kept if getattr(m, sort) is not None]
    unknown = [m for m in kept if getattr(m, sort) is None]
    # stable tie-break on keyword keeps pagination deterministic
    known.sort(key=lambda m: m.keyword)
    known.sort(key=lambda m: getattr(m, sort), reverse=direction == "desc")
    return known + unknown
