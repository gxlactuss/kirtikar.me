"""A per-address cap on how many demo runs one visitor may start.

The demo's create endpoint is unauthenticated by design, and every listing it
accepts goes on to spend real Sarvam and Gemini credit. One script pointed at
it could drain a month's quota in an afternoon and leave the judges looking at
a fallback. This is the cheapest thing that prevents that without putting a
login in front of a demo whose whole point is that there isn't one.

It is a sliding window held in process memory. That is the right size for a
single-container demo: it costs nothing, it needs no Redis, and the worst case
when the container restarts is that a handful of visitors get their allowance
back. It is not a general rate limiter and should not be mistaken for one.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.config import settings

WINDOW_SECONDS = 3600

_hits: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _client_key(request: Request) -> str:
    """The visitor's address, as seen from behind the platform's proxy.

    A Space sits behind a reverse proxy, so `request.client.host` is the
    proxy's address and would put every visitor in the world into one bucket.
    The first entry of X-Forwarded-For is the original client. It is trivially
    spoofable — which is acceptable here, because the cap protects an API
    budget rather than anything a forged header could reach.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def demo_rate_limit(request: Request) -> None:
    """Refuse a create once this address has had its hour's worth."""
    limit = settings.DEMO_MAX_RUNS_PER_HOUR
    if not settings.DEMO_MODE or limit <= 0:
        return

    key = _client_key(request)
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS

    with _lock:
        seen = _hits[key]
        while seen and seen[0] < cutoff:
            seen.popleft()

        if len(seen) >= limit:
            retry_after = int(seen[0] - cutoff) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "This demo allows "
                    f"{limit} listings an hour from one address. "
                    "Please try again shortly."
                ),
                headers={"Retry-After": str(retry_after)},
            )

        seen.append(now)

        # Addresses that stopped calling should not accumulate forever in a
        # process that stays up for a month.
        if len(_hits) > 4096:
            for stale in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
                del _hits[stale]
