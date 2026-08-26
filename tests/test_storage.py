"""Tests for the write-only-on-change behaviour."""

from __future__ import annotations

import json

from conftest import make_posting
from job_tracker.storage import (
    TIMESTAMP_MARKER,
    load_postings,
    postings_payload,
    write_json_if_changed,
    write_text_if_changed,
)


def _report(timestamp: str, body: str) -> str:
    return f"# Report\n\n{TIMESTAMP_MARKER} _Last meaningful update: {timestamp}_\n\n{body}\n"


def test_text_is_written_once_and_skipped_when_only_the_timestamp_moves(tmp_path):
    target = tmp_path / "reports" / "latest.md"

    assert write_text_if_changed(target, _report("2026-08-26 06:00", "5 jobs")) is True
    assert write_text_if_changed(target, _report("2026-08-27 06:00", "5 jobs")) is False
    assert "2026-08-26 06:00" in target.read_text(encoding="utf-8")

    assert write_text_if_changed(target, _report("2026-08-27 06:00", "6 jobs")) is True
    assert "2026-08-27 06:00" in target.read_text(encoding="utf-8")


def test_json_ignores_the_generated_at_key(tmp_path):
    target = tmp_path / "reports" / "summary.json"
    payload = {"generated_at": "2026-08-26 06:00", "totals": {"active_jobs": 5}}

    assert write_json_if_changed(target, payload) is True
    assert write_json_if_changed(target, {**payload, "generated_at": "2026-08-27 06:00"}) is False
    assert write_json_if_changed(target, {**payload, "totals": {"active_jobs": 6}}) is True

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["totals"]["active_jobs"] == 6


def test_dataset_round_trip_is_stable(tmp_path):
    target = tmp_path / "data" / "jobs.json"
    postings = [make_posting(job_id="2", company="Zeta"), make_posting(job_id="1")]

    assert write_json_if_changed(target, postings_payload(postings), volatile_keys=()) is True
    first_bytes = target.read_bytes()

    # Same data in a different order must not produce a different file.
    reversed_payload = postings_payload(list(reversed(postings)))
    assert write_json_if_changed(target, reversed_payload, volatile_keys=()) is False
    assert target.read_bytes() == first_bytes

    restored = load_postings(target)
    assert [job.job_id for job in restored] == [
        job.job_id for job in sorted(postings, key=lambda j: j.sort_key())
    ]


def test_missing_or_corrupt_dataset_is_treated_as_empty(tmp_path):
    assert load_postings(tmp_path / "nope.json") == []
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_postings(broken) == []
