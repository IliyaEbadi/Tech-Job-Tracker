"""Turning messy board data into clean, comparable records.

Normalization is the heart of the project: two runs can only be compared if
identical postings produce byte-identical records. Everything here is pure
(no network, no clock, no globals) which also makes it easy to unit test.
"""

from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser

from .config import Settings
from .models import JobPosting, RawJob

# Boards commonly join several offices into one string with semicolons.
# Only ";" is treated as a separator: "|" and "/" show up inside single
# location names such as "Remote (United States | Canada)".
_LOCATION_SEPARATORS = re.compile(r"\s*;\s*")
_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Employment-type spellings used by the different boards, mapped to ours.
_EMPLOYMENT_TYPES = {
    "fulltime": "Full-time",
    "full time": "Full-time",
    "full-time": "Full-time",
    "parttime": "Part-time",
    "part time": "Part-time",
    "part-time": "Part-time",
    "contract": "Contract",
    "contractor": "Contract",
    "temporary": "Contract",
    "intern": "Internship",
    "internship": "Internship",
    "co-op": "Internship",
    "coop": "Internship",
}

_WORKPLACE_TYPES = {
    "remote": "Remote",
    "hybrid": "Hybrid",
    "onsite": "On-site",
    "on-site": "On-site",
    "in office": "On-site",
    "in-office": "On-site",
}

_BLOCK_TAGS = {"br", "p", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


class _TextExtractor(HTMLParser):
    """Collect visible text from an HTML fragment, skipping script/style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def clean_text(value: str | None) -> str:
    """Collapse whitespace and strip surrounding blanks."""
    if not value:
        return ""
    return _WHITESPACE.sub(" ", str(value).replace(chr(0xA0), " ")).strip()


def strip_html(value: str | None) -> str:
    """Return the visible text of an HTML fragment as a single clean line.

    Greenhouse and Lever return HTML (sometimes escaped twice) in their
    description fields, so entities are unescaped before and after parsing.
    """
    if not value:
        return ""
    text = html.unescape(str(value))
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    return clean_text(html.unescape(parser.text()))


def slugify(value: str) -> str:
    """Lowercase, alphanumeric-only form used for identifiers and matching."""
    return _NON_ALNUM.sub("-", clean_text(value).lower()).strip("-")


def truncate(value: str, limit: int) -> str:
    """Shorten a string to ``limit`` characters on a word boundary."""
    text = clean_text(value)
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return cut + "..."


def normalize_location(value: str | None, include_terms: list[str]) -> str:
    """Reduce a multi-city location string to the most relevant single place.

    "New York City, NY; San Francisco, CA; Toronto, ON" becomes "Toronto, ON"
    so that reports and identifiers stay meaningful. When no configured term
    matches, the first listed location is kept unchanged.
    """
    text = clean_text(value)
    if not text:
        return "Unspecified"
    parts = [part.strip(" ,-") for part in _LOCATION_SEPARATORS.split(text) if part.strip(" ,-")]
    if not parts:
        return text
    for part in parts:
        lowered = part.lower()
        if any(term in lowered for term in include_terms):
            return part
    return parts[0]


def normalize_employment_type(value: str | None) -> str:
    """Map a board's employment-type wording onto a small fixed vocabulary."""
    text = clean_text(value).lower()
    if not text:
        return ""
    return _EMPLOYMENT_TYPES.get(text, clean_text(value).title())


def normalize_workplace_type(value: str | None, location: str = "") -> str:
    """Map remote/hybrid/on-site wording, falling back to the location text."""
    text = clean_text(value).lower()
    if text:
        for key, label in _WORKPLACE_TYPES.items():
            if key in text:
                return label
    lowered = clean_text(location).lower()
    for key, label in _WORKPLACE_TYPES.items():
        if key in lowered:
            return label
    return ""


def normalize_date(value: str | None) -> str:
    """Return the YYYY-MM-DD prefix of an ISO-style timestamp, or an empty string."""
    match = re.match(r"\d{4}-\d{2}-\d{2}", clean_text(value))
    return match.group(0) if match else ""


def make_job_id(company: str, title: str, location: str) -> str:
    """Build the deterministic identifier used for dedup and change detection.

    The identifier is a short SHA-256 digest of the slugified company, title
    and location. Two runs of the tracker - and two different job boards
    carrying the same posting - therefore produce the same id, while a genuine
    new posting produces a new one. No random values are involved.
    """
    fingerprint = "|".join((slugify(company), slugify(title), slugify(location)))
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]


def matched_keywords(title: str, keywords: list[str]) -> list[str]:
    """Return the configured keywords that appear in a title, sorted."""
    lowered = " " + clean_text(title).lower() + " "
    return sorted({keyword for keyword in keywords if keyword in lowered})


def build_tags(title: str, workplace_type: str, settings: Settings) -> list[str]:
    """Small, deterministic set of labels shown in the dataset and report."""
    tags = set(matched_keywords(title, settings.roles.all_keywords()))
    if matched_keywords(title, settings.roles.junior_terms):
        tags.add("junior")
    if workplace_type:
        tags.add(workplace_type.lower())
    return sorted(tags)


def normalize_job(raw: RawJob, settings: Settings, *, first_seen: str, category: str) -> JobPosting:
    """Convert a raw posting into the stored, normalized shape."""
    title = clean_text(raw.title)
    company = clean_text(raw.company)
    location = normalize_location(raw.location, settings.location.include_terms)
    workplace_type = normalize_workplace_type(raw.workplace_type, location)
    return JobPosting(
        job_id=make_job_id(company, title, location),
        title=title,
        company=company,
        location=location,
        url=clean_text(raw.url),
        source=clean_text(raw.source),
        category=category,
        employment_type=normalize_employment_type(raw.employment_type),
        workplace_type=workplace_type,
        posted_at=normalize_date(raw.posted_at),
        first_seen=first_seen,
        tags=build_tags(title, workplace_type, settings),
        summary=truncate(strip_html(raw.description), settings.report.summary_chars),
    )


def deduplicate(postings: list[JobPosting]) -> list[JobPosting]:
    """Collapse postings that share a job id.

    The same role can be published on more than one board. Keeping the record
    whose (source, url, title) sorts first makes the choice deterministic, so
    the stored dataset does not flip between runs.
    """
    best: dict[str, JobPosting] = {}
    for posting in sorted(postings, key=lambda job: (job.source, job.url, job.title)):
        best.setdefault(posting.job_id, posting)
    return sorted(best.values(), key=lambda job: job.sort_key())
