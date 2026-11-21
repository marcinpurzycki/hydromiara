"""Sentinel-2 readings over a parcel: NDVI and NDMI of clear scenes.

For each search window (the weeks before the analysis date and the same
period of earlier years) the adapter finds the scenes, reads the scene
classification of the newest ones, and reads the bands only of scenes with
enough clear pixels over the parcel. Windows are worked on at the same time
and raster reads run in worker threads. The whole call has a time budget;
when it runs out, the scenes finished so far are returned and the rest is
reported as a limitation. No scene after the analysis date is used.
"""

import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from datetime import date as Date
from typing import Any, NamedTuple

import httpx

from app.contracts.common import GeoJsonGeometry
from app.contracts.report import Limitation
from app.contracts.source_data import SatelliteData, SatelliteScene, SourceOutcome
from app.sources import satellite_params as params
from app.sources.satellite_indices import (
    ClearCheck,
    RasterOpener,
    SceneReadError,
    check_clear,
    compute_indices,
    open_remote,
    read_layer,
)
from app.sources.satellite_limitations import WindowState, find_limitations
from app.sources.satellite_search import (
    SatelliteSearchError,
    SceneItem,
    find_scenes,
    search_windows,
)

# Runs a blocking function in a worker thread.
Runner = Callable[..., "asyncio.Future[Any]"]


class SatelliteFetch(NamedTuple):
    """Satellite readings for one analysis, how they were obtained and what is missing."""

    data: SatelliteData | None
    outcome: SourceOutcome
    limitations: list[Limitation]


def _check_day(
    opener: RasterOpener, copies: list[SceneItem], geometry: dict[str, Any]
) -> tuple[SceneItem, ClearCheck] | None:
    """Clear-pixel check of one acquisition day: the first copy covering the parcel."""
    for item in copies:
        try:
            check = check_clear(opener, item.hrefs[params.ASSET_SCL], geometry)
        except SceneReadError:
            continue
        if check.empty_reason in ("outside_raster", "no_valid_data"):
            continue  # the parcel lies off this tile; another copy may cover it
        return item, check
    return None


class SatelliteSource:
    """Clear Sentinel-2 scenes over a parcel, up to the analysis date."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        opener: RasterOpener = open_remote,
        time_budget_s: float = params.TIME_BUDGET_S,
    ) -> None:
        self._transport = transport
        self._opener = opener
        self._time_budget_s = time_budget_s

    async def _measure(
        self, run: Runner, item: SceneItem, check: ClearCheck, geometry: dict[str, Any]
    ) -> SatelliteScene | None:
        """Read the bands of a scene that passed the check and compute its indices."""
        reads = [
            run(read_layer, self._opener, item.hrefs[params.ASSET_RED], geometry),
            run(read_layer, self._opener, item.hrefs[params.ASSET_NIR], geometry),
            run(
                lambda: read_layer(
                    self._opener,
                    item.hrefs[params.ASSET_SWIR],
                    geometry,
                    margin_m=params.COARSE_MARGIN_M,
                )
            ),
        ]
        results = await asyncio.gather(*reads, return_exceptions=True)
        for result in results:
            if isinstance(result, SceneReadError):
                return None
            if isinstance(result, BaseException):
                raise result
        try:
            indices = compute_indices(check.window, *results)
        except SceneReadError:
            return None
        return SatelliteScene(
            date=item.date,
            clear_share_pct=check.clear_share_pct,
            ndvi=indices.ndvi,
            ndmi=indices.ndmi,
        )

    async def _work_window(
        self,
        state: WindowState,
        client: httpx.AsyncClient,
        run: Runner,
        geometry: dict[str, Any],
    ) -> None:
        """Search one window and read its newest clear scenes into `state`."""
        try:
            days = await find_scenes(client, geometry, state.window)
        except SatelliteSearchError:
            state.status = "search_failed"
            return
        if not days:
            state.status = "no_scenes"
            return
        for start in range(0, len(days), params.SCL_BATCH_SIZE):
            batch = days[start : start + params.SCL_BATCH_SIZE]
            checked = await asyncio.gather(
                *(run(_check_day, self._opener, copies, geometry) for copies in batch)
            )
            for found in checked:  # newest day first
                if found is None:
                    continue
                item, check = found
                if check.empty_reason == "parcel_too_small":
                    state.status = "too_small"
                    return
                if not check.passes:
                    continue
                scene = await self._measure(run, item, check, geometry)
                if scene is not None:
                    state.scenes.append(scene)
                if len(state.scenes) >= params.SCENES_PER_WINDOW:
                    state.status = "found"
                    return
        state.status = "found" if state.scenes else "no_clear"

    async def _work(self, states: list[WindowState], geometry: dict[str, Any]) -> None:
        """Work on all windows at once until they are done or the budget runs out."""
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(
            max_workers=params.READ_WORKERS, thread_name_prefix="satellite"
        )

        def run(function: Callable[..., Any], *args: Any) -> "asyncio.Future[Any]":
            return loop.run_in_executor(executor, function, *args)

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=min(params.SEARCH_TIMEOUT_S, self._time_budget_s),
                headers={"User-Agent": params.USER_AGENT},
            ) as client:
                tasks = [
                    asyncio.create_task(self._work_window(state, client, run, geometry))
                    for state in states
                ]
                _, pending = await asyncio.wait(tasks, timeout=self._time_budget_s)
                for task in pending:
                    task.cancel()
                results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Reads already running end on their own timeouts; queued ones are dropped.
            executor.shutdown(wait=False, cancel_futures=True)
        for result in results:
            if isinstance(result, Exception):
                raise result

    async def fetch(self, geometry: GeoJsonGeometry, analysis_date: Date) -> SatelliteFetch:
        """Satellite readings for an analysis: scenes, outcome record and what is missing.

        Scenes are ordered by date, oldest first.
        """
        started = time.monotonic()
        states = [WindowState(window=window) for window in search_windows(analysis_date)]
        await self._work(states, geometry.model_dump())

        scenes = sorted(
            (scene for state in states for scene in state.scenes), key=lambda scene: scene.date
        )
        limitations = find_limitations(states, self._time_budget_s)
        data = SatelliteData(scenes=scenes) if scenes else None
        outcome = SourceOutcome(
            topic="satellite",
            source_name=params.SOURCE_NAME if data else None,
            chain_step=1 if data else None,
            ok=data is not None,
            duration_s=round(time.monotonic() - started, 3),
            data_date=(
                f"{scenes[0].date.isoformat()}/{scenes[-1].date.isoformat()}" if data else None
            ),
            fetched_at=datetime.now(UTC),
            message=" ".join(limitation.text for limitation in limitations) or None,
        )
        return SatelliteFetch(data=data, outcome=outcome, limitations=limitations)
