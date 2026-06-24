"""
Background scheduler (rust-py-scheduler) for recurring maintenance jobs.

Jobs registered here run on a dedicated Rust-driven OS thread, started from
``CoreConfig.ready()`` via :func:`rust_py_scheduler.django.start_in_background`.
"""

import logging

from rust_py_scheduler import Scheduler

from . import services

logger = logging.getLogger("apps.core.scheduler")

scheduler = Scheduler()


def cleanup_expired() -> None:
    """Evict expired cache entries and stale rate-limit keys."""
    removed_cache = services.cache.cleanup_expired()
    removed_keys = sum(limiter.cleanup_expired() for limiter in services.all_limiters())
    logger.info(
        "scheduler.cleanup removed_cache=%s removed_rate_keys=%s",
        removed_cache,
        removed_keys,
    )


def verify_audit_chain() -> None:
    """Daily integrity check of the hash-chained audit log."""
    result = services.audit.verify()
    if result.get("valid"):
        logger.info(
            "scheduler.audit_verify ok total_events=%s", result.get("total_events")
        )
    else:
        logger.error("scheduler.audit_verify FAILED result=%s", result)


def register_jobs() -> None:
    """Idempotently register the recurring jobs."""
    if scheduler.list_jobs():
        return
    scheduler.every("10m", cleanup_expired, max_retries=2)
    scheduler.cron("0 3 * * *", verify_audit_chain, max_retries=1)
