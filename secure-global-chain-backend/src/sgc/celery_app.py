"""Celery application (broker/result backend = Redis).

Queues mirror AGENTS_AND_COMPUTE.md §1 (ingest, evidence, optimize, agents,
audit). Task modules and the beat schedule (executive read-model refresh, device
re-attestation, cold-chain sweeps, Neo4j reconciliation) are added as those
workers are wired; this is the minimal app so the ``worker`` and ``beat`` compose
services start cleanly.
"""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "sgc",
    broker=settings.broker_url,
    backend=settings.result_backend,
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    timezone="UTC",
    enable_utc=True,
    # Beat schedule entries are registered here as periodic jobs are built.
    beat_schedule={},
)


@celery_app.task(name="sgc.ping")
def ping() -> str:
    """Trivial liveness task."""
    return "pong"
