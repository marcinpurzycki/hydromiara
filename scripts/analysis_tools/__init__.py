"""Shared parts of the backtest and source timing tools.

Importing this package makes the application package `app` importable: the
tools run the analysis with the application's own code. The application is
looked for next to the `scripts` directory, in `backend/` (a checkout) or
directly beside it (the service image, where the application lives in `/srv`).
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = SCRIPTS_DIR.parent


def application_dir() -> Path | None:
    """Directory that holds the `app` package, or None when it is not found."""
    for candidate in (REPOSITORY_DIR / "backend", REPOSITORY_DIR):
        if (candidate / "app" / "main.py").is_file():
            return candidate
    return None


_found = application_dir()
if _found is not None and str(_found) not in sys.path:
    sys.path.insert(0, str(_found))
