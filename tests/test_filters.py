"""Tests for the location and role filters."""

from __future__ import annotations

import pytest

from job_tracker.filters import (
    categorize_title,
    classify,
    has_junior_signal,
    is_excluded_title,
    location_matches,
)
from job_tracker.models import RawJob


@pytest.mark.parametrize(
    "location",
    [
        "Toronto, ON",
        "Mississauga, Ontario",
        "New York City, NY; Toronto, ON",
        "Kitchener-Waterloo, ON",
        "Remote (Canada)",
        "Canada",
    ],
)
def test_locations_that_should_be_kept(location, settings):
    assert location_matches(location, settings) is True


@pytest.mark.parametrize(
    "location",
    [
        "Austin, TX",
        "Ontario, California",
        "Remote (USA)",
        "Vancouver, Canada",
        "Berlin, Germany",
        "",
    ],
)
def test_locations_that_should_be_dropped(location, settings):
    assert location_matches(location, settings) is False


@pytest.mark.parametrize(
    "title",
    [
        "Senior Software Developer",
        "Staff Backend Engineer",
        "Lead Developer, Embedded",
        "Engineering Manager",
        "Director of Engineering",
        "Software Developer II",
        "Solutions Architect",
    ],
)
def test_senior_titles_are_excluded(title, settings):
    assert is_excluded_title(title, settings) is True


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Junior Software Developer", "Software Development"),
        ("Backend Developer", "Backend"),
        ("Front End Developer", "Frontend"),
        ("QA Automation Engineer", "QA and Automation"),
        ("Data Analyst, Operations", "Data and BI"),
        ("Application Support Analyst", "Support and Operations"),
        ("DevOps Engineer", "Cloud and DevOps"),
        ("Marketing Coordinator", None),
        ("Warehouse Associate", None),
    ],
)
def test_titles_are_categorized(title, expected, settings):
    assert categorize_title(title, settings) == expected


def test_specific_categories_win_over_the_catch_all(settings):
    # "developer" alone would match Software Development, but Backend is
    # declared first in the configuration file.
    assert categorize_title("Python Developer", settings) == "Backend"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Junior Developer", True),
        ("Software Engineer Intern (Winter 2027)", True),
        ("Software Developer - New Graduate", True),
        ("Software Developer", False),
    ],
)
def test_junior_signal_detection(title, expected, settings):
    assert has_junior_signal(title, settings) is expected


def _raw(title: str, location: str) -> RawJob:
    return RawJob(
        title=title,
        company="Example Labs",
        location=location,
        url="https://example.com/1",
        source="greenhouse",
    )


def test_classify_keeps_a_junior_toronto_role(settings):
    assert classify(_raw("Junior Software Developer", "Toronto, ON"), settings) == (
        "Software Development"
    )


@pytest.mark.parametrize(
    "raw",
    [
        _raw("Junior Software Developer", "Austin, TX"),
        _raw("Senior Software Developer", "Toronto, ON"),
        _raw("Warehouse Associate", "Toronto, ON"),
        _raw("", "Toronto, ON"),
    ],
)
def test_classify_rejects_everything_else(raw, settings):
    assert classify(raw, settings) is None
