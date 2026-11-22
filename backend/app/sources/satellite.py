"""Sentinel-2 readings over a parcel: NDVI and NDMI of clear scenes.

For each search window (the days before the analysis date and the same time
of the year in earlier years) the adapter finds the scenes, reads the scene
classification of each acquisition day, and reads the bands only of scenes
with enough clear pixels over the parcel. Windows are worked on at the same
time and raster reads run in worker threads. The whole call has a time
budget; when it runs out, the scenes finished so far are returned and the
rest is reported as a limitation. No scene after the analysis date is used.

The windows of earlier years are always read: the adapter does not know the
crop history, and the engine decides which of those years may be compared.

Two interchangeable services hold the scenes. The primary one is asked
first; when it delivers no reading within the fallback time, its work is
dropped and the secondary one is asked with the time that is left.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from datetime import date as Date
from typing import Any, NamedTuple

import httpx

from app.contracts.common import GeoJsonGeometry
from app.contracts.report import Limitation
from app.contracts.source_data import SatelliteData, SourceOutcome
from app.sources import satellite_params as params
from app.sources.satellite_indices import RasterOpener, open_remote
from app.sources.satellite_limitations import WindowState, find_limitations, gave_no_result
from app.sources.satellite_providers import (
    Provider,
    configured_chain,
    configured_fallback_after_s,
)
from app.sources.satellite_search import SatelliteSearchError, read_token, search_windows
from app.sources.satellite_windows import work_windows


class SatelliteFetch(NamedTuple):
    """Satellite readings for one analysis, how they were obtained and what is missing."""

    data: SatelliteData | None
    outcome: SourceOutcome
    limitations: list[Limitation]


class SatelliteSource:
    """Clear Sentinel-2 scenes over a parcel, up to the analysis date."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        opener: RasterOpener = open_remote,
        time_budget_s: float = params.TIME_BUDGET_S,
        providers: Sequence[Provider] | None = None,
        fallback_after_s: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Without `providers` and `fallback_after_s` the project configuration applies.

        `clock` and `sleep` measure and wait out the time limits; tests replace them.
        """
        self._clock = clock
        self._sleep = sleep
        self._transport = transport
        self._opener = opener
        self._time_budget_s = time_budget_s
        self._providers = list(providers) if providers is not None else configured_chain()
        self._fallback_after_s = (
            configured_fallback_after_s() if fallback_after_s is None else fallback_after_s
        )
        self._tokens: dict[str, tuple[str, datetime]] = {}

    async def _token(self, client: httpx.AsyncClient, provider: Provider) -> str | None:
        """Read token of a service that needs one; kept until shortly before it expires."""
        if provider.token_url is None:
            return None
        kept = self._tokens.get(provider.name)
        if kept and kept[1] - datetime.now(UTC) > timedelta(seconds=params.TOKEN_MARGIN_S):
            return kept[0]
        self._tokens[provider.name] = await read_token(client, provider)
        return self._tokens[provider.name][0]

    async def _finished(self, task: "asyncio.Task[None]", timeout_s: float) -> bool:
        """Wait for the task at most `timeout_s`; True when it ended in that time."""
        timer = asyncio.ensure_future(self._sleep(timeout_s))
        try:
            await asyncio.wait({task, timer}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            timer.cancel()
        return task.done()

    async def _work(
        self,
        states: list[WindowState],
        geometry: dict[str, Any],
        provider: Provider,
        budget_s: float,
        first_reading_s: float | None,
    ) -> None:
        """Work on all windows at once with one service.

        Stops when the windows are done or `budget_s` runs out. With
        `first_reading_s`, stops already then unless a scene has been read.
        """
        started = self._clock()
        loop = asyncio.get_running_loop()
        # Half of the reading threads belong to the current window alone.
        own = max(1, provider.read_workers // 2)
        executors = [
            ThreadPoolExecutor(max_workers=workers, thread_name_prefix="satellite")
            for workers in (own, max(1, provider.read_workers - own))
        ]

        def runner(executor: ThreadPoolExecutor) -> Callable[..., "asyncio.Future[Any]"]:
            return lambda function, *args: loop.run_in_executor(executor, function, *args)

        def left(limit_s: float) -> float:
            return max(0.0, limit_s - (self._clock() - started))

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=min(params.SEARCH_TIMEOUT_S, first_reading_s or budget_s, budget_s),
                headers={"User-Agent": params.USER_AGENT},
            ) as client:
                try:
                    token = await self._token(client, provider)
                except SatelliteSearchError:
                    for state in states:
                        state.status = "search_failed"
                    return
                task = asyncio.create_task(
                    work_windows(
                        states, client, *map(runner, executors), self._opener, geometry,
                        provider, token,
                    )  # fmt: skip
                )
                first_wait = left(min(first_reading_s or budget_s, budget_s))
                done = await self._finished(task, first_wait)
                if not done and first_reading_s and any(state.scenes for state in states):
                    done = await self._finished(task, left(budget_s))
                if not done:
                    task.cancel()
                (result,) = await asyncio.gather(task, return_exceptions=True)
        finally:
            # Reads already running end on their own timeouts; queued ones are dropped.
            for executor in executors:
                executor.shutdown(wait=False, cancel_futures=True)
        if isinstance(result, Exception):
            raise result

    async def fetch(self, geometry: GeoJsonGeometry, analysis_date: Date) -> SatelliteFetch:
        """Satellite readings for an analysis: scenes, outcome record and what is missing.

        Scenes are ordered by date, oldest first.
        """
        started = self._clock()
        outline = geometry.model_dump()
        states: list[WindowState] = []
        used, step = self._providers[0], 1
        for position, provider in enumerate(self._providers, start=1):
            budget_left = self._time_budget_s - (self._clock() - started)
            if position > 1 and budget_left <= 0:
                break  # no time for the next service; keep what the last one reported
            is_last = position == len(self._providers)
            states = [WindowState(window=window) for window in search_windows(analysis_date)]
            used, step = provider, position
            await self._work(
                states, outline, provider, budget_left, None if is_last else self._fallback_after_s
            )
            if not gave_no_result(states):
                break

        scenes = sorted(
            (scene for state in states for scene in state.scenes), key=lambda scene: scene.date
        )
        limitations = find_limitations(states, self._time_budget_s, used.archive_note)
        data = SatelliteData(scenes=scenes) if scenes else None
        outcome = SourceOutcome(
            topic="satellite",
            source_name=used.source_name if data else None,
            chain_step=step if data else None,
            ok=data is not None,
            duration_s=round(self._clock() - started, 3),
            data_date=(
                f"{scenes[0].date.isoformat()}/{scenes[-1].date.isoformat()}" if data else None
            ),
            fetched_at=datetime.now(UTC),
            message=" ".join(limitation.text for limitation in limitations) or None,
        )
        return SatelliteFetch(data=data, outcome=outcome, limitations=limitations)
