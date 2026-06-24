"""Helpers that bridge rust-py-rate-limit into DRF views."""

from rest_framework.exceptions import Throttled

from .services import get_limiter


def client_ip(request) -> str:
    """Best-effort client IP, honoring a single proxy hop."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def enforce(name: str, key: str) -> dict:
    """
    Consume one token from the ``name`` bucket for ``key``.

    Raises DRF's ``Throttled`` (HTTP 429 + Retry-After) when the limit is hit.
    Returns the limiter's status dict otherwise.
    """
    result = get_limiter(name).check(key)
    if not result["allowed"]:
        raise Throttled(wait=result["retry_after_seconds"])
    return result
