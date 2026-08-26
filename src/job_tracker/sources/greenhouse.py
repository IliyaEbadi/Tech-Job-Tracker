"""Greenhouse public job-board API.

Greenhouse publishes every customer's board as read-only JSON at
``https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs``. No key, no
login and no scraping are involved - this is the endpoint the companies' own
careers pages call.
"""

from __future__ import annotations

from typing import Any

from ..models import RawJob
from .base import JobSource, SourceError, board_entries

API_TEMPLATE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


class GreenhouseSource(JobSource):
    """Read postings from one or more Greenhouse boards."""

    type_name = "greenhouse"

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        boards = board_entries(self.options, "boards")
        if not boards:
            self.log.warning("no_boards_configured source=%s", self.name)
        for token, company in boards:
            try:
                payload = self.client.get_json(
                    API_TEMPLATE.format(token=token), params={"content": "true"}
                )
            except SourceError as error:
                # One dead board must not cost us the other boards.
                self.log.warning("board_failed board=%s error=%s", token, error)
                continue
            board_jobs = self._parse(payload, fallback_company=company)
            self.log.info("board_collected board=%s jobs=%d", token, len(board_jobs))
            jobs.extend(board_jobs)
        return jobs

    def _parse(self, payload: Any, *, fallback_company: str) -> list[RawJob]:
        """Convert a Greenhouse board response into raw postings."""
        records = payload.get("jobs", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        jobs: list[RawJob] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            location = record.get("location") or {}
            jobs.append(
                RawJob(
                    title=str(record.get("title") or ""),
                    company=str(record.get("company_name") or fallback_company),
                    location=str(location.get("name") or "") if isinstance(location, dict) else "",
                    url=str(record.get("absolute_url") or ""),
                    source=self.name,
                    posted_at=str(record.get("first_published") or record.get("updated_at") or ""),
                    description=str(record.get("content") or ""),
                )
            )
        return jobs
