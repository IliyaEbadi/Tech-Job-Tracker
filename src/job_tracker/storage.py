"""Reading and writing the repository's tracked artifacts.

Two ideas keep the repository history honest:

* **Deterministic output.** Records are sorted and serialized the same way
  every time, so identical data produces an identical file.
* **Write only on change.** Files are compared before being written, and the
  volatile parts (a run timestamp) are ignored during that comparison. A run
  that finds nothing new therefore leaves the working tree untouched and the
  daily workflow has nothing to commit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import JobPosting

SCHEMA_VERSION = 1

# Text used to mark the generated-at line in Markdown output. Lines containing
# it are ignored when deciding whether a report really changed.
TIMESTAMP_MARKER = "<!-- generated-at -->"

# Top-level keys in summary.json that change on every run by definition.
VOLATILE_JSON_KEYS = ("generated_at",)


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" keeps output identical on Windows and on the Linux runner.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def dumps_json(payload: Any) -> str:
    """Serialize to pretty JSON with a trailing newline (stable formatting)."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def load_postings(path: Path | str) -> list[JobPosting]:
    """Load the previously stored dataset, or an empty list on first run.

    A corrupt or unreadable file is treated as "no previous data" rather than
    crashing the run; every posting is then reported as new.
    """
    text = _read_text(Path(path))
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    records = payload.get("jobs", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    return [JobPosting.from_dict(record) for record in records if isinstance(record, dict)]


def postings_payload(postings: list[JobPosting]) -> dict[str, Any]:
    """Build the JSON body of ``data/jobs.json``.

    The payload deliberately contains no timestamp: the file should change
    only when the job data itself changes.
    """
    ordered = sorted(postings, key=lambda job: job.sort_key())
    return {
        "schema_version": SCHEMA_VERSION,
        "job_count": len(ordered),
        "jobs": [posting.to_dict() for posting in ordered],
    }


def strip_volatile_lines(text: str, marker: str = TIMESTAMP_MARKER) -> str:
    """Drop the lines that carry a run timestamp, for comparison purposes."""
    return "\n".join(line for line in text.splitlines() if marker not in line)


def write_text_if_changed(path: Path | str, text: str, *, marker: str = TIMESTAMP_MARKER) -> bool:
    """Write a text file only when its meaningful content changed.

    Returns True when the file was written.
    """
    target = Path(path)
    existing = _read_text(target)
    if existing is not None and strip_volatile_lines(existing, marker) == strip_volatile_lines(
        text, marker
    ):
        return False
    _write_text(target, text)
    return True


def write_json_if_changed(
    path: Path | str,
    payload: dict[str, Any],
    *,
    volatile_keys: tuple[str, ...] = VOLATILE_JSON_KEYS,
) -> bool:
    """Write a JSON file only when its meaningful content changed.

    Top-level ``volatile_keys`` (the run timestamp) are excluded from the
    comparison but still written when a real change is being saved.
    """
    target = Path(path)
    text = dumps_json(payload)
    existing = _read_text(target)
    if existing is not None:
        try:
            old = json.loads(existing)
        except json.JSONDecodeError:
            old = None
        if isinstance(old, dict):
            trimmed_old = {k: v for k, v in old.items() if k not in volatile_keys}
            trimmed_new = {k: v for k, v in payload.items() if k not in volatile_keys}
            if trimmed_old == trimmed_new:
                return False
    _write_text(target, text)
    return True
