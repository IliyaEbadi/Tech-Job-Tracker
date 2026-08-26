"""Command-line entry point.

    python -m job_tracker              # collect, compare, write artifacts
    python -m job_tracker --dry-run    # do everything except write files
    python -m job_tracker --list-sources

Exit codes: ``0`` success, ``1`` configuration problem, ``2`` the run was
abandoned because the sources could not be reached.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, ConfigError, load_settings
from .logging_setup import setup_logging
from .pipeline import (
    DEFAULT_DATA_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_SUMMARY_PATH,
    RunResult,
    run_tracker,
)
from .sources import SOURCE_TYPES, board_entries


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="job-tracker",
        description="Collect entry-level Toronto/GTA tech job postings and report on changes.",
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="path to settings.yaml"
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH, help="dataset to update")
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT_PATH, help="Markdown report to write"
    )
    parser.add_argument(
        "--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="JSON summary to write"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="run the pipeline without writing any file"
    )
    parser.add_argument(
        "--list-sources", action="store_true", help="show the configured sources and exit"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug-level logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="warnings and errors only")
    return parser


def _print_sources(settings) -> None:
    """Show what the configuration asks the tracker to collect."""
    print("Configured sources:")
    for entry in settings.sources:
        known = "ok" if entry.type in SOURCE_TYPES else "UNKNOWN TYPE"
        state = "enabled" if entry.enabled else "disabled"
        boards = board_entries(entry.options, "boards") or board_entries(entry.options, "companies")
        names = ", ".join(token for token, _ in boards) or "(none)"
        print(f"  - {entry.name} [{entry.type}, {state}, {known}]: {names}")


def _print_result(result: RunResult) -> None:
    """Print a short, human-friendly summary of the run to stdout."""
    if not result.ok:
        print(f"Run abandoned: {result.aborted_reason}")
        print("Existing data and reports were left untouched.")
        return

    counts = result.changes.counts()
    print(f"Active postings tracked : {len(result.postings)}")
    print(f"New this run            : {counts['added']}")
    print(f"Removed / expired       : {counts['removed']}")
    print(f"Updated                 : {counts['changed']}")
    if result.source_errors:
        print(f"Source warnings         : {len(result.source_errors)}")
        for error in result.source_errors:
            print(f"  ! {error}")
    if result.written_files:
        print("Files updated           : " + ", ".join(result.written_files))
    else:
        print("Files updated           : none (nothing meaningful changed)")


def main(argv: list[str] | None = None) -> int:
    """Run the tracker and return a process exit code."""
    args = build_parser().parse_args(argv)
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        settings = load_settings(args.config)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1

    if args.list_sources:
        _print_sources(settings)
        return 0

    result = run_tracker(
        settings,
        data_path=args.data,
        report_path=args.report,
        summary_path=args.summary,
        dry_run=args.dry_run,
    )
    _print_result(result)
    return 0 if result.ok else 2


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
