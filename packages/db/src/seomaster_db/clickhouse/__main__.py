import asyncio

from seomaster_db.clickhouse import migrate

print("applied:", asyncio.run(migrate()) or "nothing (up to date)")
