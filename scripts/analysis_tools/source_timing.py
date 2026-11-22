"""Timing the data sources: each on its own, and inside a whole analysis.

"Isolated" is one round for a parcel and a date in which the parcel service
and then every connected source is called alone, one after another, through
the same adapters, with the same time limits and by the same function the
analysis uses. "Analysis" is an ordinary whole analysis, where the sources
run in parallel; its source times are the ones stored with the Report.

Every measurement is one row: which source, how long, whether data arrived,
the time limit that applied. The first round of a parcel and date is marked
`first`, later rounds `repeat`, so a cold call can be told from a warm one.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from analysis_tools.inputs import InputRow
from analysis_tools.runner import AnalysisResult
from analysis_tools.service import RunInfo, timestamp
from app.orchestrator.fetching import AnalysisFailed, fetch_one, fetch_parcel
from app.orchestrator.params import ANALYSIS_BUDGET_S
from app.orchestrator.progress import Progress
from app.orchestrator.sources import AnalysisSources, FetchContext, get_analysis_sources
from app.orchestrator.sources import get_optional_sources, get_weather_source
from app.sources.parcels import get_parcel_source

ISOLATED = "isolated"
ANALYSIS = "analysis"
# The row of a whole analysis among the rows of its sources.
ANALYSIS_TOTAL = "analysis_total"
FIRST, REPEAT = "first", "repeat"
LOG_TAG = "timing"

KEY_COLUMNS = ("parcel_id", "crop_id", "analysis_date", "repeat", "phase")
COLUMNS = (
    "label", "region", *KEY_COLUMNS,
    "call", "source", "ok", "duration_s", "limit_s", "within_limit",
    "chain_step", "source_name", "data_date", "fetched_at", "message",
    "started_at", "mode", "host", "code_version",
)  # fmt: skip


@dataclass(frozen=True)
class Timing:
    """One measured call (or one whole analysis)."""

    source: str
    ok: bool
    duration_s: float | None
    limit_s: float | None
    chain_step: int | None = None
    source_name: str | None = None
    data_date: str | None = None
    fetched_at: datetime | None = None
    message: str | None = None

    @property
    def within_limit(self) -> bool | None:
        if self.duration_s is None or self.limit_s is None:
            return None
        return self.ok and self.duration_s <= self.limit_s


def application_sources() -> AnalysisSources:
    """The sources a new analysis of the application would use right now."""
    from app.main import app

    def resolve(dependency):
        return app.dependency_overrides.get(dependency, dependency)()

    return get_analysis_sources(
        resolve(get_parcel_source), resolve(get_weather_source), resolve(get_optional_sources)
    )


def source_limits(sources: AnalysisSources) -> dict[str, float]:
    """Time limit of every connected source, of the parcel and of a whole analysis."""
    limits = {spec.topic: spec.timeout_s for spec in sources.specs if spec.connected}
    limits["parcel"] = sources.parcel_timeout_s
    limits[ANALYSIS_TOTAL] = ANALYSIS_BUDGET_S
    return limits


def _from_outcome(outcome, duration_s: float | None, limit_s: float | None) -> Timing:
    return Timing(
        source=outcome.topic,
        ok=outcome.ok,
        duration_s=duration_s,
        limit_s=limit_s,
        chain_step=outcome.chain_step,
        source_name=outcome.source_name,
        data_date=outcome.data_date,
        fetched_at=outcome.fetched_at,
        message=outcome.message,
    )


async def measure_isolated(sources: AnalysisSources, row: InputRow) -> list[Timing]:
    """Call the parcel service and then every connected source, one at a time.

    Without the parcel nothing else can be asked, so only its row is returned.
    """
    limits = source_limits(sources)
    started = time.monotonic()
    try:
        parcel, outcome = await fetch_parcel(sources, row.parcel_id, LOG_TAG)
    except AnalysisFailed as failure:
        return [
            Timing(
                source="parcel",
                ok=False,
                duration_s=round(time.monotonic() - started, 3),
                limit_s=limits["parcel"],
                fetched_at=datetime.now(UTC),
                message=failure.detail or failure.message,
            )
        ]
    timings = [_from_outcome(outcome, round(time.monotonic() - started, 3), limits["parcel"])]
    context = FetchContext(parcel=parcel, analysis_date=row.analysis_date)
    progress = Progress(sources.specs)
    for spec in sources.specs:
        if not spec.connected:
            continue
        started = time.monotonic()
        fetched = await fetch_one(spec, context, progress, LOG_TAG)
        duration_s = round(time.monotonic() - started, 3)
        timings.append(_from_outcome(fetched.outcome, duration_s, spec.timeout_s))
    return timings


def analysis_timings(result: AnalysisResult, limits: dict[str, float]) -> list[Timing]:
    """The whole analysis and, when its source data can be read, each source in it."""
    timings = [
        Timing(
            source=ANALYSIS_TOTAL,
            ok=result.done,
            duration_s=None if result.total_s is None else round(result.total_s, 3),
            limit_s=limits.get(ANALYSIS_TOTAL),
            message=result.failure or None,
        )
    ]
    if result.outcomes:
        timings.extend(
            _from_outcome(outcome, outcome.duration_s, limits.get(outcome.topic))
            for outcome in result.outcomes
        )
    elif result.report is not None:
        # Over HTTP only whether each source gave data is known, not its time.
        for source in result.report.sources:
            timings.append(
                Timing(
                    source=source.topic,
                    ok=not source.missing,
                    duration_s=None,
                    limit_s=limits.get(source.topic),
                    chain_step=None if source.missing else source.chain_step,
                    source_name=source.name,
                    data_date=source.data_date,
                    fetched_at=source.fetched_at,
                )
            )
    return timings


def timing_rows(
    row: InputRow,
    repeat: int,
    phase: str,
    started_at: datetime,
    timings: list[Timing],
    run: RunInfo,
) -> list[dict[str, object]]:
    """The measurements of one round as rows of the output file."""
    shared = {
        "label": row.label,
        "region": row.region,
        "parcel_id": row.parcel_id,
        "crop_id": row.crop_id,
        "analysis_date": row.analysis_date.isoformat(),
        "repeat": repeat,
        "phase": phase,
        "call": FIRST if repeat == 1 else REPEAT,
        "started_at": timestamp(started_at),
        "mode": run.mode,
        "host": run.host,
        "code_version": run.code_version,
    }
    return [
        {
            **shared,
            "source": timing.source,
            "ok": timing.ok,
            "duration_s": timing.duration_s,
            "limit_s": timing.limit_s,
            "within_limit": timing.within_limit,
            "chain_step": timing.chain_step,
            "source_name": timing.source_name,
            "data_date": timing.data_date,
            "fetched_at": timestamp(timing.fetched_at),
            "message": timing.message,
        }
        for timing in timings
    ]
