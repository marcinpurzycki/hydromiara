"""Work on one search window of the satellite adapter with one service.

The window is searched, the scene classification of its newest days is read
and the bands are read only for days with enough clear pixels over the parcel.
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
    check_day,
    compute_indices,
    read_layer,
)
from app.sources.satellite_limitations import WindowState
from app.sources.satellite_providers import Provider
from app.sources.satellite_search import SatelliteSearchError, SceneItem, find_scenes

# Runs a blocking function in a worker thread.
Runner = Callable[..., "asyncio.Future[Any]"]


async def measure(
    run: Runner, opener: RasterOpener, item: SceneItem, check: ClearCheck, geometry: dict[str, Any]
) -> SatelliteScene | None:
    """Read the bands of a scene that passed the check and compute its indices."""
    reads = [
        run(read_layer, opener, item.hrefs[params.ASSET_RED], geometry),
        run(read_layer, opener, item.hrefs[params.ASSET_NIR], geometry),
        run(
            lambda: read_layer(
                opener,
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
        indices = compute_indices(check.window, *results, item.reflectance_offset)
    except SceneReadError:
        return None
    return SatelliteScene(
        date=item.date,
        clear_share_pct=check.clear_share_pct,
        ndvi=indices.ndvi,
        ndmi=indices.ndmi,
    )


async def work_window(
    state: WindowState,
    client: httpx.AsyncClient,
    run: Runner,
    opener: RasterOpener,
    geometry: dict[str, Any],
    provider: Provider,
    token: str | None,
) -> None:
    """Search one window and read its newest clear scenes into `state`."""
    try:
        days = await find_scenes(client, provider, geometry, state.window, token)
    except SatelliteSearchError:
        state.status = "search_failed"
        return
    if not days:
        state.status = "no_scenes"
        return
    for start in range(0, len(days), params.SCL_BATCH_SIZE):
        batch = days[start : start + params.SCL_BATCH_SIZE]
        checked = await asyncio.gather(
            *(run(check_day, opener, copies, geometry) for copies in batch)
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
            scene = await measure(run, opener, item, check, geometry)
            if scene is not None:
                state.scenes.append(scene)
            if len(state.scenes) >= params.SCENES_PER_WINDOW:
                state.status = "found"
                return
    state.status = "found" if state.scenes else "no_clear"
