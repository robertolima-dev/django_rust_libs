import logging
import os
import sys

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger("apps.core")

# Management commands during which the scheduler must NOT start.
_BLOCKED_COMMANDS = {
    "migrate",
    "makemigrations",
    "collectstatic",
    "test",
    "shell",
    "shell_plus",
    "createsuperuser",
    "loaddata",
    "dumpdata",
    "check",
}


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        if not getattr(settings, "SCHEDULER_AUTOSTART", False):
            return
        if any(cmd in sys.argv for cmd in _BLOCKED_COMMANDS):
            return
        # With runserver's autoreloader, ready() runs twice; only start in the
        # child process (RUN_MAIN == "true").
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return

        from rust_py_scheduler.django import start_in_background

        from .scheduler import register_jobs, scheduler

        register_jobs()
        start_in_background(scheduler)
        logger.info("Background scheduler started with %d job(s).", len(scheduler.list_jobs()))
