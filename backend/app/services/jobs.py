from __future__ import annotations

from fastapi import BackgroundTasks

from app.core.config import get_settings
from app.workers.scraper import run_scraper_job_sync


def enqueue_job(background_tasks: BackgroundTasks | None, job_id: int) -> dict[str, str]:
    settings = get_settings()
    if settings.redis_url:
        from redis import Redis
        from rq import Queue

        queue = Queue(settings.rq_queue_name, connection=Redis.from_url(settings.redis_url))
        queue.enqueue("app.workers.scraper.run_scraper_job_sync", job_id, job_timeout=settings.job_timeout_seconds)
        return {"mode": "rq"}

    if background_tasks is None:
        raise RuntimeError("BackgroundTasks is required when Redis is not configured")

    background_tasks.add_task(run_scraper_job_sync, job_id)
    return {"mode": "background"}
