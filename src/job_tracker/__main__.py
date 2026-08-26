"""Allow ``python -m job_tracker`` to run the CLI."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
