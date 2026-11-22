"""The orchestrator: starts analyses in the background and answers about them.

`start` registers the analysis, returns its random identifier at once and runs
the work as an asyncio task: fetch the sources within the time budget, freeze
the crop history, build the Report, store it together with its source data.
`derive` builds another Report from the source data stored with a finished
one, with another crop history and without fetching anything.
Clock and randomness live here and in the adapters, never in the engine.

Progress of a running analysis is kept in memory; the final state is in the
database. An analysis found unfinished in the database after a process restart
is closed as failed (`recover`), so nothing stays "running" forever. This
assumes one service process per database file.
"""

import asyncio
import logging
import secrets
import time
from collections.abc import Callable
from datetime import UTC, date, datetime

from app.catalog.crops import get_crop
from app.contracts.analyses import AnalysisRequest, AnalysisStatus, CropHistory
from app.contracts.report import Report
from app.orchestrator import params
from app.orchestrator.fetching import AnalysisFailed, fetch_source_data
from app.orchestrator.progress import Progress
from app.orchestrator.report_builder import ReportInputs, build_report
from app.orchestrator.report_summary import Summarizer, summarised
from app.orchestrator.sources import AnalysisSources
from app.storage.reports import AnalysisRecord, ReportStore

logger = logging.getLogger("hydromiara.analysis")


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_report_id() -> str:
    """Random, unguessable identifier: the only key to a Report."""
    return secrets.token_urlsafe(params.REPORT_ID_BYTES)


