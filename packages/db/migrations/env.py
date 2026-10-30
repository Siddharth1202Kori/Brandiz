import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from seomaster_core.config import get_settings
from seomaster_db import models  # noqa: F401  (registers tables)
from seomaster_db.base import Base, make_engine

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _main() -> None:
    url = context.config.attributes.get("database_url") or get_settings().database_url
    engine = make_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
        await conn.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline mode not supported")
asyncio.run(_main())
