"""In-memory stand-in for running analyses: progress is simulated with a timer."""

import secrets
import time

from app.contracts.analyses import AnalysisStatus, SourceId, SourceProgress
from app.mock.data import MOCK_REPORT_ID

# Source, seconds after start at which it finishes, note shown when finished.
_TIMELINE: list[tuple[SourceId, float, str | None]] = [
    ("weather", 1.0, None),
    ("soil", 2.5, None),
    ("terrain", 3.5, "Model terenu 30 m zamiast 1 m."),
    ("satellite", 5.0, None),
    ("hydro", 6.0, "Źródło nie odpowiedziało."),
]
_MISSING: set[SourceId] = {"hydro"}

# Multiplier for the timeline; tests set it to 0 to finish instantly.
speed = 1.0

_started: dict[str, float] = {}


def _elapsed(report_id: str) -> float | None:
    if report_id == MOCK_REPORT_ID:
        return float("inf")
    started = _started.get(report_id)
    return None if started is None else time.monotonic() - started


def start(finished: bool = False) -> str:
    """Register a new analysis and return its random report identifier."""
    report_id = secrets.token_urlsafe(16)
    _started[report_id] = float("-inf") if finished else time.monotonic()
    return report_id


def exists(report_id: str) -> bool:
    return _elapsed(report_id) is not None


def is_done(report_id: str) -> bool:
    elapsed = _elapsed(report_id)
    return elapsed is not None and elapsed >= _TIMELINE[-1][1] * speed


def status(report_id: str) -> AnalysisStatus | None:
    elapsed = _elapsed(report_id)
    if elapsed is None:
        return None
    sources = []
    for source_id, ends_at, note in _TIMELINE:
        if elapsed >= ends_at * speed:
            state = "missing" if source_id in _MISSING else "done"
            sources.append(SourceProgress(id=source_id, state=state, note=note))
        else:
            sources.append(SourceProgress(id=source_id, state="run"))
    state = "done" if is_done(report_id) else "running"
    return AnalysisStatus(state=state, sources=sources)
