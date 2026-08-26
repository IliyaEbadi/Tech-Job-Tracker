"""Ashby public job-board API.

Ashby publishes each customer's board at
``https://api.ashbyhq.com/posting-api/job-board/<org>``. Like the other two
sources it is a public, documented, unauthenticated read-only endpoint.
"""

from __future__ import annotations

from typing import Any

from ..models import RawJob
from .base import JobSource, SourceError, board_entries

API_TEMPLATE = "https://api.ashbyhq.com/posting-api/job-board/{token}"


class AshbySource(JobSource):
    """Read postings from one or more Ashby job boards."""

    type_name = "ashby"

    def fetch(self) -> list[RawJob]:
        jobs: list[RawJob] = []
        boards = board_entries(self.options, "boards")
        if not boards:
            self.log.warning("no_boards_configured source=%s", self.name)
        for token, company in boards:
            try:
                payload = self.client.get_json(API_TEMPLATE.format(token=token))
            except SourceError as error:
                self.log.warning("board_failed board=%s error=%s", token, error)
                continue
            board_jobs = self._parse(payload, company=company)
            self.log.info("board_collected board=%s jobs=%d", token, len(board_jobs))
            jobs.extend(board_jobs)
        return jobs

    def _parse(self, payload: Any, *, company: str) -> list[RawJob]:
        """Convert an Ashby board response into raw postings."""
        records = payload.get("jobs", []) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        jobs: list[RawJob] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            # Ashby keeps unlisted drafts in the same feed.
            if record.get("isListed") is False:
                continue
            jobs.append(
                RawJob(
                    title=str(record.get("title") or ""),
                    company=str(record.get("organizationName") or company),
                    location=str(record.get("location") or ""),
                    url=str(record.get("jobUrl") or record.get("applyUrl") or ""),
                    source=self.name,
                    employment_type=str(record.get("employmentType") or ""),
                    workplace_type=str(record.get("workplaceType") or ""),
                    posted_at=str(record.get("publishedAt") or ""),
                    description=str(record.get("descriptionPlain") or ""),
                )
            )
        return jobs
