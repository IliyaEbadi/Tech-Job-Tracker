"""One place to configure logging.

Log lines use ``key=value`` pairs (``source_collected source=lever jobs=12``)
so they stay readable in a terminal and remain easy to grep in the GitHub
Actions log.
"""

from __future__ import annotations

import logging
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Send structured logs to stderr so stdout stays free for run output."""
    level = logging.DEBUG if verbose else logging.WARNING if quiet else logging.INFO
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # The HTTP libraries are chatty at DEBUG level and add nothing here.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
