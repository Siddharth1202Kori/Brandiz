"""ClickHouse client factory + ordered SQL migration runner.

Usage: `uv run python -m seomaster_db.clickhouse` (applies pending files in `sql/`).
"""

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from seomaster_core.config import Settings, get_settings

log = logging.getLogger(__name__)
SQL_DIR = Path(__file__).parent / "sql"


async def make_client(
    settings: Settings | None = None, *, database: str | None = None
) -> AsyncClient:
    s = settings or get_settings()
    url = urlsplit(s.clickhouse_url)
    return await clickhouse_connect.get_async_client(
        host=url.hostname or "localhost",
        port=url.port or (8443 if url.scheme == "https" else 8123),
        secure=url.scheme == "https",
        username=s.clickhouse_user,
        password=s.clickhouse_password.get_secret_value(),
        database=database or s.clickhouse_database,
        connect_timeout=5,
        send_receive_timeout=30,
    )


class ClickHouseHandle:
    """Lazily connects on first use, so the API boots even while ClickHouse is down."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def client(self) -> AsyncClient:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = await make_client(self._settings)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


def _statements(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


async def migrate(settings: Settings | None = None) -> list[str]:
    s = settings or get_settings()
    bootstrap = await make_client(s, database="default")
    await bootstrap.command(f"CREATE DATABASE IF NOT EXISTS {s.clickhouse_database}")
    client = await make_client(s)
    await client.command(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(name String, applied_at DateTime DEFAULT now()) ENGINE = MergeTree ORDER BY name"
    )
    done = {
        row[0] for row in (await client.query("SELECT name FROM schema_migrations")).result_rows
    }
    applied: list[str] = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        if path.name in done:
            continue
        for stmt in _statements(path.read_text()):
            await client.command(stmt)
        await client.insert("schema_migrations", [[path.name]], column_names=["name"])
        applied.append(path.name)
        log.info("clickhouse migration applied: %s", path.name)
    await bootstrap.close()
    await client.close()
    return applied
