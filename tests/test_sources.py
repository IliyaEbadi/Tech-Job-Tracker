"""Tests for the three source adapters.

No test in this file touches the network: each source is handed a fake HTTP
client that replays a stored JSON fixture.
"""

from __future__ import annotations

from conftest import load_fixture
from job_tracker.config import parse_settings
from job_tracker.sources import build_sources
from job_tracker.sources.ashby import AshbySource
from job_tracker.sources.base import SourceError
from job_tracker.sources.greenhouse import GreenhouseSource
from job_tracker.sources.lever import LeverSource, epoch_ms_to_date


def test_greenhouse_maps_every_field(fake_client):
    client = fake_client({"greenhouse.io": load_fixture("greenhouse_board.json")})
    source = GreenhouseSource("greenhouse", {"boards": ["examplelabs"]}, client)

    jobs = source.fetch()

    assert len(jobs) == 5
    first = jobs[0]
    assert first.title == "Junior Software Developer"
    assert first.company == "Example Labs"
    assert first.location == "Toronto, ON"
    assert first.url.endswith("/4981486007")
    assert first.posted_at.startswith("2026-08-01")
    assert first.source == "greenhouse"
    assert "Python" in first.description


def test_greenhouse_calls_the_documented_board_url(fake_client):
    client = fake_client({"greenhouse.io": load_fixture("greenhouse_board.json")})
    GreenhouseSource("greenhouse", {"boards": ["examplelabs"]}, client).fetch()
    assert client.calls == ["https://boards-api.greenhouse.io/v1/boards/examplelabs/jobs"]


def test_lever_maps_fields_and_converts_timestamps(fake_client):
    client = fake_client({"api.lever.co": load_fixture("lever_postings.json")})
    source = LeverSource("lever", {"companies": ["exampleco"]}, client)

    jobs = source.fetch()

    assert [job.title for job in jobs] == [
        "Application Support Analyst",
        "Merchandising Coordinator",
        "Data Analyst",
    ]
    assert jobs[0].company == "Exampleco"
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].workplace_type == "hybrid"
    assert jobs[0].posted_at == "2026-08-04"
    # An empty location falls back to the allLocations list.
    assert jobs[2].location == "Markham, ON; Remote - Canada"
    assert jobs[2].posted_at == ""


def test_lever_prefers_plain_text_descriptions(fake_client):
    client = fake_client({"api.lever.co": load_fixture("lever_postings.json")})
    jobs = LeverSource("lever", {"companies": ["exampleco"]}, client).fetch()
    assert jobs[0].description == "Support our internal applications and users."
    assert jobs[1].description.startswith("<div>")


def test_epoch_conversion_handles_bad_input():
    assert epoch_ms_to_date(1785852800174) == "2026-08-04"
    assert epoch_ms_to_date(None) == ""
    assert epoch_ms_to_date("nonsense") == ""
    assert epoch_ms_to_date(0) == ""


def test_ashby_skips_unlisted_jobs(fake_client):
    client = fake_client({"ashbyhq.com": load_fixture("ashby_board.json")})
    source = AshbySource("ashby", {"boards": ["exampleorg"]}, client)

    jobs = source.fetch()

    titles = [job.title for job in jobs]
    assert "Unlisted Draft Role" not in titles
    assert len(jobs) == 3
    assert jobs[0].company == "Exampleorg"
    assert jobs[0].employment_type == "Intern"
    assert jobs[0].workplace_type == "Hybrid"


def test_a_failing_board_does_not_lose_the_others(fake_client):
    client = fake_client(
        {
            "boards/broken/": SourceError("boom"),
            "greenhouse.io": load_fixture("greenhouse_board.json"),
        }
    )
    source = GreenhouseSource("greenhouse", {"boards": ["broken", "examplelabs"]}, client)

    jobs = source.fetch()

    assert len(jobs) == 5


def test_board_entries_accept_a_company_override(fake_client):
    client = fake_client({"ashbyhq.com": load_fixture("ashby_board.json")})
    options = {"boards": [{"token": "exampleorg", "company": "Example Org Inc."}]}
    jobs = AshbySource("ashby", options, client).fetch()
    assert jobs[0].company == "Example Org Inc."


def test_build_sources_skips_unknown_and_disabled_entries():
    raw = {
        "sources": [
            {"name": "greenhouse", "type": "greenhouse", "options": {"boards": ["a"]}},
            {"name": "mystery", "type": "not-a-real-source"},
            {"name": "disabled", "type": "lever", "enabled": False},
        ],
        "location": {"include_terms": ["toronto"]},
        "roles": {"categories": {"Software Development": ["developer"]}},
    }
    sources = build_sources(parse_settings(raw))
    assert [source.name for source in sources] == ["greenhouse"]
