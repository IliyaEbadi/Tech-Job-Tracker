"""Tests for day-to-day change detection."""

from __future__ import annotations

from conftest import make_posting
from job_tracker.changes import (
    carry_forward_first_seen,
    diff_postings,
    material_differences,
)


def test_identical_datasets_report_no_changes():
    previous = [make_posting(job_id="1"), make_posting(job_id="2", title="QA Analyst")]
    current = [make_posting(job_id="1"), make_posting(job_id="2", title="QA Analyst")]

    changes = diff_postings(previous, current)

    assert changes.has_changes is False
    assert changes.counts() == {"added": 0, "removed": 0, "changed": 0, "unchanged": 2}


def test_added_and_removed_postings_are_detected():
    previous = [make_posting(job_id="1"), make_posting(job_id="2", title="QA Analyst")]
    current = [make_posting(job_id="1"), make_posting(job_id="3", title="Data Analyst")]

    changes = diff_postings(previous, current)

    assert [job.job_id for job in changes.added] == ["3"]
    assert [job.job_id for job in changes.removed] == ["2"]
    assert changes.unchanged == 1
    assert changes.has_changes is True


def test_material_edits_are_detected_and_described():
    previous = [make_posting(job_id="1", location="Toronto, ON")]
    current = [make_posting(job_id="1", location="Remote - Canada")]

    changes = diff_postings(previous, current)

    assert len(changes.changed) == 1
    edit = changes.changed[0]
    assert edit.fields == ["location"]
    assert edit.describe() == "location: Toronto, ON -> Remote - Canada"


def test_cosmetic_edits_are_ignored():
    before = make_posting(summary="Build things.", first_seen="2026-08-01", tags=["a"])
    after = make_posting(summary="Build many things!", first_seen="2026-08-09", tags=["b"])

    assert material_differences(before, after) == []
    assert diff_postings([before], [after]).has_changes is False


def test_first_seen_is_carried_forward_for_known_jobs():
    previous = [make_posting(job_id="1", first_seen="2026-07-01")]
    current = [make_posting(job_id="1", first_seen="2026-08-26"), make_posting(job_id="2")]

    result = carry_forward_first_seen(previous, current)

    assert result[0].first_seen == "2026-07-01"
    assert result[1].first_seen == "2026-08-01"  # untouched default from the factory


def test_change_lists_are_sorted_deterministically():
    previous = []
    current = [
        make_posting(job_id="1", company="Zeta"),
        make_posting(job_id="2", company="Alpha"),
    ]

    changes = diff_postings(previous, current)

    assert [job.company for job in changes.added] == ["Alpha", "Zeta"]
