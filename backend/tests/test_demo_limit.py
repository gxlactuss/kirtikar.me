"""The demo's shared daily cap on live runs."""
import json
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.core import demo_limit
from app.core.config import settings


@pytest.fixture(autouse=True)
def demo_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_MAX_RUNS_PER_DAY", 10)
    monkeypatch.setattr(settings, "DEMO_LIMIT_STATE_PATH", str(tmp_path / "limit.json"))
    demo_limit.reset_demo_limit()
    yield tmp_path / "limit.json"
    demo_limit.reset_demo_limit()


def _at(monkeypatch, iso: str) -> None:
    monkeypatch.setattr(demo_limit, "_now", lambda: datetime.fromisoformat(iso))


def test_eleventh_run_of_the_day_is_refused(monkeypatch):
    _at(monkeypatch, "2026-10-05T10:00:00+05:30")
    for _ in range(10):
        demo_limit.demo_rate_limit()
    with pytest.raises(HTTPException) as refused:
        demo_limit.demo_rate_limit()
    assert refused.value.status_code == 429
    assert refused.value.headers["Retry-After"] == str(14 * 3600)


def test_allowance_resets_at_ist_midnight(monkeypatch):
    _at(monkeypatch, "2026-10-05T23:59:00+05:30")
    for _ in range(10):
        demo_limit.demo_rate_limit()
    _at(monkeypatch, "2026-10-06T00:00:01+05:30")
    demo_limit.demo_rate_limit()


def test_count_survives_a_restart(monkeypatch, demo_cap):
    _at(monkeypatch, "2026-10-05T10:00:00+05:30")
    for _ in range(10):
        demo_limit.demo_rate_limit()
    assert json.loads(demo_cap.read_text()) == {"day": "2026-10-05", "count": 10}

    monkeypatch.setattr(demo_limit, "_loaded", False)
    monkeypatch.setattr(demo_limit, "_count", 0)
    with pytest.raises(HTTPException):
        demo_limit.demo_rate_limit()


def test_no_cap_outside_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    for _ in range(20):
        demo_limit.demo_rate_limit()
