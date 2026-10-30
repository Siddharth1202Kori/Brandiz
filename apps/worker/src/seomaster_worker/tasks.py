"""Celery tasks: thin wrappers. Async job logic lives in per-domain modules (keyword_jobs)."""

import asyncio
import logging
import time

from celery import Task
from redis import Redis

from seomaster_worker import keyword_jobs
from seomaster_worker.celery_app import app, settings

log = logging.getLogger(__name__)
HEARTBEAT_KEY = "worker:heartbeat"  # read by GET /healthz
COLLECT_FIRST_CHECK_S = 60  # Google Ads tasks usually finish within a few minutes
COLLECT_RETRY_S = 120
COLLECT_MAX_CHECKS = 30  # give up after ~1 hour; the batch re-queues them in 6 h


class BaseTask(Task):  # type: ignore[misc]
    """Retries transient infra errors with exponential backoff + jitter."""

    autoretry_for = (ConnectionError, TimeoutError)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 5


@app.task(base=BaseTask, name="seomaster_worker.tasks.heartbeat")
def heartbeat() -> float:
    now = time.time()
    with Redis.from_url(settings.redis_url) as redis:
        redis.set(HEARTBEAT_KEY, now, ex=3600)
    log.info("heartbeat")
    return now


# -- Phase 1: keywords ---------------------------------------------------------------------


@app.task(base=BaseTask, name="maintenance.refresh_stale_keywords")
def refresh_stale_keywords() -> int:
    async def run() -> int:
        async with keyword_jobs.runtime(settings) as rt:
            return await keyword_jobs.refresh_stale_keywords(rt)

    return asyncio.run(run())


@app.task(base=BaseTask, name="fetch.keyword_volume_batch")
def keyword_volume_batch() -> int:
    async def run() -> list[tuple[str, str]]:
        async with keyword_jobs.runtime(settings) as rt:
            return await keyword_jobs.queue_volume_batch(rt)

    queued = asyncio.run(run())
    for task_id, market in queued:
        keyword_volume_collect.apply_async(
            (task_id, market), countdown=COLLECT_FIRST_CHECK_S, queue="fetch"
        )
    return len(queued)


@app.task(
    base=BaseTask,
    bind=True,
    name="fetch.keyword_volume_collect",
    max_retries=COLLECT_MAX_CHECKS,
)
def keyword_volume_collect(self: Task, task_id: str, market: str) -> int:
    async def run() -> int | None:
        async with keyword_jobs.runtime(settings) as rt:
            return await keyword_jobs.collect_volume(rt, task_id, market)

    updated = asyncio.run(run())
    if updated is None:  # provider still working on it
        raise self.retry(countdown=COLLECT_RETRY_S)
    return updated
