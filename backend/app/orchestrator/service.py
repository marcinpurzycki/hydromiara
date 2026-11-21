"""The orchestrator: starts analyses in the background and answers about them.

`start` registers the analysis, returns its random identifier at once and runs
the work as an asyncio task: fetch the sources within the time budget, freeze
the crop history, build the Report, store it together with its source data.
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
from datetime import UTC, datetime

from app.catalog.crops import get_crop
from app.contracts.analyses import AnalysisRequest, AnalysisStatus, CropHistory
from app.orchestrator import params
from app.orchestrator.fetching import AnalysisFailed, fetch_source_data
from app.orchestrator.progress import Progress
from app.orchestrator.report_builder import ReportInputs, build_report
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
    ) -> None:
        self.store = store
        self._clock = clock
        self._fetch_budget_s = max(0.0, budget_s - params.COMPUTE_RESERVE_S)
        self._running: dict[str, Progress] = {}
        # Strong references: the event loop keeps only weak ones to its tasks.
        self._tasks: set[asyncio.Task] = set()

    async def recover(self) -> int:
        """Close analyses left unfinished by a previous process; returns how many."""
        code = "analysis_interrupted"
        return await asyncio.to_thread(
            self.store.fail_unfinished, code, params.FAILURES[code], self._clock()
        )

    async def purge(self) -> int:
        """Delete Reports older than the retention time; returns how many."""
        return await asyncio.to_thread(self.store.purge_expired, self._clock())

    async def start(self, request: AnalysisRequest, sources: AnalysisSources) -> str:
        """Register the analysis and run it in the background; returns its identifier."""
        report_id = new_report_id()
        progress = Progress(sources.specs)
        await asyncio.to_thread(
            self.store.create, report_id, request, progress.snapshot(), self._clock()
        )
        self._running[report_id] = progress
        task = asyncio.create_task(self._run(report_id, request, sources, progress))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return report_id

    async def _run(
        self,
        report_id: str,
        request: AnalysisRequest,
        sources: AnalysisSources,
        progress: Progress,
    ) -> None:
        tag = report_id[: params.LOG_ID_CHARS]
        started = time.monotonic()
        logger.info(
            "analysis %s started parcel=%s crop=%s date=%s",
            tag, request.parcel_id, request.crop_id, request.analysis_date.isoformat(),
        )
        state = "done"
        try:
            await self._analyse(report_id, request, sources, progress, tag)
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
    ) -> None:
        async with asyncio.timeout(self._fetch_budget_s):
            source_data, limitations = await fetch_source_data(
                sources, request.parcel_id.strip(), request.analysis_date, progress, tag
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
        )
        computed = time.monotonic()
        report = await asyncio.to_thread(build_report, inputs)
        logger.info("analysis %s engine duration_s=%.3f", tag, time.monotonic() - computed)
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

    async def shutdown(self) -> None:
        """Stop running analyses; the next start closes them as interrupted."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
