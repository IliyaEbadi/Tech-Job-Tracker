"""Tests for cleaning, identifiers and deduplication."""

from __future__ import annotations

from conftest import make_posting
from job_tracker.models import RawJob
from job_tracker.normalize import (
    clean_text,
    deduplicate,
    make_job_id,
    normalize_date,
    normalize_employment_type,
    normalize_job,
    normalize_location,
    normalize_workplace_type,
    slugify,
    strip_html,
    truncate,
)


def test_clean_text_collapses_whitespace_and_nbsp():
    assert clean_text("  Junior  Software\n Developer ") == "Junior Software Developer"
    assert clean_text(None) == ""


def test_strip_html_handles_double_escaped_markup():
    raw = "&lt;p&gt;Work with our&amp;nbsp;&lt;strong&gt;Python&lt;/strong&gt; team.&lt;/p&gt;"
    assert strip_html(raw) == "Work with our Python team."


def test_strip_html_drops_script_content():
    assert strip_html("<div>Keep<script>alert(1)</script></div>") == "Keep"


def test_slugify_and_truncate():
    assert slugify("  Junior Software Developer (Co-op) ") == "junior-software-developer-co-op"
    assert truncate("one two three four", 9) == "one two..."
    assert truncate("short", 100) == "short"


def test_normalize_location_prefers_a_configured_city():
    location = "New York City, NY; San Francisco, CA; Toronto, ON"
    assert normalize_location(location, ["toronto"]) == "Toronto, ON"


def test_normalize_location_falls_back_to_first_entry():
    assert normalize_location("Berlin; Paris", ["toronto"]) == "Berlin"
    assert normalize_location("", ["toronto"]) == "Unspecified"


def test_normalize_location_keeps_pipes_inside_one_name():
    text = "Remote (United States | Canada)"
    assert normalize_location(text, ["toronto"]) == text


def test_employment_workplace_and_date_normalization():
    assert normalize_employment_type("FullTime") == "Full-time"
    assert normalize_employment_type("") == ""
    assert normalize_workplace_type("Onsite") == "On-site"
    assert normalize_workplace_type("", "Remote - Canada") == "Remote"
    assert normalize_date("2026-08-05T17:27:16.004+00:00") == "2026-08-05"
    assert normalize_date("not a date") == ""


def test_job_id_is_deterministic_and_ignores_formatting():
    first = make_job_id("Example Labs", "Junior Software Developer", "Toronto, ON")
    second = make_job_id("  example   labs ", "junior software developer", "toronto, on")
    assert first == second
    assert len(first) == 12


def test_job_id_changes_with_the_job_identity():
    base = make_job_id("Example Labs", "Junior Software Developer", "Toronto, ON")
    assert base != make_job_id("Example Labs", "Junior QA Analyst", "Toronto, ON")
    assert base != make_job_id("Other Corp", "Junior Software Developer", "Toronto, ON")
    assert base != make_job_id("Example Labs", "Junior Software Developer", "Ottawa, ON")


def test_normalize_job_builds_a_complete_record(settings):
    raw = RawJob(
        title="  Junior Python Developer ",
        company="Example Labs",
        location="Toronto, ON; Remote",
        url="https://example.com/jobs/1",
        source="greenhouse",
        employment_type="FullTime",
        workplace_type="Hybrid",
        posted_at="2026-08-01T10:00:00-04:00",
        description="<p>Build APIs with <b>Python</b>.</p>",
    )
    posting = normalize_job(raw, settings, first_seen="2026-08-02", category="Backend")

    assert posting.title == "Junior Python Developer"
    assert posting.location == "Toronto, ON"
    assert posting.employment_type == "Full-time"
    assert posting.workplace_type == "Hybrid"
    assert posting.posted_at == "2026-08-01"
    assert posting.first_seen == "2026-08-02"
    assert posting.summary == "Build APIs with Python."
    assert "junior" in posting.tags
    assert posting.job_id == make_job_id("Example Labs", "Junior Python Developer", "Toronto, ON")


def test_deduplicate_collapses_the_same_job_from_two_boards():
    ashby = make_posting(source="ashby", url="https://ashby.example/1")
    greenhouse = make_posting(source="greenhouse", url="https://greenhouse.example/1")
    other = make_posting(job_id="bbbbbbbbbbbb", title="QA Analyst")

    result = deduplicate([greenhouse, ashby, other])

    assert len(result) == 2
    # "ashby" sorts before "greenhouse", so the winner is picked deterministically.
    assert result[0].source == "ashby"
    assert deduplicate([ashby, greenhouse, other]) == result


def test_deduplicate_sorts_output_stably():
    postings = [
        make_posting(job_id="1", company="Zeta", title="Software Developer"),
        make_posting(job_id="2", company="Alpha", title="Software Developer"),
        make_posting(job_id="3", company="Alpha", title="Backend Developer"),
    ]
    ordered = [(job.company, job.title) for job in deduplicate(postings)]
    assert ordered == [
        ("Alpha", "Backend Developer"),
        ("Alpha", "Software Developer"),
        ("Zeta", "Software Developer"),
    ]
