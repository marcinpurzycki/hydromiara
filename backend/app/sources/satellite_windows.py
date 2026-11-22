"""Work on the search windows of the satellite adapter with one service.

Order of work: every window is searched; one scene per acquisition day is
kept, always on the same tile; the scene classification of every such day is
read; the bands are read only for the clear days a window may use. Windows
are worked on at the same time, the current one with reading threads of its
own. Each finished scene is recorded at once, so that work cut short by the
time limit keeps what it has.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from app.contracts.source_data import SatelliteScene
from app.sources import satellite_params as params
from app.sources.satellite_indices import (
    ClearCheck,
    RasterOpener,
    SceneReadError,
    check_clear,
    compute_indices,
    read_layer,
)
from app.sources.satellite_limitations import WindowState
from app.sources.satellite_outline import ParcelOutline
from app.sources.satellite_providers import Provider
from app.sources.satellite_search import SatelliteSearchError, SceneItem, find_scenes
from app.sources.satellite_selection import by_preference, main_tile, one_per_day

# Runs a blocking function in a worker thread.
Runner = Callable[..., "asyncio.Future[Any]"]


def check_scene(opener: RasterOpener, item: SceneItem, geometry: Any) -> ClearCheck | None:
    """Clear-pixel check of one scene; None when its classification cannot be read."""
    try:
        return check_clear(opener, item.hrefs[params.ASSET_SCL], geometry)
    except SceneReadError:
        return None


async def measure(
    run: Runner, opener: RasterOpener, item: SceneItem, check: ClearCheck, geometry: Any
) -> SatelliteScene | None:
    """Read the bands of a scene that passed the check and compute its indices.

    Only the bands of an index the parcel has enough pixels for are read.
    None when a file cannot be read or the scene gives no index.
    """
    wanted: list[tuple[str, float] | None] = [None] * 4
    if check.ndvi_possible:
        wanted[0] = (params.ASSET_RED, params.FINE_BUFFER_M)
        wanted[1] = (params.ASSET_NIR, params.FINE_BUFFER_M)
    if check.ndmi_possible:
        wanted[2] = (params.ASSET_NIR_NARROW, params.COARSE_BUFFER_M)
        wanted[3] = (params.ASSET_SWIR, params.COARSE_BUFFER_M)

    def read(layer: str, buffer_m: float) -> Any:
        return read_layer(opener, item.hrefs[layer], geometry, buffer_m=buffer_m)

    reads = [run(read, *band) for band in wanted if band is not None]
    results = await asyncio.gather(*reads, return_exceptions=True)
    for result in results:
        if isinstance(result, SceneReadError):
            return None
        if isinstance(result, BaseException):
            raise result
    layers = iter(results)
    bands = [None if band is None else next(layers) for band in wanted]
    try:
        indices = compute_indices(check.window, *bands, item.reflectance_offset)
    except SceneReadError:
        return None
    if indices.ndvi is None and indices.ndmi is None:
        return None
    return SatelliteScene(
        date=item.date,
        clear_share_pct=check.clear_share_pct,
        ndvi=indices.ndvi,
        ndmi=indices.ndmi,
    )


async def work_window(
    state: WindowState, days: list[SceneItem], run: Runner, opener: RasterOpener, geometry: Any
) -> None:
    """Classify every day of one window and read its preferred clear scenes into `state`.

    The classification of every day is queued at once, the preferred day
    first. Results are taken in that order, and the bands of a clear scene are
    queued as soon as it is known to be among the scenes the window may use,
    so a slow file holds back only the days after it.
    """
    if not days:
        state.status = "no_scenes"
        return
    ordered = by_preference(state.window, days)
    checks = [run(check_scene, opener, item, geometry) for item in ordered]
    reads: list[asyncio.Future[None]] = []
    spare: list[tuple[SceneItem, ClearCheck]] = []  # clear scenes beyond the quota

    async def record(item: SceneItem, check: ClearCheck) -> None:
        scene = await measure(run, opener, item, check, geometry)
        if scene is not None:
            state.scenes.append(scene)

    try:
        for item, pending in zip(ordered, checks, strict=True):
            check = await pending
            if check is None or not check.passes:
                if check is not None and check.empty_reason == "parcel_too_small":
                    state.status = "too_small"
                    return
                continue
            state.ndmi_missing = state.ndmi_missing or not check.ndmi_possible
            if len(reads) < state.window.quota:
                reads.append(asyncio.ensure_future(record(item, check)))
            else:
                spare.append((item, check))
        await asyncio.gather(*reads)
        while len(state.scenes) < state.window.quota and spare:
            # A scene that failed is replaced by the next preferred clear one.
            batch = spare[: state.window.quota - len(state.scenes)]
            del spare[: len(batch)]
            await asyncio.gather(*(record(*chosen) for chosen in batch))
        state.status = "found" if state.scenes else "no_clear"
    finally:
        for read in reads:  # nothing is left running when the time limit cuts the work
            read.cancel()


async def work_windows(
    states: list[WindowState],
    client: httpx.AsyncClient,
    run_current: Runner,
    run_earlier: Runner,
    opener: RasterOpener,
    geometry: dict[str, Any],
    provider: Provider,
    token: str | None,
) -> None:
    """Search all windows of one service, then read them at the same time.

    Windows that end before the archive of the service begins are not asked.
    The current window reads with `run_current`, the windows of earlier years
    share `run_earlier`, so that the earlier years never hold the current
    window back.
    """
    asked = []
    for state in states:
        if state.window.end < provider.archive_start:
            state.status = "before_archive"
        else:
            asked.append(state)

    async def search(state: WindowState) -> list[SceneItem] | None:
        try:
            return await find_scenes(client, provider, geometry, state.window, token)
        except SatelliteSearchError:
            state.status = "search_failed"
            return None

    found = await asyncio.gather(*(search(state) for state in asked))
    tile = main_tile(item for items in found if items for item in items)
    outline = ParcelOutline(geometry)
    await asyncio.gather(
        *(
            work_window(
                state,
                one_per_day(items, tile),
                run_current if state.window.current else run_earlier,
                opener,
                outline,
            )
            for state, items in zip(asked, found, strict=True)
            if items is not None
        )
    )
