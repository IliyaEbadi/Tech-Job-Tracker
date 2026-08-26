"""Data structures shared by every stage of the pipeline.

Two shapes exist on purpose:

* :class:`RawJob` is whatever a source could pull out of its API. Fields are
  loose strings because each board names things differently.
* :class:`JobPosting` is the cleaned, filtered record that gets written to
  ``data/jobs.json``. Every field is normalized and the ``job_id`` is
  deterministic, which is what makes day-to-day comparisons possible.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Fields compared when deciding whether an existing posting "materially
# changed". Deliberately excludes free text such as the summary, which some
# boards re-render slightly differently between runs.
MATERIAL_FIELDS: tuple[str, ...] = (
    "title",
    "company",
    "location",
    "url",
    "employment_type",
    "workplace_type",
    "category",
)


@dataclass(slots=True)
class RawJob:
    """An un-normalized posting exactly as a source read it."""

    title: str
    company: str
    location: str
    url: str
    source: str
    employment_type: str = ""
    workplace_type: str = ""
    posted_at: str = ""
    description: str = ""


@dataclass(slots=True)
class JobPosting:
    """A normalized posting, ready to be stored and reported on."""

    job_id: str
    title: str
    company: str
    location: str
    url: str
    source: str
    category: str
    employment_type: str = ""
    workplace_type: str = ""
    posted_at: str = ""
    first_seen: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict with a stable key order for JSON output."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobPosting:
        """Rebuild a posting from stored JSON, ignoring unknown keys."""
        known = set(cls.__slots__)
        payload = {key: value for key, value in data.items() if key in known}
        payload.setdefault("tags", [])
        return cls(**payload)

    def sort_key(self) -> tuple[str, str, str]:
        """Sort key used to keep ``data/jobs.json`` byte-stable between runs."""
        return (self.company.lower(), self.title.lower(), self.job_id)
