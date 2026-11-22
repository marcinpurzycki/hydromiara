"""Point heights of the national 1 m terrain model as the first terrain link.

The GUGiK height service answers with the terrain height of listed points.
A regular grid of points is laid over the parcel and its margin, asked for in
batches of a few hundred points, several batches at a time, and returned as
an elevation grid in PL-1992 (EPSG:2180). Only point coordinates are sent out.

Reading rules, each from measurement of the service:
- a row without a third field has no height;
- a batch answered with heights of exactly 0.0 is a failed request, not
  ground at sea level, so a batch holding any zero is asked once more. A
  height stays 0.0 only when both answers say so and the batch is not zero
  throughout (low-lying ground repeats its zeros, a failed request does not);
  a batch that is zero throughout twice gives no heights;
- the link has data when enough of the points inside the parcel have a height.
"""

import asyncio
import math
from typing import NamedTuple

import httpx
from shapely import Point
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from app.contracts.source_data import TerrainData
from app.sources import terrain_params as params
from app.sources.raster import WGS84, reproject_geometry
from app.sources.terrain import TerrainLinkError, TerrainReading

Heights = list[float | None]

_TOO_SMALL = "działka za mała dla tego źródła"
_TOO_FEW = "usługa wysokości punktów nie podała wysokości dla {missing} z {inside} punktów działki"
_WIDER_STEP = (
    "Działka jest duża, więc wysokości terenu odczytano co {step} m zamiast co "
    f"{params.GUGIK_GRID_STEP_M} m."
)


class PointGrid(NamedTuple):
    """Regular grid of points in PL-1992, rows from north to south."""

    west: int  # easting of the first column
    north: int  # northing of the first row
    step: int  # spacing in metres
    cols: int
    rows: int

    def points(self) -> list[tuple[int, int]]:
        """(northing, easting) of every point, row by row from the north-west."""
        return [
            (self.north - row * self.step, self.west + col * self.step)
            for row in range(self.rows)
            for col in range(self.cols)
        ]

    @property
    def transform(self) -> tuple[float, float, float, float, float, float]:
        """Affine transform under which every point is the centre of its cell."""
        half = self.step / 2
        return (float(self.step), 0.0, self.west - half, 0.0, -float(self.step), self.north + half)


def point_grid(bounds: tuple[float, float, float, float]) -> PointGrid:
    """Grid of whole-metre points over the bounds (PL-1992) and their margin.

    The spacing is the standard one, or the smallest wider one at which the
    grid stays within the point limit.
    """
    min_e, min_n, max_e, max_n = bounds
    margin = params.WINDOW_MARGIN_M
    west, east = math.ceil(min_e - margin), math.floor(max_e + margin)
    south, north = math.ceil(min_n - margin), math.floor(max_n + margin)
    step = params.GUGIK_GRID_STEP_M
    while True:
        cols, rows = (east - west) // step + 1, (north - south) // step + 1
        if cols * rows <= params.GUGIK_MAX_POINTS:
            return PointGrid(west=west, north=north, step=step, cols=cols, rows=rows)
        step += 1


def request_url(points: list[tuple[int, int]]) -> str:
    """Address of one request: `x y` pairs, x being the northing, y the easting."""
    if len(points) > params.GUGIK_SERVICE_POINT_LIMIT:
        raise ValueError("more points than the service answers in one request")
    pairs = ",".join(f"{northing}%20{easting}" for northing, easting in points)
    return f"{params.GUGIK_URL}?request={params.GUGIK_REQUEST}&list={pairs}"


def parse_heights(text: str, expected: int) -> Heights | None:
    """Heights in the order of the request; None when the answer is not a point list."""
    rows = [row.split() for row in text.strip().split(",")]
    if len(rows) != expected:
        return None
    heights: Heights = []
    for fields in rows:
        if len(fields) == 2:  # no third field: the point has no height
            heights.append(None)
            continue
        try:
            height = float(fields[2]) if len(fields) == 3 else math.nan
        except ValueError:
            height = math.nan
        if not math.isfinite(height):
            return None
        heights.append(height)
    return heights


