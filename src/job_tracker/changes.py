"""Comparing yesterday's dataset with today's.

The tracker only has something to say when the job market moved, so every run
diffs the freshly collected postings against the dataset already committed in
the repository. The diff is what drives the report - and what decides whether
the automated workflow commits anything at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import MATERIAL_FIELDS, JobPosting


@dataclass(slots=True)
class ChangedJob:
    """One posting that still exists but whose details were edited."""

    before: JobPosting
    after: JobPosting
    fields: list[str]

    def describe(self) -> str:
        """Human-readable summary such as ``location: Toronto -> Remote``."""
        parts = [
            f"{name}: {getattr(self.before, name) or '-'} -> {getattr(self.after, name) or '-'}"
            for name in self.fields
        ]
        return "; ".join(parts)


@dataclass(slots=True)
class ChangeSet:
    """The difference between the previous and the current dataset."""

    added: list[JobPosting] = field(default_factory=list)
    removed: list[JobPosting] = field(default_factory=list)
    changed: list[ChangedJob] = field(default_factory=list)
    unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        """True when at least one posting was added, removed or edited."""
        return bool(self.added or self.removed or self.changed)

    def counts(self) -> dict[str, int]:
        """Compact counts, used in the summary JSON and log output."""
        return {
            "added": len(self.added),
            "removed": len(self.removed),
            "changed": len(self.changed),
            "unchanged": self.unchanged,
        }


def _index(postings: list[JobPosting]) -> dict[str, JobPosting]:
    return {posting.job_id: posting for posting in postings}


def material_differences(before: JobPosting, after: JobPosting) -> list[str]:
    """Return the names of the meaningful fields that differ between two records.

    Only the fields in :data:`job_tracker.models.MATERIAL_FIELDS` are compared.
    Free text such as the summary is ignored on purpose: boards re-render it
    slightly differently from time to time and those edits are not news.
    """
    return [name for name in MATERIAL_FIELDS if getattr(before, name) != getattr(after, name)]


def diff_postings(previous: list[JobPosting], current: list[JobPosting]) -> ChangeSet:
    """Compare two datasets and classify every posting.

    Postings are matched by their deterministic ``job_id``, so a job that is
    still open on the board is recognised as the same job on every run.
    """
    old = _index(previous)
    new = _index(current)

    added = [new[job_id] for job_id in new.keys() - old.keys()]
    removed = [old[job_id] for job_id in old.keys() - new.keys()]

    changed: list[ChangedJob] = []
    unchanged = 0
    for job_id in old.keys() & new.keys():
        fields = material_differences(old[job_id], new[job_id])
        if fields:
            changed.append(ChangedJob(before=old[job_id], after=new[job_id], fields=fields))
        else:
            unchanged += 1

    # Deterministic ordering keeps the generated report byte-stable.
    added.sort(key=lambda job: job.sort_key())
    removed.sort(key=lambda job: job.sort_key())
    changed.sort(key=lambda item: item.after.sort_key())
    return ChangeSet(added=added, removed=removed, changed=changed, unchanged=unchanged)


def carry_forward_first_seen(
    previous: list[JobPosting], current: list[JobPosting]
) -> list[JobPosting]:
    """Keep the original discovery date of postings we have seen before.

    Without this, ``first_seen`` would be rewritten to today on every run and
    the dataset would change daily for no real reason.
    """
    old = _index(previous)
    for posting in current:
        known = old.get(posting.job_id)
        if known and known.first_seen:
            posting.first_seen = known.first_seen
    return current
