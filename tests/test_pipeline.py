"""End-to-end tests for a full run, using fake sources only."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from conftest import load_fixture
from job_tracker.models import RawJob
from job_tracker.pipeline import run_tracker
from job_tracker.sources.ashby import AshbySource
from job_tracker.sources.base import JobSource, SourceError
from job_tracker.sources.greenhouse import GreenhouseSource
from job_tracker.sources.lever import LeverSource

RUN_ONE = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
RUN_TWO = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)


class StaticSource(JobSource):
    """A source that returns a fixed list of postings (or raises)."""

    type_name = "static"

    def __init__(self, name: str, jobs: list[RawJob], error: Exception | None = None) -> None:
        super().__init__(name, {}, client=None)
        self.jobs = jobs
        self.error = error

    def fetch(self) -> list[RawJob]:
        if self.error:
            raise self.error
        return list(self.jobs)


def _raw(title: str, location: str = "Toronto, ON", **overrides) -> RawJob:
    values = {
        "title": title,
        "company": "Example Labs",
        "location": location,
        "url": f"https://example.com/{title.lower().replace(' ', '-')}",
        "source": "static",
        "description": "Some description.",
    }
    values.update(overrides)
    return RawJob(**values)


@pytest.fixture
def paths(tmp_path):
    return {
        "data_path": tmp_path / "data" / "jobs.json",
        "report_path": tmp_path / "reports" / "latest.md",
        "summary_path": tmp_path / "reports" / "summary.json",
    }


def test_full_run_writes_all_three_artifacts(settings, paths):
    source = StaticSource(
        "static",
        [_raw("Junior Software Developer"), _raw("QA Automation Engineer"), _raw("Chef")],
    )

    result = run_tracker(settings, sources=[source], now=RUN_ONE, **paths)

    assert result.ok
    assert len(result.postings) == 2  # the chef is filtered out
    assert len(result.written_files) == 3
    assert paths["data_path"].is_file()
    assert paths["report_path"].is_file()
    assert paths["summary_path"].is_file()

    stored = json.loads(paths["data_path"].read_text(encoding="utf-8"))
    assert stored["job_count"] == 2
    assert stored["jobs"][0]["first_seen"] == "2026-08-26"
    assert "generated_at" not in stored


def test_second_run_with_identical_data_changes_nothing(settings, paths):
    jobs = [_raw("Junior Software Developer"), _raw("Data Analyst")]

    run_tracker(settings, sources=[StaticSource("static", jobs)], now=RUN_ONE, **paths)
    before = {name: path.read_bytes() for name, path in paths.items()}

    # A day later, the boards return exactly the same postings.
    result = run_tracker(settings, sources=[StaticSource("static", jobs)], now=RUN_TWO, **paths)

    assert result.changes.has_changes is False
    assert result.written_files == []
    assert {name: path.read_bytes() for name, path in paths.items()} == before


def test_new_and_removed_jobs_flow_into_the_report(settings, paths):
    day_one = [_raw("Junior Software Developer"), _raw("Data Analyst")]
    day_two = [_raw("Junior Software Developer"), _raw("Application Support Analyst")]

    run_tracker(settings, sources=[StaticSource("static", day_one)], now=RUN_ONE, **paths)
    result = run_tracker(settings, sources=[StaticSource("static", day_two)], now=RUN_TWO, **paths)

    assert [job.title for job in result.changes.added] == ["Application Support Analyst"]
    assert [job.title for job in result.changes.removed] == ["Data Analyst"]

    report = paths["report_path"].read_text(encoding="utf-8")
    assert "Application Support Analyst" in report
    assert "2026-08-27" in report

    # The posting that survived keeps its original discovery date.
    stored = json.loads(paths["data_path"].read_text(encoding="utf-8"))
    survivor = next(job for job in stored["jobs"] if job["title"] == "Junior Software Developer")
    assert survivor["first_seen"] == "2026-08-26"


def test_a_partial_source_failure_still_produces_data(settings, paths):
    working = StaticSource("working", [_raw("Junior Software Developer")])
    broken = StaticSource("broken", [], error=SourceError("boom"))

    result = run_tracker(settings, sources=[working, broken], now=RUN_ONE, **paths)

    assert result.ok
    assert len(result.postings) == 1
    assert result.source_errors == ["broken: boom"]
    assert "Collection warnings" in paths["report_path"].read_text(encoding="utf-8")


def test_a_total_source_failure_leaves_the_dataset_alone(settings, paths):
    run_tracker(
        settings,
        sources=[StaticSource("static", [_raw("Junior Software Developer")])],
        now=RUN_ONE,
        **paths,
    )
    before = paths["data_path"].read_bytes()

    result = run_tracker(
        settings,
        sources=[StaticSource("static", [], error=SourceError("network down"))],
        now=RUN_TWO,
        **paths,
    )

    assert result.ok is False
    assert result.aborted_reason == "every configured source failed"
    assert paths["data_path"].read_bytes() == before


def test_dry_run_writes_nothing(settings, paths):
    result = run_tracker(
        settings,
        sources=[StaticSource("static", [_raw("Junior Software Developer")])],
        now=RUN_ONE,
        dry_run=True,
        **paths,
    )

    assert result.ok
    assert result.written_files == []
    assert not paths["data_path"].exists()


def test_the_three_real_adapters_run_end_to_end_offline(settings, paths, fake_client):
    """The shipped source classes, wired to fixtures instead of the internet."""
    client = fake_client(
        {
            "greenhouse.io": load_fixture("greenhouse_board.json"),
            "api.lever.co": load_fixture("lever_postings.json"),
            "ashbyhq.com": load_fixture("ashby_board.json"),
        }
    )
    sources = [
        GreenhouseSource("greenhouse", {"boards": ["examplelabs"]}, client),
        LeverSource("lever", {"companies": ["exampleco"]}, client),
        AshbySource("ashby", {"boards": ["exampleorg"]}, client),
    ]

    result = run_tracker(settings, sources=sources, now=RUN_ONE, **paths)

    kept = {(job.company, job.title) for job in result.postings}
    assert kept == {
        ("Example Labs", "Junior Software Developer"),
        ("Example Labs", "QA Automation Engineer"),
        ("Exampleco", "Application Support Analyst"),
        ("Exampleco", "Data Analyst"),
        ("Exampleorg", "Software Engineer Intern"),
        ("Exampleorg", "Backend Developer"),
    }
    summary = json.loads(paths["summary_path"].read_text(encoding="utf-8"))
    assert summary["totals"]["active_jobs"] == 6
    assert summary["generated_at"] == "2026-08-26 06:00"
