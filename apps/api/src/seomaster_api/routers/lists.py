"""/api/v1/keywords/lists — saved keyword lists (Semrush "Keyword Manager" lite).

Items copy the latest known metrics from ClickHouse `keyword_metrics` when added. Keywords
never seen before start empty; the `fetch.keyword_volume_batch` job fills them.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from seomaster_api.deps import DB, CurrentOrg, Keywords
from seomaster_api.errors import AppError
from seomaster_api.routers.keywords import csv_response
from seomaster_api.services import limits
from seomaster_core.keywords import InvalidKeywordError, normalize_keyword
from seomaster_core.markets import Market
from seomaster_core.models import Envelope
from seomaster_core.seo import KeywordMetrics
from seomaster_db.models import KeywordList, KeywordListItem

router = APIRouter(prefix="/api/v1/keywords/lists", tags=["keyword lists"])
MAX_ITEMS_PER_LIST = 1000


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    market: Market = Market.IN


class ListOut(BaseModel):
    id: uuid.UUID
    name: str
    market: Market
    created_at: datetime
    item_count: int = 0


class ItemOut(BaseModel):
    id: uuid.UUID
    keyword: str
    volume: int | None
    kd: int | None
    cpc: float | None
    competition: float | None
    intents: list[str]
    metrics_updated_at: datetime | None
    added_at: datetime


class ListDetail(BaseModel):
    info: ListOut
    items: list[ItemOut]


class ItemsIn(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=MAX_ITEMS_PER_LIST)


class ItemsAdded(BaseModel):
    added: int
    total: int


def _list_out(kl: KeywordList, count: int = 0) -> ListOut:
    return ListOut(
        id=kl.id, name=kl.name, market=Market(kl.market), created_at=kl.created_at, item_count=count
    )


def _item_out(i: KeywordListItem) -> ItemOut:
    return ItemOut(
        id=i.id,
        keyword=i.keyword,
        volume=i.volume,
        kd=i.kd,
        cpc=i.cpc,
        competition=i.competition,
        intents=list(i.intents or []),
        metrics_updated_at=i.metrics_updated_at,
        added_at=i.added_at,
    )


async def _get(db: DB, org_id: uuid.UUID, list_id: uuid.UUID) -> KeywordList:
    kl = await db.scalar(
        select(KeywordList).where(KeywordList.id == list_id, KeywordList.org_id == org_id)
    )
    if kl is None:  # 404, not 403: never confirm other orgs' ids
        raise AppError(404, "not_found", "List not found")
    return kl


async def _count(db: DB, list_id: uuid.UUID) -> int:
    q = select(func.count()).where(KeywordListItem.list_id == list_id)
    return int(await db.scalar(q) or 0)


async def _items(db: DB, list_id: uuid.UUID) -> list[KeywordListItem]:
    rows = await db.scalars(
        select(KeywordListItem)
        .where(KeywordListItem.list_id == list_id)
        .order_by(KeywordListItem.volume.desc().nulls_last(), KeywordListItem.keyword)
    )
    return list(rows)


@router.get("")
async def list_lists(db: DB, org: CurrentOrg) -> Envelope[list[ListOut]]:
    counts = (
        select(KeywordListItem.list_id, func.count().label("n"))
        .group_by(KeywordListItem.list_id)
        .subquery()
    )
    rows = await db.execute(
        select(KeywordList, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.list_id == KeywordList.id)
        .where(KeywordList.org_id == org.id)
        .order_by(KeywordList.created_at)
    )
    return Envelope(data=[_list_out(kl, n) for kl, n in rows.all()])


@router.post("", status_code=201)
async def create_list(body: ListIn, db: DB, org: CurrentOrg) -> Envelope[ListOut]:
    await limits.check_count(db, org, "keyword_lists")
    kl = KeywordList(org_id=org.id, name=body.name.strip(), market=body.market.value)
    db.add(kl)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "list_exists", "A list with this name already exists") from exc
    await db.refresh(kl)
    return Envelope(data=_list_out(kl))


@router.get("/{list_id}")
async def get_list(list_id: uuid.UUID, db: DB, org: CurrentOrg) -> Envelope[ListDetail]:
    kl = await _get(db, org.id, list_id)
    items = await _items(db, kl.id)
    return Envelope(
        data=ListDetail(info=_list_out(kl, len(items)), items=[_item_out(i) for i in items])
    )


@router.delete("/{list_id}", status_code=204)
async def delete_list(list_id: uuid.UUID, db: DB, org: CurrentOrg) -> None:
    await db.delete(await _get(db, org.id, list_id))
    await db.commit()


@router.post("/{list_id}/items")
async def add_items(
    list_id: uuid.UUID, body: ItemsIn, db: DB, org: CurrentOrg, kw: Keywords
) -> Envelope[ItemsAdded]:
    kl = await _get(db, org.id, list_id)
    keywords: list[str] = []
    for raw in body.keywords:
        try:
            k = normalize_keyword(raw)
        except InvalidKeywordError:
            continue
        if k not in keywords:
            keywords.append(k)
    if not keywords:
        raise AppError(422, "invalid_keyword", "No valid keywords")

    existing = await _count(db, kl.id)
    if existing + len(keywords) > MAX_ITEMS_PER_LIST:
        raise AppError(
            422,
            "list_full",
            f"A list holds at most {MAX_ITEMS_PER_LIST} keywords",
            {"max": MAX_ITEMS_PER_LIST, "current": existing},
        )

    try:
        known = await kw.store.latest(Market(kl.market), keywords)
    except Exception:
        known = {}  # ClickHouse down: add bare keywords, the volume job fills them later
    rows = [_item_row(kl.id, k, known.get(k)) for k in keywords]
    result = await db.execute(
        pg_insert(KeywordListItem)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["list_id", "keyword"])
        .returning(KeywordListItem.id)
    )
    added = len(result.all())
    await db.commit()
    return Envelope(data=ItemsAdded(added=added, total=existing + added))


def _item_row(list_id: uuid.UUID, keyword: str, m: KeywordMetrics | None) -> dict[str, object]:
    """Every row carries every column: multi-row INSERT needs identical keys."""
    has = m is not None and m.has_data
    return {
        "id": uuid.uuid4(),
        "list_id": list_id,
        "keyword": keyword,
        "volume": m.volume if has and m else None,
        "kd": m.kd if has and m else None,
        "cpc": m.cpc if has and m else None,
        "competition": m.competition if has and m else None,
        "intents": m.intents if has and m else [],
        "source": m.source if has and m else None,
        "metrics_updated_at": m.fetched_at if has and m else None,
    }


@router.delete("/{list_id}/items/{item_id}", status_code=204)
async def remove_item(list_id: uuid.UUID, item_id: uuid.UUID, db: DB, org: CurrentOrg) -> None:
    kl = await _get(db, org.id, list_id)
    item = await db.scalar(
        select(KeywordListItem).where(
            KeywordListItem.id == item_id, KeywordListItem.list_id == kl.id
        )
    )
    if item is None:
        raise AppError(404, "not_found", "Keyword not in this list")
    await db.delete(item)
    await db.commit()


@router.get("/{list_id}/export.csv", response_class=Response)
async def export_list(list_id: uuid.UUID, db: DB, org: CurrentOrg) -> Response:
    kl = await _get(db, org.id, list_id)
    await limits.consume(db, org, "exports_per_day")
    await db.commit()
    market = Market(kl.market)
    rows = [
        KeywordMetrics(
            keyword=i.keyword,
            market=market,
            volume=i.volume,
            kd=i.kd,
            cpc=i.cpc,
            competition=i.competition,
            intents=list(i.intents or []),
            source=i.source or "",
            fetched_at=i.metrics_updated_at or i.added_at,
        )
        for i in await _items(db, kl.id)
    ]
    return csv_response(rows, f"brandiz-list-{kl.name.replace(' ', '-')}.csv")
