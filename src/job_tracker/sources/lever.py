"""Lever public postings API.

Lever exposes each customer's open roles as JSON at
``https://api.lever.co/v0/postings/<company>?mode=json``. It is the documented
public feed behind ``jobs.lever.co`` pages and needs no authentication.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..models import RawJob
from .base import JobSource, SourceError, board_entries

API_TEMPLATE = "https://api.lever.co/v0/postings/{token}"


def epoch_ms_to_date(value: Any) -> str:
    """Convert Lever's millisecond timestamp into ``YYYY-MM-DD``."""
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return ""
    if milliseconds <= 0:
        return ""
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC).strftime("%Y-%m-%d")


class LeverSource(JobSource):
    """Read postings from one or more Lever job boards."""

    type_name = "lever"

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        companies = board_entries(self.options, "companies")
        if not companies:
            self.log.warning("no_companies_configured source=%s", self.name)
        for token, company in companies:
            try:
                payload = self.client.get_json(
                    API_TEMPLATE.format(token=token), params={"mode": "json"}
                )
            except SourceError as error:
                self.log.warning("board_failed board=%s error=%s", token, error)
                continue
            board_jobs = self._parse(payload, company=company)
            self.log.info("board_collected board=%s jobs=%d", token, len(board_jobs))
            jobs.extend(board_jobs)
        return jobs

    def _parse(self, payload: Any, *, company: str) -> list[RawJob]:
        """Convert a Lever postings response into raw postings."""
        if not isinstance(payload, list):
            return []
        jobs: list[RawJob] = []
        for record in payload:
            if not isinstance(record, dict):
                continue
            categories = record.get("categories") or {}
            if not isinstance(categories, dict):
                categories = {}
            locations = categories.get("allLocations") or []
            location = categories.get("location") or (
                "; ".join(str(item) for item in locations) if isinstance(locations, list) else ""
            )
            description = (
                record.get("descriptionPlain")
                or record.get("description")
                or record.get("descriptionBody")
                or ""
            )
            jobs.append(
                RawJob(
                    title=str(record.get("text") or ""),
                    company=company,
                    location=str(location or ""),
                    url=str(record.get("hostedUrl") or record.get("applyUrl") or ""),
                    source=self.name,
                    employment_type=str(categories.get("commitment") or ""),
                    workplace_type=str(record.get("workplaceType") or ""),
                    posted_at=epoch_ms_to_date(record.get("createdAt")),
                    description=str(description),
                )
            )
        return jobs
