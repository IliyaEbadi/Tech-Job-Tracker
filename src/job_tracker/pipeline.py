"""The end-to-end run: collect, filter, compare, write.

Reading this file top to bottom is the fastest way to understand the project.
Every step delegates to a small module that can be tested on its own:

    sources -> filters -> normalize -> changes -> report -> storage
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .changes import ChangeSet, carry_forward_first_seen, diff_postings
from .config import Settings
from .filters import classify
from .models import JobPosting, RawJob
from .normalize import deduplicate, normalize_job
from .report import build_summary, render_markdown
from .sources import JobSource, build_sources
from .storage import (
    load_postings,
    postings_payload,
    write_json_if_changed,
    write_text_if_changed,
)

logger = logging.getLogger(__name__)

DEFAULT_DATA_PATH = Path("data/jobs.json")
DEFAULT_REPORT_PATH = Path("reports/latest.md")
DEFAULT_SUMMARY_PATH = Path("reports/summary.json")


@dataclass(slots=True)
class RunResult:
    """Everything a caller (the CLI, or a test) needs to know about a run."""

    postings: list[JobPosting] = field(default_factory=list)
    changes: ChangeSet = field(default_factory=ChangeSet)
    summary: dict = field(default_factory=dict)
    collected: int = 0
    source_errors: list[str] = field(default_factory=list)
    written_files: list[str] = field(default_factory=list)
    aborted_reason: str = ""

    @property
    def ok(self) -> bool:
        """True when the run produced a usable dataset."""
        return not self.aborted_reason


def collect_raw_jobs(sources: list[JobSource]) -> tuple[list[RawJob], list[str]]:
    """Fetch from every source, tolerating individual failures.

    A source that raises is logged and skipped: partial data from the other
    sources is far more useful than no data at all.
    """
    raw_jobs: list[RawJob] = []
    errors: list[str] = []
    for source in sources:
        try:
            jobs = source.fetch()
        except Exception as error:  # noqa: BLE001 - one bad source must not stop the run
            logger.error("source_failed source=%s error=%s", source.name, error)
            errors.append(f"{source.name}: {error}")
            continue
        logger.info("source_collected source=%s raw_jobs=%d", source.name, len(jobs))
        raw_jobs.extend(jobs)
    return raw_jobs, errors


def select_and_normalize(
    raw_jobs: list[RawJob], settings: Settings, *, first_seen: str
) -> list[JobPosting]:
    """Keep the relevant postings and turn them into normalized records."""
    kept: list[JobPosting] = []
    for raw in raw_jobs:
        category = classify(raw, settings)
        if category is None:
            continue
        kept.append(normalize_job(raw, settings, first_seen=first_seen, category=category))
    postings = deduplicate(kept)
    logger.info("filtered raw=%d kept=%d unique=%d", len(raw_jobs), len(kept), len(postings))
    return postings


def _abort_reason(
    postings: list[JobPosting],
    previous: list[JobPosting],
    sources: list[JobSource],
    errors: list[str],
) -> str:
    """Decide whether the result is too damaged to overwrite the dataset.

    Network trouble must never be recorded as "every job in Toronto closed",
    so a run that lost all of its sources leaves the committed data alone.
    """
    if sources and len(errors) >= len(sources):
        return "every configured source failed"
    if errors and previous and not postings:
        return "sources failed and no postings were collected"
    return ""


def run_tracker(
    settings: Settings,
    *,
    data_path: Path | str = DEFAULT_DATA_PATH,
    report_path: Path | str = DEFAULT_REPORT_PATH,
    summary_path: Path | str = DEFAULT_SUMMARY_PATH,
    sources: list[JobSource] | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> RunResult:
    """Run the whole pipeline once and return what happened."""
    moment = now or datetime.now(UTC)
    today = moment.strftime("%Y-%m-%d")
    generated_at = moment.strftime("%Y-%m-%d %H:%M")

    active_sources = sources if sources is not None else build_sources(settings)
    logger.info("run_started sources=%s", ",".join(source.name for source in active_sources))

    raw_jobs, errors = collect_raw_jobs(active_sources)
    postings = select_and_normalize(raw_jobs, settings, first_seen=today)
    previous = load_postings(data_path)

    reason = _abort_reason(postings, previous, active_sources, errors)
    if reason:
        logger.error("run_aborted reason=%s", reason)
        return RunResult(
            postings=previous,
            collected=len(raw_jobs),
            source_errors=errors,
            aborted_reason=reason,
        )

    postings = carry_forward_first_seen(previous, postings)
    changes = diff_postings(previous, postings)
    summary = build_summary(
        postings, changes, settings, generated_at=generated_at, source_errors=errors
    )
    report = render_markdown(postings, changes, summary, settings)

    written: list[str] = []
    if not dry_run:
        if write_json_if_changed(data_path, postings_payload(postings), volatile_keys=()):
            written.append(str(data_path))
        # The report describes the last run that actually found something. When
        # nothing changed, regenerating it would only churn the "new this run"
        # counters and the timestamp, so the existing report is left in place.
        missing_report = not Path(report_path).is_file() or not Path(summary_path).is_file()
        if changes.has_changes or written or missing_report:
            if write_json_if_changed(summary_path, summary):
                written.append(str(summary_path))
            if write_text_if_changed(report_path, report):
                written.append(str(report_path))

    logger.info(
        "run_finished active=%d added=%d removed=%d changed=%d written=%s",
        len(postings),
        len(changes.added),
        len(changes.removed),
        len(changes.changed),
        ",".join(written) or "none",
    )
    return RunResult(
        postings=postings,
        changes=changes,
        summary=summary,
        collected=len(raw_jobs),
        source_errors=errors,
        written_files=written,
    )
