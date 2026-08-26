"""Tests for the generated summary and Markdown report."""

from __future__ import annotations

from conftest import make_posting
from job_tracker.changes import diff_postings
from job_tracker.report import build_summary, render_markdown
from job_tracker.storage import TIMESTAMP_MARKER


def _dataset():
    return [
        make_posting(job_id="1", company="Alpha", title="Junior Software Developer"),
        make_posting(job_id="2", company="Alpha", title="QA Analyst", category="QA and Automation"),
        make_posting(job_id="3", company="Beta", title="Data Analyst", category="Data and BI"),
    ]


def test_summary_counts_and_rankings(settings):
    postings = _dataset()
    changes = diff_postings([postings[0]], postings)

    summary = build_summary(postings, changes, settings, generated_at="2026-08-26 06:00")

    assert summary["totals"]["active_jobs"] == 3
    assert summary["totals"]["added"] == 2
    assert summary["totals"]["explicitly_junior"] == 1
    assert summary["top_companies"][0] == {"company": "Alpha", "jobs": 2}
    assert [row["category"] for row in summary["by_category"]] == [
        "Data and BI",
        "QA and Automation",
        "Software Development",
    ]
    assert [job["title"] for job in summary["new_jobs"]] == ["QA Analyst", "Data Analyst"]


def test_report_contains_the_expected_sections(settings):
    postings = _dataset()
    changes = diff_postings([], postings)
    summary = build_summary(postings, changes, settings, generated_at="2026-08-26 06:00")

    report = render_markdown(postings, changes, summary, settings)

    assert TIMESTAMP_MARKER in report
    for heading in (
        "## Snapshot",
        "## New this run",
        "## Removed or expired since the last run",
        "## Updated postings",
        "## Top companies",
        "## Roles by category",
        "## Sources",
    ):
        assert heading in report
    assert "[Junior Software Developer](https://example.com/jobs/1)" in report


def test_report_is_deterministic(settings):
    postings = _dataset()
    changes = diff_postings([], postings)
    summary = build_summary(postings, changes, settings, generated_at="2026-08-26 06:00")

    assert render_markdown(postings, changes, summary, settings) == render_markdown(
        postings, changes, summary, settings
    )


def test_empty_sections_render_a_placeholder(settings):
    changes = diff_postings([], [])
    summary = build_summary([], changes, settings, generated_at="2026-08-26 06:00")

    report = render_markdown([], changes, summary, settings)

    assert "_None._" in report
    assert "Active postings tracked | 0" in report


def test_pipe_characters_in_titles_do_not_break_the_table(settings):
    postings = [make_posting(title="Developer | Platform")]
    changes = diff_postings([], postings)
    summary = build_summary(postings, changes, settings, generated_at="2026-08-26 06:00")

    report = render_markdown(postings, changes, summary, settings)

    assert "Developer \\| Platform" in report


def test_source_warnings_are_reported(settings):
    changes = diff_postings([], [])
    summary = build_summary(
        [], changes, settings, generated_at="2026-08-26 06:00", source_errors=["lever: timeout"]
    )

    report = render_markdown([], changes, summary, settings)

    assert "## Collection warnings" in report
    assert "lever: timeout" in report
