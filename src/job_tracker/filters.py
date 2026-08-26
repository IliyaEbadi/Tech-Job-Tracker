"""Deciding which postings belong in a Toronto entry-level tech report.

Two independent questions are asked about every raw posting:

1. Is it in Toronto / the GTA (or remote within Canada)?
2. Is it an early-career technology role?

Both answers come from plain keyword lists in ``config/settings.yaml``.
Keyword matching is not clever, but it is predictable, easy to tune without
touching code, and easy to explain in an interview.
"""

from __future__ import annotations

from .config import Settings
from .models import RawJob
from .normalize import clean_text


def _padded(value: str | None) -> str:
    """Lowercase text padded with spaces so ' jr ' style terms can match."""
    return " " + clean_text(value).lower() + " "


def _contains_any(haystack: str, terms: list[str]) -> bool:
    return any(term in haystack for term in terms)


def location_matches(location: str | None, settings: Settings) -> bool:
    """Return True when a location string is relevant to a Toronto job seeker.

    The rules are applied in order:

    1. An explicit exclude term (``Ontario, California``) rejects the posting.
    2. Any GTA/Ontario include term accepts it.
    3. A Canada-wide *remote* posting is accepted when ``allow_remote_canada``
       is on. The word "remote" (or a location of exactly "Canada") is
       required so that "Vancouver, Canada" is not treated as GTA-relevant.
    """
    text = _padded(location)
    rules = settings.location
    if _contains_any(text, rules.exclude_terms):
        return False
    if _contains_any(text, rules.include_terms):
        return True
    if rules.allow_remote_canada and _contains_any(text, rules.remote_canada_terms):
        return "remote" in text or text.strip() == "canada"
    return False


def is_excluded_title(title: str | None, settings: Settings) -> bool:
    """Return True for senior, management or otherwise non-entry-level titles."""
    return _contains_any(_padded(title), settings.roles.exclude_terms)


def categorize_title(title: str | None, settings: Settings) -> str | None:
    """Return the role category for a title, or None when nothing matches.

    Categories are tested in the order they appear in the configuration file,
    so specific buckets (QA, Data, Support) are checked before the general
    "Software Development" catch-all at the bottom of the list.
    """
    text = _padded(title)
    for category, keywords in settings.roles.categories.items():
        if _contains_any(text, keywords):
            return category
    return None


def has_junior_signal(title: str | None, settings: Settings) -> bool:
    """Return True when a title explicitly advertises an early-career role."""
    return _contains_any(_padded(title), settings.roles.junior_terms)


def classify(raw: RawJob, settings: Settings) -> str | None:
    """Return the category to store a posting under, or None to skip it.

    A posting is kept when its location is GTA-relevant, its title is not a
    senior/management title, and its title matches one of the configured role
    categories.
    """
    if not clean_text(raw.title) or not clean_text(raw.company):
        return None
    if not location_matches(raw.location, settings):
        return None
    if is_excluded_title(raw.title, settings):
        return None
    return categorize_title(raw.title, settings)
