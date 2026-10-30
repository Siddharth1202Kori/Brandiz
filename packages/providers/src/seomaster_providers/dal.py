"""Data Access Layer: the only path from a report to a paid provider.

Lookup order (doc 03 §4.4):
    1. hot cache (Redis / Upstash)          -> cached
    2. warm store (ClickHouse, not expired) -> cached, re-warms hot
    3. budget guard                         -> over cap: stale copy or BudgetExceededError
    4. single-flight lock                   -> concurrent identical misses share one fetch
    5. provider fetch -> warm + hot + spend counters
Every lookup writes one ledger row (hits included) so hit rate and cost per view are measurable.
Cache/ledger outages degrade to "miss" / "not logged" instead of failing the request.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol

from seomaster_core import timing

log = logging.getLogger(__name__)

Tier = Literal["hot", "warm", "provider", "stale"]


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DalRequest:
    key: str
    ttl: timedelta
    provider: str
    endpoint: str
    org_id: uuid.UUID | None = None


@dataclass(frozen=True)
class FetchResult:
    payload: Any  # JSON-serializable
    cost_usd: Decimal = Decimal(0)


@dataclass(frozen=True)
class StoredPayload:
    key: str
    provider: str
    endpoint: str
    payload: Any
    fetched_at: datetime
    expires_at: datetime

    def to_json(self) -> str:
        return json.dumps(
            {
                "key": self.key,
                "provider": self.provider,
                "endpoint": self.endpoint,
                "payload": self.payload,
                "fetched_at": self.fetched_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "StoredPayload":
        d = json.loads(raw)
        return cls(
            key=d["key"],
            provider=d["provider"],
            endpoint=d["endpoint"],
            payload=d["payload"],
            fetched_at=datetime.fromisoformat(d["fetched_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
        )


@dataclass(frozen=True)
class DalResult:
    payload: Any
    tier: Tier
    source: str
    fetched_at: datetime

    @property
    def cached(self) -> bool:
        return self.tier != "provider"

    @property
    def stale(self) -> bool:
        return self.tier == "stale"


@dataclass(frozen=True)
class LedgerEntry:
    created_at: datetime
    provider: str
    endpoint: str
    cache_key: str
    org_id: uuid.UUID | None
    cache_tier: Tier
    cost_usd: Decimal
    latency_ms: int


@dataclass(frozen=True)
class BudgetConfig:
    daily_global_usd: Decimal
    daily_org_usd: Decimal


class BudgetExceededError(Exception):
    def __init__(self, scope: str) -> None:
        super().__init__(f"daily provider budget exceeded ({scope})")
        self.scope = scope


class HotCache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_s: int) -> None: ...
    async def acquire(self, key: str, token: str, ttl_ms: int) -> bool: ...
    async def release(self, key: str, token: str) -> None: ...
    async def add_spend(self, scope: str, usd: Decimal) -> None: ...
    async def get_spend(self, scope: str) -> Decimal: ...


class WarmStore(Protocol):
    async def get(self, key: str, *, allow_expired: bool = False) -> StoredPayload | None: ...
    async def put(self, item: StoredPayload) -> None: ...


class Ledger(Protocol):
    async def record(self, entry: LedgerEntry) -> None: ...


@dataclass
class DataAccessLayer:
    hot: HotCache
    warm: WarmStore
    ledger: Ledger
    budget: BudgetConfig
    now: Callable[[], datetime] = utcnow
    lock_ttl_ms: int = 30_000
    lock_wait_s: float = 20.0
    poll_s: float = 0.05
    _background: set[asyncio.Task[None]] = field(default_factory=set)

    async def get(
        self,
        req: DalRequest,
        fetch: Callable[[], Awaitable[FetchResult]],
        *,
        force: bool = False,
    ) -> DalResult:
        """`force=True` skips both cache tiers (scheduled refresh); budget + lock still apply."""
        t0 = time.perf_counter()

        if not force:
            if item := await self._hot_get(req.key):
                return await self._done(req, item, "hot", t0)

            if (item := await self._warm_get(req.key)) is not None:
                await self._hot_set(item)
                return await self._done(req, item, "warm", t0)

        try:
            await self._check_budget(req.org_id)
        except BudgetExceededError:
            stale = await self._warm_get(req.key, allow_expired=True)
            if stale is None:
                raise
            return await self._done(req, stale, "stale", t0)

        token = uuid.uuid4().hex
        if not await self._acquire(req.key, token):
            if not force and (item := await self._wait_for_peer(req.key)):
                return await self._done(req, item, "hot", t0)
            log.warning("single-flight wait timed out, fetching anyway: %s", req.key)

        try:
            with timing.measure("provider"):
                result = await fetch()
            fetched_at = self.now()
            item = StoredPayload(
                key=req.key,
                provider=req.provider,
                endpoint=req.endpoint,
                payload=result.payload,
                fetched_at=fetched_at,
                expires_at=fetched_at + req.ttl,
            )
            await self._warm_put(item)
            await self._hot_set(item)
            await self._add_spend(req.org_id, result.cost_usd)
            return await self._done(req, item, "provider", t0, cost=result.cost_usd)
        finally:
            await self._release(req.key, token)

    # -- budget -----------------------------------------------------------------

    def _scopes(self, org_id: uuid.UUID | None) -> list[tuple[str, Decimal]]:
        day = self.now().strftime("%Y-%m-%d")
        scopes = [(f"budget:{day}:global", self.budget.daily_global_usd)]
        if org_id is not None:
            scopes.append((f"budget:{day}:org:{org_id}", self.budget.daily_org_usd))
        return scopes

    async def _check_budget(self, org_id: uuid.UUID | None) -> None:
        for scope, cap in self._scopes(org_id):
            try:
                spent = await self.hot.get_spend(scope)
            except Exception:
                log.exception("budget read failed; allowing call")
                continue
            if spent >= cap:
                raise BudgetExceededError(scope.split(":", 2)[2])

    async def _add_spend(self, org_id: uuid.UUID | None, usd: Decimal) -> None:
        if usd <= 0:
            return
        for scope, _ in self._scopes(org_id):
            try:
                await self.hot.add_spend(scope, usd)
            except Exception:
                log.exception("budget write failed")

    # -- cache tiers (failures degrade to miss) ----------------------------------

    async def _hot_get(self, key: str) -> StoredPayload | None:
        try:
            with timing.measure("cache"):
                raw = await self.hot.get(f"dal:{key}")
        except Exception:
            log.exception("hot cache get failed")
            return None
        return StoredPayload.from_json(raw) if raw else None

    async def _hot_set(self, item: StoredPayload) -> None:
        ttl_s = int((item.expires_at - self.now()).total_seconds())
        if ttl_s <= 0:
            return
        try:
            await self.hot.set(f"dal:{item.key}", item.to_json(), ttl_s)
        except Exception:
            log.exception("hot cache set failed")

    async def _warm_get(self, key: str, *, allow_expired: bool = False) -> StoredPayload | None:
        try:
            with timing.measure("store"):
                item = await self.warm.get(key, allow_expired=allow_expired)
        except Exception:
            log.exception("warm store get failed")
            return None
        if item and not allow_expired and item.expires_at <= self.now():
            return None
        return item

    async def _warm_put(self, item: StoredPayload) -> None:
        try:
            await self.warm.put(item)
        except Exception:
            log.exception("warm store put failed")

    # -- single-flight -------------------------------------------------------------

    async def _acquire(self, key: str, token: str) -> bool:
        try:
            return await self.hot.acquire(f"dal:lock:{key}", token, self.lock_ttl_ms)
        except Exception:
            log.exception("lock acquire failed; proceeding without lock")
            return True

    async def _release(self, key: str, token: str) -> None:
        try:
            await self.hot.release(f"dal:lock:{key}", token)
        except Exception:
            log.exception("lock release failed")

    async def _wait_for_peer(self, key: str) -> StoredPayload | None:
        deadline = time.monotonic() + self.lock_wait_s
        while time.monotonic() < deadline:
            await asyncio.sleep(self.poll_s)
            if item := await self._hot_get(key):
                return item
        return None

    # -- ledger ---------------------------------------------------------------------

    async def _done(
        self,
        req: DalRequest,
        item: StoredPayload,
        tier: Tier,
        t0: float,
        *,
        cost: Decimal = Decimal(0),
    ) -> DalResult:
        entry = LedgerEntry(
            created_at=self.now(),
            provider=req.provider,
            endpoint=req.endpoint,
            cache_key=req.key,
            org_id=req.org_id,
            cache_tier=tier,
            cost_usd=cost,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        try:
            await self.ledger.record(entry)
        except Exception:
            log.exception("ledger write failed")
        return DalResult(
            payload=item.payload, tier=tier, source=item.provider, fetched_at=item.fetched_at
        )
