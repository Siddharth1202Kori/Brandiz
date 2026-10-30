import os
import time

import pytest
from redis import Redis

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")


@pytest.mark.integration
def test_heartbeat_writes_timestamp() -> None:
    from seomaster_worker.tasks import HEARTBEAT_KEY, heartbeat, settings

    before = time.time()
    heartbeat.apply().get()
    with Redis.from_url(settings.redis_url) as redis:
        value = float(redis.get(HEARTBEAT_KEY) or 0)
    assert value >= before
