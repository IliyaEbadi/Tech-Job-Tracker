"""Shared test fixtures.

Every test in this suite runs offline. Sources are exercised through
:class:`FakeHttpClient`, which replays the JSON documents in ``fixtures/``
instead of calling a real job board.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from job_tracker.config import Settings, load_settings
from job_tracker.models import JobPosting
from job_tracker.sources.base import SourceError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Read a JSON fixture from ``tests/fixtures``."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeHttpClient:
    """Stand-in for :class:`job_tracker.sources.base.HttpClient`.

    ``responses`` maps a URL fragment to either a payload or an exception to
    raise, which is how failure handling is tested without a network.
    """

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(url)
        for fragment, payload in self.responses.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise SourceError(f"no fake response registered for {url}")


@pytest.fixture(autouse=True)
def reset_logging():
    """Detach log handlers between tests.

    The CLI attaches a handler bound to pytest's captured stderr; leaving it
    installed would make later tests log to a closed stream.
    """
    yield
    logging.getLogger().handlers.clear()


@pytest.fixture(scope="session")
def settings() -> Settings:
    """The real project configuration, so tests cover the shipped keywords."""
    return load_settings(PROJECT_ROOT / "config" / "settings.yaml")


@pytest.fixture
def fake_client():
    """Factory fixture: ``fake_client({"greenhouse.io": payload})``."""
    return FakeHttpClient


def make_posting(**overrides: Any) -> JobPosting:
    """Build a JobPosting with sensible defaults for change-detection tests."""
    values: dict[str, Any] = {
        "job_id": "aaaaaaaaaaaa",
        "title": "Junior Software Developer",
        "company": "Example Labs",
        "location": "Toronto, ON",
        "url": "https://example.com/jobs/1",
        "source": "greenhouse",
        "category": "Software Development",
        "employment_type": "Full-time",
        "workplace_type": "Hybrid",
        "posted_at": "2026-08-01",
        "first_seen": "2026-08-01",
        "tags": ["software developer"],
        "summary": "Build things.",
    }
    values.update(overrides)
    return JobPosting(**values)
