"""Test settings: inherit everything but run on an in-memory SQLite database."""

import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Don't spin up the background scheduler during tests.
SCHEDULER_AUTOSTART = False

# Keep the audit trail out of the project tree during tests.
AUDIT_FILE_PATH = str(Path(tempfile.gettempdir()) / "audit_test.jsonl")

# Generous limits so functional tests never trip the limiter; the dedicated
# rate-limit test overrides these.
RATE_LIMITS = {
    "default": {"limit": 1000, "window_seconds": 60},
    "login": {"limit": 1000, "window_seconds": 60},
    "register": {"limit": 1000, "window_seconds": 60},
    "forgot_password": {"limit": 1000, "window_seconds": 60},
}
