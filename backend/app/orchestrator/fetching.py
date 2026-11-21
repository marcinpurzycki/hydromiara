"""Fetching the source data of one analysis: the parcel, then the rest in parallel.

Every source has its own time limit and never stops the others: a source that
fails, raises or is too slow becomes a missing part with a recorded outcome.
Only a missing required source (the parcel, the weather) ends the analysis.
The duration of every source goes to the log.
"""

import asyncio
import logging
import time
from datetime import UTC, date, datetime

from app.contracts.report import Limitation
from app.contracts.source_data import ParcelData, SourceData, SourceOutcome
from app.orchestrator import params
from app.orchestrator.progress import Progress
from app.orchestrator.sources import AnalysisSources, FetchContext, SourceFetch, SourceSpec

logger = logging.getLogger("hydromiara.analysis")


class AnalysisFailed(Exception):
    """The analysis cannot produce a Report; `code` is a key of `params.FAILURES`."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail

    @property
    def message(self) -> str:
        base = params.FAILURES.get(self.code, params.FAILURES["analysis_failed"])
        return f"{base} {self.detail}" if self.detail else base


def _no_answer(spec: SourceSpec, started: float, message: str) -> SourceFetch:
    outcome = SourceOutcome(
        topic=spec.topic,
        source_name=None,
        chain_step=None,
        ok=False,
        duration_s=round(time.monotonic() - started, 3),
        data_date=None,
        fetched_at=datetime.now(UTC),
        message=message,
    )
    return SourceFetch(data=None, outcome=outcome)


def _log(tag: str, outcome: SourceOutcome) -> None:
    logger.info(
        "analysis %s source=%s ok=%s duration_s=%.3f",
        tag, outcome.topic, outcome.ok, outcome.duration_s,
    )


async def fetch_one(
    spec: SourceSpec, context: FetchContext, progress: Progress, tag: str
) -> SourceFetch:
    """One source within its own time limit; never raises for a source problem."""
    progress.set(spec.status_id, "run")
    started = time.monotonic()
    try:
        async with asyncio.timeout(spec.timeout_s):
            result = await spec.fetch(context)
    except TimeoutError:
        note = params.SOURCE_TIMEOUT_NOTE.format(seconds=spec.timeout_s)
        result = _no_answer(spec, started, note)
    except Exception as exc:  # a broken source must not break the analysis
        logger.warning("analysis %s source=%s raised %s", tag, spec.topic, type(exc).__name__)
        result = _no_answer(spec, started, params.SOURCE_ERROR_NOTE)
    _log(tag, result.outcome)
    state = "done" if result.data is not None else "missing"
    progress.set(spec.status_id, state, result.outcome.message)
    return result


async def fetch_parcel(
    sources: AnalysisSources, parcel_id: str, tag: str
) -> tuple[ParcelData, SourceOutcome]:
    try:
        async with asyncio.timeout(sources.parcel_timeout_s):
            parcel, outcome = await sources.parcels.fetch(parcel_id)
    except TimeoutError:
        raise AnalysisFailed(
            "parcel_unavailable", "Usługa lokalizacji działek nie odpowiedziała."
        ) from None
    _log(tag, outcome)
    if parcel is None:
        raise AnalysisFailed("parcel_unavailable", outcome.message)
    return parcel, outcome


async def fetch_source_data(
    sources: AnalysisSources,
    parcel_id: str,
    analysis_date: date,
    progress: Progress,
    tag: str,
) -> tuple[SourceData, list[Limitation]]:
    """Complete source data of an analysis and the limitations the sources reported."""
    parcel, parcel_outcome = await fetch_parcel(sources, parcel_id, tag)
    context = FetchContext(parcel=parcel, analysis_date=analysis_date)
    connected = [spec for spec in sources.specs if spec.connected]
    results = await asyncio.gather(
        *(fetch_one(spec, context, progress, tag) for spec in connected)
    )

    parts: dict[str, object] = {}
    limitations: list[Limitation] = []
    for spec, result in zip(connected, results, strict=True):
        if result.data is None and spec.required:
            raise AnalysisFailed(f"{spec.topic}_unavailable", result.outcome.message)
        parts[spec.topic] = result.data
        limitations.extend(result.limitations)
    outcomes = [parcel_outcome, *(result.outcome for result in results)]
    return SourceData(parcel=parcel, outcomes=outcomes, **parts), limitations
