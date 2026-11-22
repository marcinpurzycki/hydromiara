"""Running ordinary analyses through the service routes, a few at a time at most.

Every analysis is the same request the web application sends: start, follow
the status until it is no longer running, read the Report. An analysis that
is refused, fails or cannot be followed gives a result with the reason; it
never stops the others.
"""

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from analysis_tools.inputs import InputRow
from analysis_tools.pacing import DailyAllowanceUsed, Pace
from analysis_tools.service import Service
from app.contracts.report import Report
from app.contracts.source_data import SourceOutcome
from app.orchestrator.params import ANALYSIS_BUDGET_S

DEFAULT_POLL_S = 0.25
# An analysis the service does not end by itself is given up after this long.
GIVE_UP_S = 2 * ANALYSIS_BUDGET_S

DONE = "done"
FAILED = "failed"


@dataclass
class AnalysisResult:
    """What one analysis gave: a Report with its timings, or the reason it gave none."""

    row: InputRow
    started_at: datetime
    state: str = FAILED
    failure: str = ""
    total_s: float | None = None
    report: Report | None = None
    report_json: dict | None = None
    status: dict | None = None
    # Outcome of every source as stored with the Report; empty over HTTP.
    outcomes: list[SourceOutcome] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return self.state == DONE


@dataclass
class _Active:
    result: AnalysisResult
    report_id: str
    started: float


def _error_text(response: httpx.Response) -> str:
    """`code: message` of an error answer of the service, or its plain text."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and "code" in body:
        return f"{body['code']}: {body.get('message', '')}".strip()
    return f"HTTP {response.status_code}: {response.text[:200]}"


def _start(service: Service, row: InputRow) -> _Active | AnalysisResult:
    result = AnalysisResult(row=row, started_at=datetime.now(UTC))
    request = {
        "parcel_id": row.parcel_id,
        "crop_id": row.crop_id,
        "analysis_date": row.analysis_date.isoformat(),
    }
    started = time.monotonic()
    try:
        response = service.client.post("/api/analyses", json=request)
    except httpx.HTTPError as problem:
        result.failure = f"service_unreachable: {type(problem).__name__}"
        return result
    if response.status_code != 202:
        result.failure = f"not_accepted: {_error_text(response)}"
        return result
    return _Active(result=result, report_id=response.json()["report_id"], started=started)


def _stored_outcomes(service: Service, report_id: str) -> list[SourceOutcome]:
    if service.store is None:
        return []
    stored = service.store.inputs(report_id, datetime.now(UTC))
    return [] if stored is None else list(stored.source_data.outcomes)


def _finish(service: Service, active: _Active, status: dict) -> AnalysisResult:
    result = active.result
    result.status = status
    answer = service.client.get(f"/api/reports/{active.report_id}")
    if answer.status_code != 200:
        result.failure = _error_text(answer)
        return result
    result.report_json = answer.json()
    try:
        result.report = Report.model_validate(result.report_json)
    except ValidationError as problem:
        result.failure = f"report_not_readable: {problem.error_count()} validation errors"
        return result
    result.outcomes = _stored_outcomes(service, active.report_id)
    result.state = DONE
    return result


def _poll(service: Service, active: _Active) -> AnalysisResult | None:
    """The result when the analysis has ended (or is given up), else None."""
    result = active.result
    try:
        response = service.client.get(f"/api/analyses/{active.report_id}/status")
        elapsed = time.monotonic() - active.started
        if response.status_code != 200:
            result.total_s = elapsed
            result.failure = f"status_unavailable: {_error_text(response)}"
            return result
        status = response.json()
        if status["state"] == "running":
            if elapsed <= GIVE_UP_S:
                return None
            result.total_s, result.status = elapsed, status
            result.failure = f"gave_up: still running after {GIVE_UP_S:.0f} s"
            return result
        result.total_s = elapsed
        return _finish(service, active, status)
    except httpx.HTTPError as problem:
        result.total_s = time.monotonic() - active.started
        result.failure = f"service_unreachable: {type(problem).__name__}"
        return result


def run_analyses(
    service: Service,
    rows: Sequence[InputRow],
    pace: Pace,
    *,
    concurrency: int = 1,
    poll_s: float = DEFAULT_POLL_S,
    announce: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[AnalysisResult]:
    """Run the analyses in order, at most `concurrency` at a time; results as they end.

    Starts are spaced and capped by `pace`. May raise `DailyAllowanceUsed`
    from the pace; analyses already running are then left to the service.
    The total time has the resolution of `poll_s`.
    """
    waiting = list(rows)
    active: list[_Active] = []
    while waiting or active:
        if waiting and len(active) < max(1, concurrency):
            if not active:
                pace.acquire(announce)
                ready = True
            else:
                try:
                    ready = pace.wait_s() == 0
                except DailyAllowanceUsed:
                    # Raised again by `acquire` once the running analyses have ended.
                    ready = False
                if ready:
                    pace.started()
            if ready:
                row = waiting.pop(0)
                announce(f"analysing {row.name}")
                begun = _start(service, row)
                if isinstance(begun, AnalysisResult):
                    yield begun
                else:
                    active.append(begun)
                continue
        sleep(poll_s)
        for item in list(active):
            ended = _poll(service, item)
            if ended is not None:
                active.remove(item)
                yield ended
