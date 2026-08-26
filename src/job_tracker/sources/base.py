"""The small abstraction every job source implements.

A source knows one thing: how to turn its own API response into a list of
:class:`~job_tracker.models.RawJob` records. Filtering, normalization and
change detection happen later, which is why adding a new board only means
adding one class and one entry in ``config/settings.yaml``.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import requests

from ..config import HttpSettings
from ..models import RawJob

logger = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Raised when a source cannot produce usable data."""


class HttpClient:
    """A deliberately small, polite HTTP client.

    It identifies itself with a User-Agent, always uses a timeout, retries a
    couple of times on transient failures, and pauses between requests so the
    tracker never hammers a public job board.
    """

    def __init__(self, settings: HttpSettings | None = None) -> None:
        self.settings = settings or HttpSettings()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.settings.user_agent,
                "Accept": "application/json",
            }
        )
        self._last_request_at = 0.0

    def _wait_for_turn(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.settings.delay_seconds - elapsed
        if self._last_request_at and remaining > 0:
            time.sleep(remaining)

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET a URL and return the decoded JSON body.

        Raises :class:`SourceError` when every attempt fails.
        """
        attempts = max(1, self.settings.max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            self._wait_for_turn()
            try:
                response = self.session.get(
                    url, params=params, timeout=self.settings.timeout_seconds
                )
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                last_error = error
                logger.warning(
                    "http_request_failed url=%s attempt=%d/%d error=%s",
                    url,
                    attempt,
                    attempts,
                    error,
                )
                if attempt < attempts:
                    time.sleep(min(2.0 * attempt, 5.0))
            finally:
                self._last_request_at = time.monotonic()
        raise SourceError(f"request failed for {url}: {last_error}")


def display_name(token: str) -> str:
    """Turn a board token into a readable company name (``knix`` -> ``Knix``)."""
    return token.replace("-", " ").replace("_", " ").strip().title()


def board_entries(options: dict[str, Any], key: str) -> list[tuple[str, str]]:
    """Read a list of boards from a source's options.

    Entries may be a plain token (``- knix``) or a mapping that overrides the
    company name (``- {token: knix, company: "Knix Wear"}``).
    """
    entries: list[tuple[str, str]] = []
    for entry in options.get(key) or []:
        if isinstance(entry, dict):
            token = str(entry.get("token", "")).strip()
            company = str(entry.get("company") or display_name(token)).strip()
        else:
            token = str(entry).strip()
            company = display_name(token)
        if token:
            entries.append((token, company))
    return entries


class JobSource(ABC):
    """Base class for every source."""

    #: Value used in ``config/settings.yaml`` under ``type:``.
    type_name: ClassVar[str] = ""

    def __init__(self, name: str, options: dict[str, Any], client: HttpClient) -> None:
        self.name = name
        self.options = options
        self.client = client
        self.log = logging.getLogger(f"job_tracker.sources.{name}")

    @abstractmethod
    def fetch(self) -> list[RawJob]:
        """Return every posting this source can currently see."""

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<{type(self).__name__} name={self.name!r}>"