def _has_zero(heights: Heights) -> bool:
    return any(height == 0.0 for height in heights)


def _all_zero(heights: Heights) -> bool:
    known = [height for height in heights if height is not None]
    return bool(known) and all(height == 0.0 for height in known)


def settle(first: Heights | None, second: Heights | None) -> Heights | None:
    """Heights of a batch from its first answer and the repeated one."""
    good = [answer for answer in (first, second) if answer is not None and not _all_zero(answer)]
    if not good:
        return None
    if len(good) == 1:
        # The other answer failed, so the zeros of this one are not confirmed.
        return [None if height == 0.0 else height for height in good[0]]
    return [b if a is None or a == 0.0 else a for a, b in zip(*good, strict=True)]


def inside_flags(grid: PointGrid, outline_metric: BaseGeometry) -> list[bool]:
    parcel = prep(outline_metric)
    return [parcel.contains(Point(easting, northing)) for northing, easting in grid.points()]


class GugikPointHeights:
    """Elevation grid read every few metres from the 1 m terrain model."""

    name = params.GUGIK_SOURCE_NAME
    timeout_s = params.GUGIK_LINK_TIMEOUT_S

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def _ask(self, client: httpx.AsyncClient, batch: list[tuple[int, int]]) -> Heights | None:
        try:
            response = await client.get(request_url(batch))
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        return parse_heights(response.text, len(batch))

    async def _batch(
        self, client: httpx.AsyncClient, gate: asyncio.Semaphore, batch: list[tuple[int, int]]
    ) -> Heights:
        async with gate:
            first = await self._ask(client, batch)
            if first is not None and not _has_zero(first):
                return first
            settled = settle(first, await self._ask(client, batch))
        return [None] * len(batch) if settled is None else settled

    async def heights(self, points: list[tuple[int, int]]) -> Heights:
        """Height of every point, in order; None where the service gave none."""
        size = params.GUGIK_POINTS_PER_REQUEST
        batches = [points[start : start + size] for start in range(0, len(points), size)]
        gate = asyncio.Semaphore(params.GUGIK_PARALLEL_REQUESTS)
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=params.GUGIK_REQUEST_TIMEOUT_S,
            limits=httpx.Limits(max_connections=params.GUGIK_PARALLEL_REQUESTS),
            headers={"User-Agent": params.USER_AGENT},
        ) as client:
            answers = await asyncio.gather(*(self._batch(client, gate, batch) for batch in batches))
        return [height for answer in answers for height in answer]

    async def read(self, outline: BaseGeometry) -> TerrainReading:
        """Grid around the outline (EPSG:4326) in PL-1992."""
        outline_metric = reproject_geometry(outline, WGS84, params.GUGIK_CRS)
        grid = point_grid(outline_metric.bounds)
        inside = inside_flags(grid, outline_metric)
        if sum(inside) < params.GUGIK_MIN_POINTS_INSIDE:
            raise TerrainLinkError(_TOO_SMALL)
        heights = await self.heights(grid.points())
        wanted = sum(inside)
        known = sum(
            1
            for height, within in zip(heights, inside, strict=True)
            if within and height is not None
        )
        if known < params.GUGIK_MIN_SHARE_INSIDE * wanted:
            raise TerrainLinkError(_TOO_FEW.format(missing=wanted - known, inside=wanted))
        rows = [heights[start : start + grid.cols] for start in range(0, len(heights), grid.cols)]
        data = TerrainData(
            resolution_m=float(grid.step),
            crs=params.GUGIK_CRS,
            transform=grid.transform,
            elevations_m=rows,
        )
        wider = grid.step > params.GUGIK_GRID_STEP_M
        return TerrainReading(
            data=data, data_date=None, note=_WIDER_STEP.format(step=grid.step) if wider else None
        )
