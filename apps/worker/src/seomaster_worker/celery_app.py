"""Celery app.

Local dev (macOS) uses `--pool=threads`: the default prefork pool fails there. Linux prod
(Oracle VM) can use prefork; tasks are I/O-bound so threads are fine either way.

Worker: `celery -A seomaster_worker.celery_app worker -Q maintenance,rank,audit,gsc,fetch`

Broker = VM Redis in prod, never Upstash: Celery polls the broker constantly (doc 03 §14.2).
No result backend: task status lives in Postgres rows (audit_runs, gsc_connections, ...).
"""

from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_ready
from kombu import Queue

from seomaster_core.config import get_settings
from seomaster_core.observability import setup_logging, setup_tracing

QUEUES = ("maintenance", "rank", "audit", "gsc", "fetch")
HEARTBEAT_EVERY_S = 300.0  # 288 Redis writes/day — cheap even on Upstash's free tier

settings = get_settings()
app = Celery("seomaster", broker=settings.celery_broker_url, include=["seomaster_worker.tasks"])
app.conf.update(
    task_queues=[Queue(q) for q in QUEUES],
    task_default_queue="maintenance",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    worker_hijack_root_logger=False,
    timezone="UTC",
    beat_schedule={
        "heartbeat": {"task": "seomaster_worker.tasks.heartbeat", "schedule": HEARTBEAT_EVERY_S},
        "refresh-stale-keywords": {
            "task": "maintenance.refresh_stale_keywords",
            "schedule": crontab(hour=21, minute=30),  # 03:00 IST, quiet hours for both markets
            "options": {"queue": "maintenance"},
        },
        "keyword-volume-batch": {
            "task": "fetch.keyword_volume_batch",
            "schedule": 15 * 60.0,
            "options": {"queue": "fetch"},
        },
    },
)


@worker_process_init.connect
def _init_worker(**_: Any) -> None:
    setup_logging(json_logs=settings.app_env != "dev")
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn, environment=settings.app_env, send_default_pii=False
        )
    if setup_tracing("seomaster-worker", settings.otel_exporter_otlp_endpoint):
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()


@worker_ready.connect
def _heartbeat_on_start(**_: Any) -> None:
    """Beat's first interval run is 5 min after start; report liveness immediately."""
    app.send_task("seomaster_worker.tasks.heartbeat")
