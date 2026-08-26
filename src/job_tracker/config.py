"""Loading and validating ``config/settings.yaml``.

The YAML file is the only place search behaviour is defined. Parsing it into
dataclasses (instead of passing dictionaries around) means a typo in the file
fails loudly at start-up rather than silently filtering out every job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/settings.yaml")


class ConfigError(ValueError):
    """Raised when the configuration file is missing or malformed."""


@dataclass(slots=True)
class HttpSettings:
    """How the tracker behaves as an HTTP client."""

    user_agent: str = "toronto-tech-job-tracker/1.0"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    delay_seconds: float = 1.0


@dataclass(slots=True)
class SourceSettings:
    """One configured source (a name, a type, and its options)."""

    name: str
    type: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LocationSettings:
    """Terms that decide whether a posting counts as Toronto/GTA."""

    include_terms: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    allow_remote_canada: bool = True
    remote_canada_terms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RoleSettings:
    """Terms that decide whether a title is an early-career tech role."""

    categories: dict[str, list[str]] = field(default_factory=dict)
    exclude_terms: list[str] = field(default_factory=list)
    junior_terms: list[str] = field(default_factory=list)

    def all_keywords(self) -> list[str]:
        """Every category keyword, flattened. Used by the role filter."""
        return [keyword for keywords in self.categories.values() for keyword in keywords]


@dataclass(slots=True)
class ReportSettings:
    """Presentation knobs for the generated report."""

    max_new_rows: int = 25
    top_n: int = 10
    summary_chars: int = 280


@dataclass(slots=True)
class Settings:
    """The whole configuration file, parsed."""

    http: HttpSettings = field(default_factory=HttpSettings)
    sources: list[SourceSettings] = field(default_factory=list)
    location: LocationSettings = field(default_factory=LocationSettings)
    roles: RoleSettings = field(default_factory=RoleSettings)
    report: ReportSettings = field(default_factory=ReportSettings)

    def enabled_sources(self) -> list[SourceSettings]:
        """Configured sources with ``enabled: true``."""
        return [source for source in self.sources if source.enabled]


def _lower_terms(values: Any, *, where: str) -> list[str]:
    """Coerce a YAML list into a list of lowercase, stripped strings."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ConfigError(f"{where} must be a list, got {type(values).__name__}")
    return [str(value).strip().lower() for value in values if str(value).strip()]


def _parse_sources(raw: Any) -> list[SourceSettings]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("'sources' must be a non-empty list")
    sources: list[SourceSettings] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"sources[{index}] must be a mapping")
        source_type = str(entry.get("type", "")).strip()
        if not source_type:
            raise ConfigError(f"sources[{index}] is missing 'type'")
        sources.append(
            SourceSettings(
                name=str(entry.get("name") or source_type).strip(),
                type=source_type,
                enabled=bool(entry.get("enabled", True)),
                options=dict(entry.get("options") or {}),
            )
        )
    return sources


def _parse_categories(raw: Any) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("roles.categories must be a mapping of category -> keywords")
    return {
        str(name): _lower_terms(keywords, where=f"roles.categories.{name}")
        for name, keywords in raw.items()
    }


def parse_settings(raw: dict[str, Any]) -> Settings:
    """Build a :class:`Settings` object from an already-parsed YAML mapping."""
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be a mapping")

    http_raw = raw.get("http") or {}
    location_raw = raw.get("location") or {}
    roles_raw = raw.get("roles") or {}
    report_raw = raw.get("report") or {}

    settings = Settings(
        http=HttpSettings(
            user_agent=str(http_raw.get("user_agent", HttpSettings.user_agent)),
            timeout_seconds=float(http_raw.get("timeout_seconds", 20.0)),
            max_retries=int(http_raw.get("max_retries", 2)),
            delay_seconds=float(http_raw.get("delay_seconds", 1.0)),
        ),
        sources=_parse_sources(raw.get("sources")),
        location=LocationSettings(
            include_terms=_lower_terms(
                location_raw.get("include_terms"), where="location.include_terms"
            ),
            exclude_terms=_lower_terms(
                location_raw.get("exclude_terms"), where="location.exclude_terms"
            ),
            allow_remote_canada=bool(location_raw.get("allow_remote_canada", True)),
            remote_canada_terms=_lower_terms(
                location_raw.get("remote_canada_terms"), where="location.remote_canada_terms"
            ),
        ),
        roles=RoleSettings(
            categories=_parse_categories(roles_raw.get("categories")),
            exclude_terms=_lower_terms(roles_raw.get("exclude_terms"), where="roles.exclude_terms"),
            junior_terms=_lower_terms(roles_raw.get("junior_terms"), where="roles.junior_terms"),
        ),
        report=ReportSettings(
            max_new_rows=int(report_raw.get("max_new_rows", 25)),
            top_n=int(report_raw.get("top_n", 10)),
            summary_chars=int(report_raw.get("summary_chars", 280)),
        ),
    )

    if not settings.location.include_terms:
        raise ConfigError("location.include_terms must list at least one term")
    if not settings.roles.categories:
        raise ConfigError("roles.categories must define at least one category")
    return settings


def load_settings(path: Path | str = DEFAULT_CONFIG_PATH) -> Settings:
    """Read and parse the YAML configuration file at ``path``."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(f"configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return parse_settings(raw)
