"""Building the human report and the machine-readable summary.

``reports/latest.md`` is what a person reads; ``reports/summary.json`` is what
another program (or a future dashboard) would read. Both are generated from
the same in-memory summary so they can never disagree.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .changes import ChangeSet
from .config import Settings
from .filters import has_junior_signal
from .models import JobPosting
from .normalize import truncate
from .storage import TIMESTAMP_MARKER

MAX_LISTED_REMOVED = 15
MAX_LISTED_CHANGED = 15
MAX_LOCATION_CHARS = 42


def _ranked(counter: Counter[str], limit: int) -> list[tuple[str, int]]:
    """Most common first, ties broken alphabetically so output is stable."""
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]


def _cell(value: str) -> str:
    """Make a value safe to place inside a Markdown table cell."""
    return (value or "-").replace("|", "\\|").replace("\n", " ").strip() or "-"


def _place(value: str) -> str:
    """Shorten a location for display; the full text stays in the dataset."""
    return _cell(truncate(value, MAX_LOCATION_CHARS))


def _link(posting: JobPosting) -> str:
    """Markdown link to a posting, falling back to plain text without a URL."""
    title = _cell(posting.title)
    return f"[{title}]({posting.url})" if posting.url else title


def build_summary(
    postings: list[JobPosting],
    changes: ChangeSet,
    settings: Settings,
    *,
    generated_at: str,
    source_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Collect every number the report needs into one plain dictionary."""
    top_n = settings.report.top_n
    companies = Counter(posting.company for posting in postings)
    categories = Counter(posting.category for posting in postings)
    locations = Counter(posting.location for posting in postings)
    sources = Counter(posting.source for posting in postings)
    junior_count = sum(1 for posting in postings if has_junior_signal(posting.title, settings))

    return {
        "generated_at": generated_at,
        "totals": {
            "active_jobs": len(postings),
            "explicitly_junior": junior_count,
            **changes.counts(),
        },
        "by_source": [{"source": name, "jobs": count} for name, count in _ranked(sources, top_n)],
        "top_companies": [
            {"company": name, "jobs": count} for name, count in _ranked(companies, top_n)
        ],
        "by_category": [
            {"category": name, "jobs": count} for name, count in _ranked(categories, top_n)
        ],
        "top_locations": [
            {"location": name, "jobs": count} for name, count in _ranked(locations, top_n)
        ],
        "new_jobs": [
            {
                "job_id": posting.job_id,
                "title": posting.title,
                "company": posting.company,
                "location": posting.location,
                "category": posting.category,
                "url": posting.url,
            }
            for posting in changes.added
        ],
        "removed_jobs": [
            {
                "job_id": posting.job_id,
                "title": posting.title,
                "company": posting.company,
                "location": posting.location,
            }
            for posting in changes.removed
        ],
        "source_errors": sorted(source_errors or []),
    }


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Render a Markdown table, or a placeholder when there are no rows."""
    if not rows:
        return ["_None._", ""]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.append("")
    return lines


def render_markdown(
    postings: list[JobPosting],
    changes: ChangeSet,
    summary: dict[str, Any],
    settings: Settings,
) -> str:
    """Render ``reports/latest.md``.

    The generated-at line carries a marker comment so that a run which finds
    no new jobs can be detected as "no meaningful change" and skipped.
    """
    totals = summary["totals"]
    lines: list[str] = [
        "# Toronto Tech Job Intelligence - Latest Report",
        "",
        f"{TIMESTAMP_MARKER} _Last meaningful update: {summary['generated_at']} UTC_",
        "",
        "Entry-level technology roles in Toronto and the GTA, collected from public",
        "job-board APIs. This file is regenerated only when the underlying data changes.",
        "",
        "## Snapshot",
        "",
    ]
    lines.extend(
        _table(
            ["Metric", "Value"],
            [
                ["Active postings tracked", str(totals["active_jobs"])],
                ["New this run", str(totals["added"])],
                ["Removed / expired this run", str(totals["removed"])],
                ["Updated postings", str(totals["changed"])],
                ["Unchanged postings", str(totals["unchanged"])],
                ["Explicitly junior / intern / new-grad titles", str(totals["explicitly_junior"])],
            ],
        )
    )

    lines.append("## New this run")
    lines.append("")
    new_rows = [
        [
            _link(posting),
            _cell(posting.company),
            _place(posting.location),
            _cell(posting.category),
            _cell(posting.posted_at or posting.first_seen),
        ]
        for posting in changes.added[: settings.report.max_new_rows]
    ]
    lines.extend(_table(["Role", "Company", "Location", "Category", "Posted"], new_rows))
    hidden = len(changes.added) - len(new_rows)
    if hidden > 0:
        lines.extend([f"_...and {hidden} more in `data/jobs.json`._", ""])

    lines.append("## Removed or expired since the last run")
    lines.append("")
    removed_rows = [
        [_cell(posting.title), _cell(posting.company), _place(posting.location)]
        for posting in changes.removed[:MAX_LISTED_REMOVED]
    ]
    lines.extend(_table(["Role", "Company", "Location"], removed_rows))

    lines.append("## Updated postings")
    lines.append("")
    changed_rows = [
        [_link(item.after), _cell(item.after.company), _cell(item.describe())]
        for item in changes.changed[:MAX_LISTED_CHANGED]
    ]
    lines.extend(_table(["Role", "Company", "What changed"], changed_rows))

    lines.append(f"## Top companies (top {settings.report.top_n})")
    lines.append("")
    lines.extend(
        _table(
            ["Company", "Open tracked roles"],
            [[_cell(row["company"]), str(row["jobs"])] for row in summary["top_companies"]],
        )
    )

    lines.append("## Roles by category")
    lines.append("")
    lines.extend(
        _table(
            ["Category", "Postings"],
            [[_cell(row["category"]), str(row["jobs"])] for row in summary["by_category"]],
        )
    )

    lines.append("## Top locations")
    lines.append("")
    lines.extend(
        _table(
            ["Location", "Postings"],
            [[_place(row["location"]), str(row["jobs"])] for row in summary["top_locations"]],
        )
    )

    lines.append("## Sources")
    lines.append("")
    lines.extend(
        _table(
            ["Source", "Postings kept"],
            [[_cell(row["source"]), str(row["jobs"])] for row in summary["by_source"]],
        )
    )

    if summary["source_errors"]:
        lines.append("## Collection warnings")
        lines.append("")
        lines.extend(f"- {error}" for error in summary["source_errors"])
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "Collected from the public Greenhouse, Lever and Ashby job-board APIs.",
            "Counts describe the postings this project tracks, not the whole Toronto job market.",
            "",
        ]
    )
    return "\n".join(lines)
