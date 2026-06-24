"""
Shared singletons for the Rust-backed integrations.

These objects are process-wide and thread-safe (the heavy lifting happens in
Rust), so we instantiate them once and reuse them across the whole app.
"""

from django.conf import settings
from rust_py_audit import AuditLogger
from rust_py_cache import Cache
from rust_py_rate_limit import RateLimiter

# --------------------------------------------------------------------------- #
# rust-py-cache — in-process cache (used to cache /me responses, memoize, etc.)
# --------------------------------------------------------------------------- #
cache = Cache()


def user_cache_key(user_id) -> str:
    return f"user:{user_id}"


def invalidate_user(user_id) -> None:
    """Drop the cached representation of a user (after a profile/password change)."""
    cache.delete(user_cache_key(user_id))


# --------------------------------------------------------------------------- #
# rust-py-audit — tamper-evident, hash-chained audit log
# --------------------------------------------------------------------------- #
audit = AuditLogger(
    app_name=settings.AUDIT_APP_NAME,
    file_path=settings.AUDIT_FILE_PATH,
)


# --------------------------------------------------------------------------- #
# rust-py-rate-limit — sliding-window limiters, one per logical bucket
# --------------------------------------------------------------------------- #
# Keyed by (name, limit, window) so that overriding RATE_LIMITS in tests yields
# a fresh limiter instead of reusing a stale one.
_limiters: dict[tuple, RateLimiter] = {}


def get_limiter(name: str) -> RateLimiter:
    conf = settings.RATE_LIMITS.get(name, settings.RATE_LIMITS["default"])
    key = (name, conf["limit"], conf["window_seconds"])
    limiter = _limiters.get(key)
    if limiter is None:
        limiter = RateLimiter(limit=conf["limit"], window_seconds=conf["window_seconds"])
        _limiters[key] = limiter
    return limiter


def all_limiters() -> list[RateLimiter]:
    return list(_limiters.values())


def reset_limiters() -> None:
    """Clear every limiter's state (used by the test suite)."""
    for limiter in _limiters.values():
        limiter.clear()
