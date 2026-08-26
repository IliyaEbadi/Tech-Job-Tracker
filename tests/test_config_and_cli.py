"""Tests for configuration loading and the command-line interface."""

from __future__ import annotations

import pytest

from conftest import PROJECT_ROOT
from job_tracker.cli import main
from job_tracker.config import ConfigError, load_settings, parse_settings

CONFIG = PROJECT_ROOT / "config" / "settings.yaml"

MINIMAL = {
    "sources": [{"name": "gh", "type": "greenhouse", "options": {"boards": ["a"]}}],
    "location": {"include_terms": ["Toronto"]},
    "roles": {"categories": {"Software Development": ["Developer"]}},
}


def test_the_shipped_configuration_is_valid(settings):
    assert [source.type for source in settings.sources] == ["greenhouse", "lever", "ashby"]
    assert "toronto" in settings.location.include_terms
    assert settings.report.top_n > 0
    # The catch-all category must stay last so specific ones win.
    assert list(settings.roles.categories)[-1] == "Software Development"


def test_terms_are_lowercased_for_matching():
    settings = parse_settings(MINIMAL)
    assert settings.location.include_terms == ["toronto"]
    assert settings.roles.categories["Software Development"] == ["developer"]


def test_defaults_are_applied_when_sections_are_missing():
    settings = parse_settings(MINIMAL)
    assert settings.http.timeout_seconds == 20.0
    assert settings.report.max_new_rows == 25
    assert settings.location.allow_remote_canada is True


@pytest.mark.parametrize(
    "broken",
    [
        {**MINIMAL, "sources": []},
        {**MINIMAL, "sources": [{"name": "no-type"}]},
        {**MINIMAL, "location": {"include_terms": []}},
        {**MINIMAL, "roles": {"categories": {}}},
        {**MINIMAL, "location": {"include_terms": "toronto"}},
    ],
)
def test_bad_configuration_fails_loudly(broken):
    with pytest.raises(ConfigError):
        parse_settings(broken)


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "nope.yaml")


def test_cli_lists_sources(capsys):
    assert main(["--config", str(CONFIG), "--list-sources"]) == 0
    output = capsys.readouterr().out
    assert "greenhouse" in output
    assert "faire" in output


def test_cli_reports_a_configuration_error(tmp_path, capsys):
    assert main(["--config", str(tmp_path / "missing.yaml")]) == 1
    assert "Configuration error" in capsys.readouterr().err