class Orchestrator:
    def __init__(
        self,
        store: ReportStore,
        *,
        clock: Callable[[], datetime] = utc_now,
        budget_s: float = params.ANALYSIS_BUDGET_S,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.store = store
        self._clock = clock
        self._fetch_budget_s = max(0.0, budget_s - params.COMPUTE_RESERVE_S)
        # The summary has to end this long after the end of the fetch budget.
        self._summary_margin_s = budget_s - params.SAVE_RESERVE_S - self._fetch_budget_s
        self._summarizer = summarizer or Summarizer()
        self._running: dict[str, Progress] = {}
        # Strong references: the event loop keeps only weak ones to its tasks.
        self._tasks: set[asyncio.Task] = set()

    @property
    def running_count(self) -> int:
        return len(self._running)

    async def recover(self) -> int:
        """Close analyses left unfinished by a previous process; returns how many."""
        code = "analysis_interrupted"
        return await asyncio.to_thread(
            self.store.fail_unfinished, code, params.FAILURES[code], self._clock()
        )

    async def purge(self) -> int:
        """Delete Reports older than the retention time; returns how many."""
        return await asyncio.to_thread(self.store.purge_expired, self._clock())

    async def start(
        self,
        request: AnalysisRequest,
        sources: AnalysisSources,
        *,
        changed_from_date: date | None = None,
        crop_history: CropHistory | None = None,
    ) -> str:
        """Register the analysis and run it in the background; returns its identifier.

        `changed_from_date` is the analysis date of the Report this analysis was
        started from with another date; it is written into the new Report.
        `crop_history` is the history the analysis starts with; the user can
        still replace it while the analysis runs.
        """
        report_id = new_report_id()
        progress = Progress(sources.specs)
        await asyncio.to_thread(
            self.store.create, report_id, request, progress.snapshot(), self._clock(),
            crop_history,
        )
        self._running[report_id] = progress
        task = asyncio.create_task(
            self._run(report_id, request, sources, progress, changed_from_date)
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return report_id

    async def _run(
        self,
        report_id: str,
        request: AnalysisRequest,
        sources: AnalysisSources,
        progress: Progress,
        changed_from_date: date | None = None,
    ) -> None:
        tag = report_id[: params.LOG_ID_CHARS]
        started = time.monotonic()
        logger.info(
            "analysis %s started parcel=%s crop=%s date=%s",
            tag, request.parcel_id, request.crop_id, request.analysis_date.isoformat(),
        )
        state = "done"
        try:
            await self._analyse(report_id, request, sources, progress, tag, changed_from_date)
        except AnalysisFailed as failure:
            state = failure.code
            await self._fail(report_id, failure, progress)
        except TimeoutError:
            state = "analysis_timeout"
            await self._fail(report_id, AnalysisFailed(state), progress)
        except Exception:
            state = "analysis_failed"
            logger.exception("analysis %s failed unexpectedly", tag)
            await self._fail(report_id, AnalysisFailed(state), progress)
        finally:
            self._running.pop(report_id, None)
        logger.info(
            "analysis %s finished state=%s total_s=%.3f", tag, state, time.monotonic() - started
        )

    async def _analyse(
        self,
        report_id: str,
        request: AnalysisRequest,
        sources: AnalysisSources,
        progress: Progress,
        tag: str,
        changed_from_date: date | None = None,
    ) -> None:
        deadline = time.monotonic() + self._fetch_budget_s
        async with asyncio.timeout(self._fetch_budget_s):
            source_data, limitations = await fetch_source_data(
                sources, request.parcel_id.strip(), request.analysis_date, progress, tag,
                deadline,
            )
        # From here on a crop history sent by the user is answered with "too late".
        history = await asyncio.to_thread(self.store.begin_finalize, report_id)
        inputs = ReportInputs(
            report_id=report_id,
            created_at=self._clock(),
            source_data=source_data,
            crop=get_crop(request.crop_id),
            analysis_date=request.analysis_date,
            crop_history=history,
            source_limitations=tuple(limitations),
            changed_from_date=changed_from_date,
        )
        computed = time.monotonic()
        report = await asyncio.to_thread(build_report, inputs)
        logger.info("analysis %s engine duration_s=%.3f", tag, time.monotonic() - computed)
        time_left_s = deadline + self._summary_margin_s - time.monotonic()
        report = await summarised(report, self._summarizer, time_left_s, tag)
        progress.close()
        await asyncio.to_thread(
            self.store.save_report,
            report, source_data, limitations, progress.snapshot(), self._clock(),
        )

    async def _fail(self, report_id: str, failure: AnalysisFailed, progress: Progress) -> None:
        progress.close()
        await asyncio.to_thread(
            self.store.save_failure,
            report_id, failure.code, failure.message, progress.snapshot(), self._clock(),
        )

    async def record(self, report_id: str) -> AnalysisRecord | None:
        """The analysis as stored; None when unknown or past the retention time."""
        return await asyncio.to_thread(self.store.get, report_id, self._clock())

    async def status(self, report_id: str) -> AnalysisStatus | None:
        progress = self._running.get(report_id)
        if progress is not None:
            return AnalysisStatus(state="running", sources=progress.snapshot())
        record = await self.record(report_id)
        if record is None:
            return None
        state = record.state if record.finished else "running"
        return AnalysisStatus(state=state, sources=record.sources)

    async def report_json(self, report_id: str) -> str | None:
        """The stored Report, byte for byte; reading never computes anything."""
        return await asyncio.to_thread(self.store.report_json, report_id, self._clock())

    async def put_crop_history(self, report_id: str, history: CropHistory) -> bool:
        """Attach the crop history to a running analysis; False when it is too late."""
        return await asyncio.to_thread(self.store.set_crop_history, report_id, history)

    async def derive(self, source_id: str, history: CropHistory) -> str | None:
        """A new Report from the stored data of a finished one, with another history.

        Nothing is fetched and the source Report is not touched. Returns the
        new identifier, or None when the source has no stored data (any more).
        """
        started = time.monotonic()
        return await asyncio.to_thread(self._derive, source_id, history, started)

    def _derive(self, source_id: str, history: CropHistory, started: float) -> str | None:
        now = self._clock()
        stored = self.store.inputs(source_id, now)
        source_json = self.store.report_json(source_id, now)
        if stored is None or source_json is None:
            return None
        record = stored.record
        inputs = ReportInputs(
            report_id=new_report_id(),
            created_at=now,
            source_data=stored.source_data,
            crop=get_crop(record.crop_id),
            analysis_date=record.analysis_date,
            crop_history=history,
            source_limitations=tuple(stored.source_limitations),
            derived_from=source_id,
            changed_from_date=Report.model_validate_json(source_json).meta.changed_from_date,
        )
        if not self.store.save_derived(build_report(inputs), source_id, history, now):
            return None
        logger.info(
            "report %s derived from %s duration_s=%.3f",
            inputs.report_id[: params.LOG_ID_CHARS], source_id[: params.LOG_ID_CHARS],
            time.monotonic() - started,
        )
        return inputs.report_id

    async def shutdown(self) -> None:
        """Stop running analyses; the next start closes them as interrupted."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
