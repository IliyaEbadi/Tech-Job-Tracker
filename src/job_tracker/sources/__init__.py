"""Source registry.

``build_sources`` translates the ``sources:`` block of the configuration file
into ready-to-use source objects. Adding a new board type means writing one
class and adding it to :data:`SOURCE_TYPES`.
"""

from __future__ import annotations

import logging

from ..config import Settings
from .ashby import AshbySource
from .base import HttpClient, JobSource, SourceError, board_entries, display_name
from .greenhouse import GreenhouseSource
from .lever import LeverSource

logger = logging.getLogger(__name__)

SOURCE_TYPES: dict[str, type[JobSource]] = {
    GreenhouseSource.type_name: GreenhouseSource,
    LeverSource.type_name: LeverSource,
    AshbySource.type_name: AshbySource,
}


def build_sources(settings: Settings, client: HttpClient | None = None) -> list[JobSource]:
    """Instantiate every enabled source described in the configuration."""
    http_client = client or HttpClient(settings.http)
    sources: list[JobSource] = []
    for entry in settings.enabled_sources():
        source_class = SOURCE_TYPES.get(entry.type)
        if source_class is None:
            logger.warning(
                "unknown_source_type type=%s name=%s known=%s",
                entry.type,
                entry.name,
                ",".join(sorted(SOURCE_TYPES)),
            )
            continue
        sources.append(source_class(entry.name, entry.options, http_client))
    return sources


__all__ = [
    "SOURCE_TYPES",
    "AshbySource",
    "GreenhouseSource",
    "HttpClient",
    "JobSource",
    "LeverSource",
    "SourceError",
    "board_entries",
    "build_sources",
    "display_name",
]
