"""A global cap on how many demo runs everyone combined may start in a day.

The demo's run endpoints are unauthenticated by design, and every run they
accept spends real Sarvam and Gemini credit. The site is only meant for the
SIH judges, so the budget is sized for them rather than for the public: a
small number of runs per calendar day across all visitors, after which the
endpoints refuse with a 429 and the site falls back to a recorded run.

The day is the Indian calendar day (IST, UTC+05:30, no daylight saving), so
the allowance resets at midnight for the people who will be using it.

The count is kept in process memory and, when DEMO_LIMIT_STATE_PATH is set,
mirrored to a small JSON file so a restart does not hand out a fresh day's
allowance. That only holds if the file sits on storage that outlives the
container; on the image's own ephemeral disk a scale-to-zero still resets it.
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_lock = threading.Lock()
_day: Optional[str] = None
_count = 0
_loaded = False


def _now() -> datetime:
    return datetime.now(IST)


def _state_path() -> Optional[Path]:
    path = settings.DEMO_LIMIT_STATE_PATH
    return Path(path) if path else None


def _load() -> Tuple[Optional[str], int]:
    path = _state_path()
    if path is None or not path.exists():
        return None, 0
    try:
        data = json.loads(path.read_text())
        return str(data["day"]), int(data["count"])
    except (OSError, ValueError, KeyError, TypeError):
        # A corrupt file must not take the demo down; start the day over.
        logger.warning("demo limit state at %s is unreadable; ignoring it", path)
        return None, 0


def _save(day: str, count: int) -> None:
    path = _state_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps({"day": day, "count": count}))
        os.replace(tmp, path)
    except OSError:
        logger.exception("could not persist demo limit state to %s", path)


def _seconds_until_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


def demo_rate_limit() -> None:
    """Refuse a run once today's shared allowance is spent."""
    global _day, _count, _loaded

    limit = settings.DEMO_MAX_RUNS_PER_DAY
    if not settings.DEMO_MODE or limit <= 0:
        return

    now = _now()
    today = now.date().isoformat()

    with _lock:
        if not _loaded:
            _day, _count = _load()
            _loaded = True

        if _day != today:
            _day, _count = today, 0

        if _count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"This demo allows {limit} live runs a day in total. "
                    "Today's are used up; it resets at midnight IST."
                ),
                headers={"Retry-After": str(_seconds_until_midnight(now))},
            )

        _count += 1
        _save(_day, _count)


def reset_demo_limit() -> None:
    """Forget today's count. For tests."""
    global _day, _count, _loaded
    with _lock:
        _day, _count, _loaded = None, 0, True
