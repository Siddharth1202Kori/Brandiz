"""Builds the DAL and keyword provider from settings (used by API lifespan and worker jobs)."""

from decimal import Decimal

from redis.asyncio import Redis

from seomaster_core.config import Settings
from seomaster_providers.backends import (
    ClickHouseKeywordStore,
    ClickHouseLedger,
    ClickHouseWarmStore,
    ClientSource,
    RedisHotCache,
)
from seomaster_providers.dal import BudgetConfig, DataAccessLayer
from seomaster_providers.dataforseo import DataForSEOClient, DataForSEOKeywordProvider
from seomaster_providers.fake import FakeKeywordProvider
from seomaster_providers.interfaces import KeywordProvider
from seomaster_providers.keywords import KeywordService


def build_dal(settings: Settings, redis: Redis, clickhouse: ClientSource) -> DataAccessLayer:
    return DataAccessLayer(
        hot=RedisHotCache(redis),
        warm=ClickHouseWarmStore(clickhouse),
        ledger=ClickHouseLedger(clickhouse, wait=settings.app_env == "test"),
        budget=BudgetConfig(
            daily_global_usd=Decimal(str(settings.budget_daily_global_usd)),
            daily_org_usd=Decimal(str(settings.budget_daily_org_usd)),
        ),
    )


def build_keyword_provider(settings: Settings) -> KeywordProvider:
    """DataForSEO when credentials are set (and not forced fake), otherwise the free fake."""
    if settings.dataforseo_enabled and settings.app_env != "test":
        client = DataForSEOClient(
            settings.dataforseo_login,
            settings.dataforseo_password.get_secret_value(),
            base_url=settings.dataforseo_base_url,
        )
        return DataForSEOKeywordProvider(client)
    return FakeKeywordProvider()


async def close_provider(provider: KeywordProvider) -> None:
    if isinstance(provider, DataForSEOKeywordProvider):
        await provider.client.aclose()


def build_keyword_service(
    settings: Settings, redis: Redis, clickhouse: ClientSource, provider: KeywordProvider
) -> KeywordService:
    return KeywordService(
        provider=provider,
        dal=build_dal(settings, redis, clickhouse),
        store=ClickHouseKeywordStore(clickhouse),
    )
